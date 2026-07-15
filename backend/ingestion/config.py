"""Configuration for the ingestion pipeline."""
import os
from datetime import timedelta
from typing import Optional


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


SEEDED_ZIPS: list[str] = _env_list(
    "SEEDED_ZIPS",
    ["75201", "75205", "75225", "75093", "75024"],
)

COUNTIES_ACTIVE: list[str] = _env_list("COUNTIES_ACTIVE", ["dallas"])

API_BUDGETS: dict[str, Optional[int]] = {
    "rentcast": int(os.getenv("RENTCAST_MONTHLY_LIMIT", "50")),
    "attom": None,
    "census": None,
}

_TTLS: dict[tuple[str, str], timedelta] = {
    ("rentcast", "markets"): timedelta(days=30),
    ("rentcast", "sale_comparables"): timedelta(days=90),
    ("rentcast", "sale_listings"): timedelta(days=90),
    ("rentcast", "properties"): timedelta(days=365),
    ("rentcast", "avm_value"): timedelta(days=30),
    ("rentcast", "avm_rent"): timedelta(days=30),
    ("census_acs", "*"): timedelta(days=365),
    ("fema_flood", "*"): timedelta(days=365),
    ("walkscore", "*"): timedelta(days=365),
}


def get_ttl(source: str, endpoint: str) -> Optional[timedelta]:
    """Return TTL for (source, endpoint), or the source's wildcard fallback."""
    if (source, endpoint) in _TTLS:
        return _TTLS[(source, endpoint)]
    if (source, "*") in _TTLS:
        return _TTLS[(source, "*")]
    return None
