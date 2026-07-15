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
    """Read county_parcels for SEEDED_ZIPS, upsert to properties. Returns row count."""
    zips = config.SEEDED_ZIPS
    result = (
        db.client.table("county_parcels")
        .select("*")
        .eq("county", "dallas")
        .in_("situs_zip", zips)
        .execute()
    )
    adapter = DCADAdapter()
    count = 0
    for parcel in result.data:
        prop = adapter.to_property_row(parcel)
        prop["last_synced_at"] = _now_iso()
        await db.upsert_property(prop)
        count += 1
    return count


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
