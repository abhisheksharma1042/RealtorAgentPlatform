"""US Census ACS 5-year adapter (zip-level enrichment)."""
import os
from typing import Any, Optional

import httpx

from backend.db.client import db
from backend.ingestion.sources.base import SourceAdapter


class CensusAdapter(SourceAdapter):
    provider_name = "census_acs"
    BASE_URL = "https://api.census.gov/data/2022/acs/acs5"
    VARS = ["B01003_001E", "B19013_001E", "B25077_001E", "B25064_001E"]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("CENSUS_API_KEY", "")

    async def fetch_zip_stats(self, zip_code: str) -> dict[str, Any]:
        cached = await db.fetch_enrichment("census_acs", zip_code)
        if cached is not None:
            return cached
        params = {
            "get": "NAME," + ",".join(self.VARS),
            "for": f"zip code tabulation area:{zip_code}",
            "key": self.api_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            raw = resp.json()
        normalized = self._parse(raw)
        await db.upsert_enrichment("census_acs", zip_code, normalized, ttl_days=365)
        return normalized

    async def fetch(self, **params: Any) -> dict[str, Any]:
        return await self.fetch_zip_stats(params["zip_code"])

    def _parse(self, raw: list) -> dict[str, Any]:
        if len(raw) < 2:
            return {}
        header, row = raw[0], raw[1]
        idx = {name: i for i, name in enumerate(header)}

        def _num(var: str) -> Any:
            v = row[idx[var]]
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        return {
            "total_population": _num("B01003_001E"),
            "median_household_income": _num("B19013_001E"),
            "median_home_value": _num("B25077_001E"),
            "median_gross_rent": _num("B25064_001E"),
        }

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("Census enrichment writes to enrichment_cache, not properties")
