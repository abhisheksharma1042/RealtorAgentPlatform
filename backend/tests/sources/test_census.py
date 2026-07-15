import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from backend.ingestion.sources.census import CensusAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_zip_stats_hits_api_first_call(monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "test_key")
    fixture = json.loads((FIXTURES / "census_acs_sample.json").read_text())

    fake_db = AsyncMock()
    fake_db.fetch_enrichment.side_effect = [
        None,
        {
            "total_population": 24831,
            "median_household_income": 162813,
            "median_home_value": 1250000,
            "median_gross_rent": 1875,
        },
    ]

    with patch("backend.ingestion.sources.census.db", fake_db):
        adapter = CensusAdapter()
        with respx.mock(assert_all_called=False) as router:
            route = router.route(host="api.census.gov").mock(
                return_value=httpx.Response(200, json=fixture)
            )
            first = await adapter.fetch_zip_stats("75205")
            second = await adapter.fetch_zip_stats("75205")

    assert first["total_population"] == 24831
    assert first["median_household_income"] == 162813
    assert first["median_home_value"] == 1250000
    assert first["median_gross_rent"] == 1875
    assert second == first
    assert route.call_count == 1
