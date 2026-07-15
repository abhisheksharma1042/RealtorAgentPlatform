import pytest
from unittest.mock import AsyncMock, patch

from backend.ingestion.budget import (
    with_budget,
    get_or_fetch,
    BudgetExhausted,
    first_of_month_utc,
    hash_params,
)


def test_first_of_month_utc_returns_first_day():
    result = first_of_month_utc()
    assert result.day == 1


def test_hash_params_is_deterministic():
    assert hash_params({"zip": "75205", "beds": 3}) == hash_params({"beds": 3, "zip": "75205"})


def test_hash_params_differs_for_different_values():
    assert hash_params({"zip": "75205"}) != hash_params({"zip": "75201"})


@pytest.mark.asyncio
async def test_with_budget_increments_and_yields():
    fake_db = AsyncMock()
    fake_db.get_or_create_budget_row.return_value = {"requests_used": 0, "monthly_limit": 50}
    fake_db.increment_budget.return_value = {"requests_used": 1}

    with patch("backend.ingestion.budget.db", fake_db):
        async with with_budget("rentcast"):
            pass

    fake_db.increment_budget.assert_awaited_once()
    fake_db.decrement_budget.assert_not_awaited()


@pytest.mark.asyncio
async def test_with_budget_raises_when_at_limit():
    fake_db = AsyncMock()
    fake_db.get_or_create_budget_row.return_value = {"requests_used": 50, "monthly_limit": 50}

    with patch("backend.ingestion.budget.db", fake_db):
        with pytest.raises(BudgetExhausted):
            async with with_budget("rentcast"):
                pass

    fake_db.increment_budget.assert_not_awaited()


@pytest.mark.asyncio
async def test_with_budget_decrements_on_exception():
    fake_db = AsyncMock()
    fake_db.get_or_create_budget_row.return_value = {"requests_used": 0, "monthly_limit": 50}
    fake_db.increment_budget.return_value = {"requests_used": 1}

    with patch("backend.ingestion.budget.db", fake_db):
        with pytest.raises(RuntimeError):
            async with with_budget("rentcast"):
                raise RuntimeError("API failed")

    fake_db.increment_budget.assert_awaited_once()
    fake_db.decrement_budget.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_fetch_returns_cache_hit_without_calling_fetcher():
    fake_db = AsyncMock()
    fake_db.fetch_api_response.return_value = {"response": {"cached": True}, "expires_at": None}
    fetcher = AsyncMock()

    with patch("backend.ingestion.budget.db", fake_db):
        result = await get_or_fetch(
            provider="rentcast",
            endpoint="markets",
            params={"zip": "75205"},
            ttl_days=30,
            fetcher=fetcher,
        )

    assert result == {"cached": True}
    fetcher.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_fetch_calls_fetcher_on_miss():
    fake_db = AsyncMock()
    fake_db.fetch_api_response.return_value = None
    fake_db.get_or_create_budget_row.return_value = {"requests_used": 0, "monthly_limit": 50}
    fake_db.increment_budget.return_value = {"requests_used": 1}
    fetcher = AsyncMock(return_value={"fresh": True})

    with patch("backend.ingestion.budget.db", fake_db):
        result = await get_or_fetch(
            provider="rentcast",
            endpoint="markets",
            params={"zip": "75205"},
            ttl_days=30,
            fetcher=fetcher,
        )

    assert result == {"fresh": True}
    fetcher.assert_awaited_once()
    fake_db.save_api_response.assert_awaited_once()
