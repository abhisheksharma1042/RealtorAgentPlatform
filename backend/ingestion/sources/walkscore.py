"""Walk Score adapter (walk/transit/bike scores by address+coordinate)."""
import os
from typing import Any, Optional

import httpx

from backend.db.client import db
from backend.ingestion.sources.base import SourceAdapter


class WalkScoreAdapter(SourceAdapter):
    provider_name = "walkscore"
    URL = "https://api.walkscore.com/score"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("WALKSCORE_API_KEY", "")

    async def fetch_scores(self, address: str, lat: float, lon: float) -> dict[str, Any]:
        cache_key = f"{round(lat, 5)},{round(lon, 5)}"
        cached = await db.fetch_enrichment("walkscore", cache_key)
        if cached is not None:
            return cached
        params = {
            "format": "json",
            "address": address,
            "lat": lat,
            "lon": lon,
            "transit": 1,
            "bike": 1,
            "wsapikey": self.api_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.URL, params=params)
            resp.raise_for_status()
            raw = resp.json()
        normalized = {
            "walk_score": raw.get("walkscore"),
            "walk_description": raw.get("description"),
            "transit_score": (raw.get("transit") or {}).get("score"),
            "bike_score": (raw.get("bike") or {}).get("score"),
        }
        await db.upsert_enrichment("walkscore", cache_key, normalized, ttl_days=365)
        return normalized

    async def fetch(self, **params: Any) -> dict[str, Any]:
        return await self.fetch_scores(params["address"], params["lat"], params["lon"])

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError
