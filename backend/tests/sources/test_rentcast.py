import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from backend.ingestion.sources.rentcast import RentCastAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.asyncio
async def test_fetch_market_uses_cache_on_second_call(monkeypatch):
    """Second identical fetch is served from cache, not the network."""
    monkeypatch.setenv("RENTCAST_API_KEY", "test_key")

    market_response = load_fixture("rentcast_markets.json")

    # Simulate a DB with an empty cache on first call, populated on second
    fake_db = AsyncMock()
    fake_db.fetch_api_response.side_effect = [
        None,
        {"response": market_response, "expires_at": None},
    ]
    fake_db.get_or_create_budget_row.return_value = {"requests_used": 0, "monthly_limit": 50}
    fake_db.increment_budget.return_value = {"requests_used": 1}

    with patch("backend.ingestion.budget.db", fake_db):
        adapter = RentCastAdapter()
        with respx.mock(assert_all_called=False) as router:
            route = router.route(host="api.rentcast.io", path="/v1/markets").mock(
                return_value=httpx.Response(200, json=market_response)
            )
            first = await adapter.fetch_market("75205")
            second = await adapter.fetch_market("75205")

    assert first == market_response
    assert second == market_response
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_normalize_market_produces_market_stats_row():
    adapter = RentCastAdapter()
    raw = load_fixture("rentcast_markets.json")
    rows = await adapter.normalize_market("75205", raw)
    assert len(rows) >= 1
    row = rows[0]
    assert row["zip_code"] == "75205"
    assert row["median_price"] == 1250000
    assert row["property_type"] == "all"
    assert row["median_price_per_sqft"] == 425


@pytest.mark.asyncio
async def test_normalize_sold_listings_produces_property_rows():
    adapter = RentCastAdapter()
    listings = load_fixture("rentcast_sale_listings.json")
    rows = await adapter.normalize_sold_listings(listings)
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "rentcast"
    assert row["external_id"] == "rc_abc123"
    assert row["zip_code"] == "75205"
    assert row["beds"] == 4
    assert row["baths"] == 3.5
    assert row["sqft"] == 3200
    assert row["status"] == "sold"
    assert row["sold_price"] == 1350000
