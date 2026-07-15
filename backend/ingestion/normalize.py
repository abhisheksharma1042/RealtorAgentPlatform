"""Raw-layer -> normalized layer: address normalization, dedup, merge."""
import re
from datetime import datetime, timezone
from typing import Any

from backend.db.client import db
from backend.ingestion import config
from backend.ingestion.sources.dcad import DCADAdapter
from backend.ingestion.sources.rentcast import RentCastAdapter


_PUNCT_RE = re.compile(r"[.,#]")
_WS_RE = re.compile(r"\s+")


def normalize_address(addr: str) -> str:
    """Uppercase, strip punctuation, collapse whitespace. Deterministic dedup key."""
    if not addr:
        return ""
    s = addr.upper()
    s = _PUNCT_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


# County wins for these physical-attribute fields.
COUNTY_PRIORITY_FIELDS = {
    "beds", "baths", "sqft", "year_built", "lot_size_acres", "property_type",
}
# RentCast wins for these market/pricing fields.
RENTCAST_PRIORITY_FIELDS = {
    "sold_price", "sold_date", "price", "list_date", "days_on_market", "status",
}


def merge_property_records(
    county_row: dict[str, Any],
    rentcast_row: dict[str, Any],
) -> dict[str, Any]:
    """Merge one county row and one rentcast row for the same physical property."""
    merged: dict[str, Any] = {}
    all_keys = set(county_row) | set(rentcast_row)
    for k in all_keys:
        c_val = county_row.get(k)
        r_val = rentcast_row.get(k)
        if k in COUNTY_PRIORITY_FIELDS:
            merged[k] = c_val if c_val is not None else r_val
        elif k in RENTCAST_PRIORITY_FIELDS:
            merged[k] = r_val if r_val is not None else c_val
        else:
            merged[k] = c_val if c_val is not None else r_val
    merged["source"] = "merged"
    merged["external_id"] = f"merged:{county_row['external_id']}"
    return merged


async def normalize_seeded_zips_from_dcad() -> int:
    """INSERT...SELECT from county_parcels to properties for SEEDED_ZIPS.

    Single SQL statement via asyncpg - the Supabase REST client caps SELECT
    at 1000 rows and would need pagination + row-by-row upserts for tens of
    thousands of parcels. This runs in one round-trip.
    """
    import os
    import asyncpg
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set - required for bulk normalize")
    zips = config.SEEDED_ZIPS
    sql = """
        INSERT INTO properties (
            source, external_id, address, city, zip_code, location, lat, lon,
            beds, baths, sqft, lot_size_acres, year_built,
            appraised_value,
            property_type, status, last_synced_at
        )
        SELECT
            'county'                                   AS source,
            county || ':' || account_num               AS external_id,
            situs_address                              AS address,
            city                                       AS city,
            situs_zip                                  AS zip_code,
            location                                   AS location,
            ST_Y(location::geometry)                   AS lat,
            ST_X(location::geometry)                   AS lon,
            bedrooms                                   AS beds,
            bathrooms                                  AS baths,
            living_area_sqft                           AS sqft,
            ROUND((land_sqft / 43560.0)::numeric, 3)   AS lot_size_acres,
            year_built                                 AS year_built,
            total_appraised                            AS appraised_value,
            NULL                                       AS property_type,
            NULL                                       AS status,
            NOW()                                      AS last_synced_at
        FROM county_parcels
        WHERE county = 'dallas' AND situs_zip = ANY($1)
        ON CONFLICT (source, external_id) DO UPDATE SET
            address = EXCLUDED.address,
            city = EXCLUDED.city,
            zip_code = EXCLUDED.zip_code,
            location = EXCLUDED.location,
            lat = EXCLUDED.lat,
            lon = EXCLUDED.lon,
            beds = EXCLUDED.beds,
            baths = EXCLUDED.baths,
            sqft = EXCLUDED.sqft,
            lot_size_acres = EXCLUDED.lot_size_acres,
            year_built = EXCLUDED.year_built,
            appraised_value = EXCLUDED.appraised_value,
            last_synced_at = EXCLUDED.last_synced_at
    """
    conn = await asyncpg.connect(db_url)
    try:
        result = await conn.execute(sql, zips)
        # result is like 'INSERT 0 41295' - the last number is affected rows
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
    finally:
        await conn.close()


async def normalize_rentcast_market_to_stats(zip_code: str, raw_market: dict[str, Any]) -> int:
    adapter = RentCastAdapter()
    rows = await adapter.normalize_market(zip_code, raw_market)
    for row in rows:
        await db.upsert_market_stat(row)
    return len(rows)


async def normalize_rentcast_listings_to_properties(listings: list[dict[str, Any]]) -> int:
    adapter = RentCastAdapter()
    rows = await adapter.normalize_sold_listings(listings)
    for row in rows:
        row["last_synced_at"] = _now_iso()
        await db.upsert_property(row)
    return len(rows)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
