"""Integration tests for db client extensions.

These require live Supabase with migration 003 applied. If SUPABASE_URL /
SUPABASE_SERVICE_KEY aren't valid, tests will fail at collection time via
the underlying supabase client - that's expected until credentials are set.
"""
import pytest
from datetime import datetime, timezone, date


@pytest.mark.asyncio
async def test_save_and_fetch_api_response_roundtrip(db):
    key = f"testkey_{datetime.now(timezone.utc).timestamp()}"
    await db.save_api_response(
        provider="rentcast_test",
        endpoint="markets",
        cache_key=key,
        params={"zip": "75205"},
        response={"median_price": 1250000},
        ttl_days=30,
    )
    fetched = await db.fetch_api_response("rentcast_test", "markets", key)
    assert fetched is not None
    assert fetched["response"]["median_price"] == 1250000
    assert fetched["expires_at"] is not None


@pytest.mark.asyncio
async def test_fetch_api_response_miss_returns_none(db):
    result = await db.fetch_api_response("rentcast_test", "markets", "does_not_exist")
    assert result is None


@pytest.mark.asyncio
async def test_budget_row_creation_and_increment(db):
    period = date.today().replace(day=1)
    provider = f"testprov_{period.isoformat()}"
    row = await db.get_or_create_budget_row(provider, period, monthly_limit=10)
    assert row["requests_used"] == 0
    updated = await db.increment_budget(provider, period)
    assert updated["requests_used"] == 1
    reverted = await db.decrement_budget(provider, period)
    assert reverted["requests_used"] == 0


@pytest.mark.asyncio
async def test_enrichment_cache_roundtrip(db):
    key = f"testkey_{datetime.now(timezone.utc).timestamp()}"
    await db.upsert_enrichment(
        source="census_acs_test",
        cache_key=key,
        data={"total_population": 24831},
        ttl_days=365,
    )
    fetched = await db.fetch_enrichment("census_acs_test", key)
    assert fetched == {"total_population": 24831}
