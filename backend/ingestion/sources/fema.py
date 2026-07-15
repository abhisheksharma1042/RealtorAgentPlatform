"""FEMA National Flood Hazard Layer adapter (unauthenticated)."""
from typing import Any

import httpx

from backend.db.client import db
from backend.ingestion.sources.base import SourceAdapter


class FemaAdapter(SourceAdapter):
    provider_name = "fema_flood"
    # NFHL feature service - layer 28 is the flood hazard polygons layer.
    QUERY_URL = (
        "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query"
    )

    async def fetch_flood_zone(self, lat: float, lon: float) -> dict[str, Any]:
        cache_key = self._geo_key(lat, lon)
        cached = await db.fetch_enrichment("fema_flood", cache_key)
        if cached is not None:
            return cached
        params = {
            "f": "json",
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE",
            "returnGeometry": "false",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.QUERY_URL, params=params)
            resp.raise_for_status()
            raw = resp.json()
        normalized = self._parse(raw)
        await db.upsert_enrichment("fema_flood", cache_key, normalized, ttl_days=365)
        return normalized

    async def fetch(self, **params: Any) -> dict[str, Any]:
        return await self.fetch_flood_zone(params["lat"], params["lon"])

    def _parse(self, raw: dict[str, Any]) -> dict[str, Any]:
        features = raw.get("features") or []
        if not features:
            return {"fld_zone": None, "is_sfha": False, "zone_subty": None, "static_bfe": None}
        attrs = features[0].get("attributes", {})
        return {
            "fld_zone": attrs.get("FLD_ZONE"),
            "zone_subty": attrs.get("ZONE_SUBTY"),
            "is_sfha": attrs.get("SFHA_TF") == "T",
            "static_bfe": attrs.get("STATIC_BFE"),
        }

    def _geo_key(self, lat: float, lon: float) -> str:
        # 4 decimals ~ 11m precision - dedup near-identical lookups
        return f"{round(lat, 4)},{round(lon, 4)}"

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError
