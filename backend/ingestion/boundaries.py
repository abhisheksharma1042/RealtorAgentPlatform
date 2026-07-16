"""Fetch ZCTA boundary polygons from Census TIGERweb (free, no key).

Stored once per seeded zip in zip_boundaries; the coverage_map widget
renders them. TIGERweb layer note: layer 4 of PUMA_TAD_TAZ_UGA_ZCTA is
'2020 Census ZIP Code Tabulation Areas'. If a live run returns no
features, list layers at .../MapServer?f=json and update the layer id.
"""
from typing import Any, Optional

import httpx

from backend.db.client import db

TIGERWEB_ZCTA_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "PUMA_TAD_TAZ_UGA_ZCTA/MapServer/4/query"
)


async def fetch_boundary(zip_code: str) -> Optional[dict[str, Any]]:
    """Return the GeoJSON Feature for one ZCTA, or None if not found."""
    params = {
        "where": f"ZCTA5='{zip_code}'",
        "outFields": "ZCTA5",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(TIGERWEB_ZCTA_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    features = data.get("features") or []
    if not features:
        return None
    return features[0]


async def backfill_boundaries(zips: list[str]) -> int:
    """Fetch + upsert boundaries for the given zips. Returns count stored."""
    count = 0
    for zip_code in zips:
        feature = await fetch_boundary(zip_code)
        if feature is None:
            print(f"  {zip_code}: no ZCTA boundary found")
            continue
        await db.upsert_zip_boundary(zip_code, feature)
        count += 1
        print(f"  {zip_code}: boundary stored")
    return count
