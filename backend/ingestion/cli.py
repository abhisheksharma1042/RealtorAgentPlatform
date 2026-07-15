"""Ingestion CLI: `python -m backend.ingestion.cli <source> <command> [args]`."""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from backend.db.client import db  # noqa: E402 - after load_dotenv
from backend.ingestion import config, geocode, normalize  # noqa: E402
from backend.ingestion.sources.dcad import DCADAdapter  # noqa: E402
from backend.ingestion.sources.rentcast import RentCastAdapter  # noqa: E402


async def dcad_refresh(args: argparse.Namespace) -> int:
    adapter = DCADAdapter()
    path = args.file
    if not path:
        print("Downloading DCAD bulk export (~196MB)...")
        path = await adapter.fetch()
        print(f"Saved to {path}")
    print(f"Parsing {path}...")

    is_zip = str(path).lower().endswith(".zip")
    if is_zip:
        # Real DCAD zip - filter to seeded zips at parse time to keep memory bounded
        parcels_iter = adapter.parse_zip(path, seeded_zips=config.SEEDED_ZIPS)
    else:
        # Legacy flat CSV (test fixture)
        parcels_iter = adapter.parse_csv(path)

    BATCH = 500
    inserted = 0
    batch: list[dict] = []
    for parcel in parcels_iter:
        if not parcel["account_num"]:
            continue
        batch.append(parcel)
        if len(batch) >= BATCH:
            await db.upsert_county_parcels_asyncpg(batch)
            inserted += len(batch)
            print(f"  ... {inserted} parcels")
            batch = []
    if batch:
        await db.upsert_county_parcels_asyncpg(batch)
        inserted += len(batch)
    print(f"Upserted {inserted} parcels into county_parcels.")
    print("Normalizing seeded zips into properties...")
    n = await normalize.normalize_seeded_zips_from_dcad()
    print(f"Upserted {n} rows into properties (source=county).")
    return 0


async def geocode_backfill(args: argparse.Namespace) -> int:
    zips = args.zips.split(",") if args.zips else config.SEEDED_ZIPS
    matched, total = await geocode.backfill_county_parcels(
        zips=zips,
        only_missing=not args.all,
        limit=args.limit,
    )
    print(f"Geocoded {matched}/{total} parcels.")
    print("Refreshing properties.location from county_parcels...")
    n = await normalize.normalize_seeded_zips_from_dcad()
    print(f"Re-normalized {n} rows into properties.")
    return 0


async def rentcast_seed(args: argparse.Namespace) -> int:
    adapter = RentCastAdapter()
    zips = args.zips.split(",") if args.zips else config.SEEDED_ZIPS
    total_calls = 0
    for zip_code in zips:
        print(f"Seeding {zip_code}...")
        raw_market = await adapter.fetch_market(zip_code)
        n_stats = await normalize.normalize_rentcast_market_to_stats(zip_code, raw_market)
        print(f"  market_stats: +{n_stats}")
        total_calls += 1

        raw_listings = await adapter.fetch_sold_listings(zip_code, limit=100)
        n_props = await normalize.normalize_rentcast_listings_to_properties(raw_listings)
        print(f"  properties:  +{n_props}")
        total_calls += 1
    print(f"Done. ~{total_calls} RentCast requests consumed (subject to cache hits).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backend.ingestion.cli")
    sub = parser.add_subparsers(dest="source", required=True)

    dcad = sub.add_parser("dcad", help="DCAD parcel ingestion")
    dcad_sub = dcad.add_subparsers(dest="command", required=True)
    dcad_refresh_p = dcad_sub.add_parser("refresh", help="Download+ingest DCAD bulk parcels")
    dcad_refresh_p.add_argument("--file", help="Path to a local DCAD CSV (skip download)")

    geo = sub.add_parser("geocode", help="Census-based geocoding")
    geo_sub = geo.add_subparsers(dest="command", required=True)
    geo_bf = geo_sub.add_parser("backfill", help="Fill county_parcels.location via Census")
    geo_bf.add_argument("--zips", help="Comma-separated zip codes (default: SEEDED_ZIPS)")
    geo_bf.add_argument("--all", action="store_true", help="Include rows that already have location")
    geo_bf.add_argument("--limit", type=int, help="Cap on rows to geocode (for testing)")

    rent = sub.add_parser("rentcast", help="RentCast API ingestion")
    rent_sub = rent.add_subparsers(dest="command", required=True)
    rent_seed_p = rent_sub.add_parser("seed", help="Seed market_stats + sold listings for zips")
    rent_seed_p.add_argument("--zips", help="Comma-separated zip codes (default: SEEDED_ZIPS)")

    return parser


async def _dispatch(args: argparse.Namespace) -> int:
    if args.source == "dcad" and args.command == "refresh":
        return await dcad_refresh(args)
    if args.source == "geocode" and args.command == "backfill":
        return await geocode_backfill(args)
    if args.source == "rentcast" and args.command == "seed":
        return await rentcast_seed(args)
    print(f"Unknown command: {args.source} {args.command}", file=sys.stderr)
    return 2


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(_dispatch(args))


if __name__ == "__main__":
    sys.exit(main())
