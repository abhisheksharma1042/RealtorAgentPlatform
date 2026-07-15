"""Integration tests for agent tools wired to live Supabase.

Requires migration 003 applied and valid SUPABASE_URL/SERVICE_KEY.
"""
import pytest
from datetime import date

from backend.db.client import db
from backend.agent.tools import fetch_market_data, get_comparable_sales


@pytest.mark.asyncio
async def test_fetch_market_data_returns_stats_from_supabase():
    await db.upsert_market_stat({
        "zip_code": "75205",
        "period": date(2026, 6, 1).isoformat(),
        "property_type": "all",
        "median_price": 1250000,
        "avg_price": 1450000,
        "sales_volume": 87,
        "avg_days_on_market": 42,
        "median_price_per_sqft": 425,
        "active_listings_count": 203,
    })

    result = await fetch_market_data("75205")

    assert result["type"] == "market_data"
    assert result["zip_code"] == "75205"
    # Value comes back as either int or decimal-string depending on Supabase serialization
    assert str(result["median_price"]).startswith("1250000")


@pytest.mark.asyncio
async def test_get_comparable_sales_returns_county_sourced_rows():
    """County-sourced properties have status=NULL. Verify they still appear as comps."""
    await db.upsert_property({
        "source": "county",
        "external_id": "dallas:99999999",
        "address": "4712 BEVERLY DR",
        "city": "HIGHLAND PARK",
        "zip_code": "75205",
        "beds": 4,
        "baths": 3.5,
        "sqft": 3200,
    })

    result = await get_comparable_sales(zip_code="75205")

    assert result["type"] == "comparable_sales"
    assert result["count"] >= 1
    addresses = [p["address"] for p in result["properties"]]
    assert "4712 BEVERLY DR" in addresses
