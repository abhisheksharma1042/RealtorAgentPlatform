"""Provider-agnostic budget guard + cache-first fetch."""
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from backend.db.client import db
from backend.ingestion import config


class BudgetExhausted(Exception):
    def __init__(self, provider: str):
        super().__init__(f"Monthly budget exhausted for provider '{provider}'")
        self.provider = provider


def first_of_month_utc() -> date:
    now = datetime.now(timezone.utc)
    return date(now.year, now.month, 1)


def hash_params(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@asynccontextmanager
async def with_budget(provider: str):
    """Guard a metered API call. Increments on entry, decrements on exception."""
    limit = config.API_BUDGETS.get(provider)
    if limit is None:
        yield
        return

    period = first_of_month_utc()
    row = await db.get_or_create_budget_row(provider, period, monthly_limit=limit)
    if row["requests_used"] >= row["monthly_limit"]:
        raise BudgetExhausted(provider)

    await db.increment_budget(provider, period)
    try:
        yield
    except Exception:
        await db.decrement_budget(provider, period)
        raise


async def get_or_fetch(
    provider: str,
    endpoint: str,
    params: dict[str, Any],
    ttl_days: Optional[int],
    fetcher: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Cache-first fetch. Returns the response payload from cache or fresh call."""
    cache_key = hash_params(params)
    cached = await db.fetch_api_response(provider, endpoint, cache_key)
    if cached is not None:
        return cached["response"]

    async with with_budget(provider):
        response = await fetcher(params)

    await db.save_api_response(
        provider=provider,
        endpoint=endpoint,
        cache_key=cache_key,
        params=params,
        response=response,
        ttl_days=ttl_days,
    )
    return response
