# DFW Data Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded mock dictionaries in `backend/agent/tools.py` with a real Supabase-backed pipeline that ingests Dallas County parcel data (DCAD bulk export, free), RentCast API data (50 req/mo free tier), and free enrichment sources (Census ACS, FEMA NFHL, Walk Score), for 4–5 seeded DFW zip codes.

**Architecture:** Three-layer pipeline (raw → normalized → agent). Raw tables (`county_parcels`, `api_responses`, `api_budget`, `enrichment_cache`) are source-agnostic so adding TAD/CCAD/DALCAD or ATTOM later requires no schema change. A single `with_budget(provider)` context guards all metered API calls. Agent tools query the normalized layer (`properties`, `market_stats`) via the existing `db/client.py`.

**Tech Stack:** Python 3.11+, FastAPI, Supabase (PostgreSQL + PostGIS), httpx (pinned `<0.26` for supabase compat), respx (HTTP mocking), pytest + pytest-asyncio, LangGraph + Anthropic Claude Sonnet 4.5.

**Spec:** `docs/superpowers/specs/2026-07-14-dfw-data-ingestion-design.md`

---

## File Structure

**New files:**
- `backend/migrations/003_ingestion_schema.sql` — raw-layer tables + `properties` alterations
- `backend/ingestion/__init__.py`
- `backend/ingestion/config.py` — `SEEDED_ZIPS`, `COUNTIES_ACTIVE`, `API_BUDGETS`, TTL policy
- `backend/ingestion/budget.py` — `with_budget()`, `get_or_fetch()`, `BudgetExhausted`
- `backend/ingestion/normalize.py` — raw → `properties`/`market_stats`, address normalization + dedup
- `backend/ingestion/cli.py` — `python -m backend.ingestion.cli <source> <command>`
- `backend/ingestion/sources/__init__.py`
- `backend/ingestion/sources/base.py` — `SourceAdapter` abstract base
- `backend/ingestion/sources/rentcast.py`
- `backend/ingestion/sources/dcad.py`
- `backend/ingestion/sources/census.py`
- `backend/ingestion/sources/fema.py`
- `backend/ingestion/sources/walkscore.py`
- `backend/tests/__init__.py`
- `backend/tests/conftest.py` — pytest fixtures (`db`, `mock_http`)
- `backend/tests/test_budget.py`
- `backend/tests/test_normalize.py`
- `backend/tests/sources/__init__.py`
- `backend/tests/sources/test_rentcast.py`
- `backend/tests/sources/test_dcad.py`
- `backend/tests/sources/test_census.py`
- `backend/tests/sources/test_fema.py`
- `backend/tests/sources/test_walkscore.py`
- `backend/tests/test_agent_tools_integration.py`
- `backend/tests/fixtures/rentcast_markets.json`
- `backend/tests/fixtures/rentcast_sale_listings.json`
- `backend/tests/fixtures/dcad_parcel_sample.csv`
- `backend/tests/fixtures/census_acs_sample.json`
- `backend/tests/fixtures/fema_nfhl_sample.json`
- `backend/tests/fixtures/walkscore_sample.json`

**Modified files:**
- `backend/requirements.txt` — add `pytest`, `pytest-asyncio`, `respx`
- `backend/.env` — add `RENTCAST_API_KEY`, `CENSUS_API_KEY`, `WALKSCORE_API_KEY`
- `backend/db/client.py` — add `fetch_api_response`, `save_api_response`, `get_budget_row`, `increment_budget`, `decrement_budget`, `upsert_county_parcel`, `upsert_property`; drop the `status='sold'` filter in `get_comparable_sales`
- `backend/agent/tools.py` — delete `MOCK_*` dicts, wire to `db` + lazy fetch

---

## Task 0: Test scaffolding and env

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/sources/__init__.py`
- Modify: `backend/.env` (user has this open in the IDE — coordinate)

- [ ] **Step 1: Add test dependencies to requirements.txt**

Append to `backend/requirements.txt`:
```
# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
respx>=0.20.0,<0.22
```

- [ ] **Step 2: Install**

Run: `cd backend && source venv/bin/activate && pip install -r requirements.txt`
Expected: successful install, no version conflicts with `httpx<0.26`.

- [ ] **Step 3: Create test package roots**

Create `backend/tests/__init__.py` — empty file.
Create `backend/tests/sources/__init__.py` — empty file.

- [ ] **Step 4: Create conftest.py**

Create `backend/tests/conftest.py`:
```python
import asyncio
import os
import pytest
import respx
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_http():
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def db():
    from backend.db.client import db as real_db
    return real_db
```

- [ ] **Step 5: Add env var placeholders**

Add to `backend/.env` (do not overwrite existing values):
```
# Real estate data providers
RENTCAST_API_KEY=
CENSUS_API_KEY=
WALKSCORE_API_KEY=
```
FEMA and DCAD are unauthenticated — no keys.

- [ ] **Step 6: Verify pytest discovers no tests yet**

Run: `cd backend && source venv/bin/activate && pytest -q`
Expected: `no tests ran`.

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/tests/__init__.py backend/tests/sources/__init__.py backend/tests/conftest.py backend/.env
git commit -m "chore: add pytest + respx test scaffolding for ingestion"
```

---

## Task 1: Schema migration 003

**Files:**
- Create: `backend/migrations/003_ingestion_schema.sql`

- [ ] **Step 1: Write the migration SQL**

Create `backend/migrations/003_ingestion_schema.sql`:
```sql
-- Migration 003: Ingestion pipeline (raw layer + properties alterations)

BEGIN;

CREATE TABLE IF NOT EXISTS county_parcels (
  county            VARCHAR(20)  NOT NULL,
  account_num       VARCHAR(40)  NOT NULL,
  situs_address     TEXT         NOT NULL,
  situs_zip         VARCHAR(10),
  city              VARCHAR(100),
  land_use_code     VARCHAR(20),
  living_area_sqft  INTEGER,
  land_sqft         INTEGER,
  year_built        INTEGER,
  bedrooms          INTEGER,
  bathrooms         DECIMAL(3,1),
  total_appraised   DECIMAL(12,2),
  land_value        DECIMAL(12,2),
  improvement_value DECIMAL(12,2),
  tax_year          INTEGER,
  location          GEOGRAPHY(POINT, 4326),
  raw               JSONB,
  source_updated_at TIMESTAMPTZ,
  fetched_at        TIMESTAMPTZ  DEFAULT NOW(),
  PRIMARY KEY (county, account_num)
);
CREATE INDEX IF NOT EXISTS idx_county_parcels_zip     ON county_parcels(situs_zip);
CREATE INDEX IF NOT EXISTS idx_county_parcels_address ON county_parcels
  USING GIN(to_tsvector('english', situs_address));
CREATE INDEX IF NOT EXISTS idx_county_parcels_loc     ON county_parcels USING GIST(location);

CREATE TABLE IF NOT EXISTS api_responses (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider     VARCHAR(30)  NOT NULL,
  endpoint     VARCHAR(50)  NOT NULL,
  cache_key    TEXT         NOT NULL,
  params       JSONB        NOT NULL,
  response     JSONB        NOT NULL,
  fetched_at   TIMESTAMPTZ  DEFAULT NOW(),
  expires_at   TIMESTAMPTZ,
  UNIQUE(provider, endpoint, cache_key)
);
CREATE INDEX IF NOT EXISTS idx_api_responses_provider_endpoint ON api_responses(provider, endpoint);
CREATE INDEX IF NOT EXISTS idx_api_responses_expires           ON api_responses(expires_at);

CREATE TABLE IF NOT EXISTS api_budget (
  provider       VARCHAR(30)  NOT NULL,
  period         DATE         NOT NULL,
  requests_used  INTEGER      NOT NULL DEFAULT 0,
  monthly_limit  INTEGER      NOT NULL,
  updated_at     TIMESTAMPTZ  DEFAULT NOW(),
  PRIMARY KEY (provider, period)
);

CREATE TABLE IF NOT EXISTS enrichment_cache (
  source     VARCHAR(30)  NOT NULL,
  cache_key  TEXT         NOT NULL,
  data       JSONB        NOT NULL,
  fetched_at TIMESTAMPTZ  DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  PRIMARY KEY (source, cache_key)
);

ALTER TABLE properties ALTER COLUMN mls_id DROP NOT NULL;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS external_id       VARCHAR(64);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS source            VARCHAR(30);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS last_synced_at    TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_source_external ON properties(source, external_id);

COMMIT;
```

- [ ] **Step 2: Run the migration in Supabase**

Open the Supabase SQL editor for the project, paste the SQL, and execute. Expected: `Success. No rows returned.`

- [ ] **Step 3: Verify the new tables exist**

Run in Supabase SQL editor:
```sql
SELECT tablename FROM pg_tables
 WHERE schemaname='public'
   AND tablename IN ('county_parcels','api_responses','api_budget','enrichment_cache')
 ORDER BY tablename;
```
Expected: 4 rows.

- [ ] **Step 4: Verify the properties column additions**

Run:
```sql
SELECT column_name FROM information_schema.columns
 WHERE table_name='properties'
   AND column_name IN ('external_id','source','source_updated_at','last_synced_at')
 ORDER BY column_name;
```
Expected: 4 rows.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/003_ingestion_schema.sql
git commit -m "feat(db): migration 003 - ingestion raw layer + properties alterations"
```

---

## Task 2: Ingestion config module

**Files:**
- Create: `backend/ingestion/__init__.py`
- Create: `backend/ingestion/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_config.py`:
```python
from datetime import timedelta
from backend.ingestion import config


def test_seeded_zips_are_dallas_county():
    assert config.SEEDED_ZIPS == ["75201", "75205", "75225", "75093", "75024"]


def test_dallas_is_the_only_active_county():
    assert config.COUNTIES_ACTIVE == ["dallas"]


def test_rentcast_budget_is_50():
    assert config.API_BUDGETS["rentcast"] == 50


def test_ttl_for_rentcast_markets_is_30_days():
    assert config.get_ttl("rentcast", "markets") == timedelta(days=30)


def test_ttl_for_unknown_endpoint_defaults_to_wildcard():
    assert config.get_ttl("census_acs", "any_endpoint") == timedelta(days=365)


def test_ttl_missing_source_returns_none():
    assert config.get_ttl("nope", "nope") is None
```

- [ ] **Step 2: Run test — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_config.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'backend.ingestion'`.

- [ ] **Step 3: Create ingestion package and config**

Create `backend/ingestion/__init__.py` — empty.

Create `backend/ingestion/config.py`:
```python
"""Configuration for the ingestion pipeline."""
import os
from datetime import timedelta
from typing import Optional


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


SEEDED_ZIPS: list[str] = _env_list(
    "SEEDED_ZIPS",
    ["75201", "75205", "75225", "75093", "75024"],
)

COUNTIES_ACTIVE: list[str] = _env_list("COUNTIES_ACTIVE", ["dallas"])

API_BUDGETS: dict[str, Optional[int]] = {
    "rentcast": int(os.getenv("RENTCAST_MONTHLY_LIMIT", "50")),
    "attom": None,
    "census": None,
}

_TTLS: dict[tuple[str, str], timedelta] = {
    ("rentcast", "markets"): timedelta(days=30),
    ("rentcast", "sale_comparables"): timedelta(days=90),
    ("rentcast", "sale_listings"): timedelta(days=90),
    ("rentcast", "properties"): timedelta(days=365),
    ("rentcast", "avm_value"): timedelta(days=30),
    ("rentcast", "avm_rent"): timedelta(days=30),
    ("census_acs", "*"): timedelta(days=365),
    ("fema_flood", "*"): timedelta(days=365),
    ("walkscore", "*"): timedelta(days=365),
}


def get_ttl(source: str, endpoint: str) -> Optional[timedelta]:
    """Return TTL for (source, endpoint), or the source's wildcard fallback."""
    if (source, endpoint) in _TTLS:
        return _TTLS[(source, endpoint)]
    if (source, "*") in _TTLS:
        return _TTLS[(source, "*")]
    return None
```

- [ ] **Step 4: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_config.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/ingestion/__init__.py backend/ingestion/config.py backend/tests/test_config.py
git commit -m "feat(ingestion): config module with SEEDED_ZIPS, budgets, TTL policy"
```

---

## Task 3: DB client extensions

**Files:**
- Modify: `backend/db/client.py`
- Test: `backend/tests/test_db_client_extensions.py`

Wire in helpers the ingestion + budget layers need, and fix the `status='sold'` filter bug so county-sourced parcels (which have `status=NULL`) are returned by `get_comparable_sales`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_db_client_extensions.py`:
```python
import pytest
from datetime import datetime, timezone


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
    from datetime import date
    period = date.today().replace(day=1)
    provider = f"testprov_{period.isoformat()}"
    row = await db.get_or_create_budget_row(provider, period, monthly_limit=10)
    assert row["requests_used"] == 0
    updated = await db.increment_budget(provider, period)
    assert updated["requests_used"] == 1
    reverted = await db.decrement_budget(provider, period)
    assert reverted["requests_used"] == 0
```

- [ ] **Step 2: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_db_client_extensions.py -v`
Expected: FAIL with `AttributeError: 'SupabaseDB' object has no attribute 'save_api_response'`.

- [ ] **Step 3: Extend `backend/db/client.py`**

Append these methods to the `SupabaseDB` class in `backend/db/client.py` (before the `test_connection` method):
```python
    # ---------- API response cache ----------

    async def save_api_response(
        self,
        provider: str,
        endpoint: str,
        cache_key: str,
        params: Dict[str, Any],
        response: Dict[str, Any],
        ttl_days: Optional[int] = None,
    ) -> None:
        expires_at = None
        if ttl_days is not None:
            expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
        payload = {
            "provider": provider,
            "endpoint": endpoint,
            "cache_key": cache_key,
            "params": params,
            "response": response,
            "expires_at": expires_at,
        }
        self.client.table("api_responses").upsert(
            payload,
            on_conflict="provider,endpoint,cache_key",
        ).execute()

    async def fetch_api_response(
        self,
        provider: str,
        endpoint: str,
        cache_key: str,
    ) -> Optional[Dict[str, Any]]:
        result = (
            self.client.table("api_responses")
            .select("*")
            .eq("provider", provider)
            .eq("endpoint", endpoint)
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        if row.get("expires_at"):
            expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expiry < datetime.now(expiry.tzinfo):
                return None
        return row

    # ---------- Budget accounting ----------

    async def get_or_create_budget_row(
        self,
        provider: str,
        period,
        monthly_limit: int,
    ) -> Dict[str, Any]:
        period_iso = period.isoformat()
        existing = (
            self.client.table("api_budget")
            .select("*")
            .eq("provider", provider)
            .eq("period", period_iso)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]
        inserted = (
            self.client.table("api_budget")
            .insert({
                "provider": provider,
                "period": period_iso,
                "requests_used": 0,
                "monthly_limit": monthly_limit,
            })
            .execute()
        )
        return inserted.data[0]

    async def increment_budget(self, provider: str, period) -> Dict[str, Any]:
        return await self._adjust_budget(provider, period, delta=1)

    async def decrement_budget(self, provider: str, period) -> Dict[str, Any]:
        return await self._adjust_budget(provider, period, delta=-1)

    async def _adjust_budget(self, provider: str, period, delta: int) -> Dict[str, Any]:
        period_iso = period.isoformat()
        current = (
            self.client.table("api_budget")
            .select("*")
            .eq("provider", provider)
            .eq("period", period_iso)
            .limit(1)
            .execute()
        )
        if not current.data:
            raise RuntimeError(f"No budget row for {provider} @ {period_iso}")
        new_used = max(0, current.data[0]["requests_used"] + delta)
        updated = (
            self.client.table("api_budget")
            .update({"requests_used": new_used, "updated_at": datetime.utcnow().isoformat()})
            .eq("provider", provider)
            .eq("period", period_iso)
            .execute()
        )
        return updated.data[0]

    # ---------- Upserts for normalized layer ----------

    async def upsert_county_parcel(self, parcel: Dict[str, Any]) -> None:
        self.client.table("county_parcels").upsert(
            parcel,
            on_conflict="county,account_num",
        ).execute()

    async def upsert_property(self, prop: Dict[str, Any]) -> None:
        self.client.table("properties").upsert(
            prop,
            on_conflict="source,external_id",
        ).execute()

    async def upsert_market_stat(self, stat: Dict[str, Any]) -> None:
        self.client.table("market_stats").upsert(
            stat,
            on_conflict="zip_code,period,property_type",
        ).execute()

    async def upsert_enrichment(
        self,
        source: str,
        cache_key: str,
        data: Dict[str, Any],
        ttl_days: Optional[int] = None,
    ) -> None:
        expires_at = None
        if ttl_days is not None:
            expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
        self.client.table("enrichment_cache").upsert(
            {
                "source": source,
                "cache_key": cache_key,
                "data": data,
                "expires_at": expires_at,
            },
            on_conflict="source,cache_key",
        ).execute()

    async def fetch_enrichment(
        self,
        source: str,
        cache_key: str,
    ) -> Optional[Dict[str, Any]]:
        result = (
            self.client.table("enrichment_cache")
            .select("*")
            .eq("source", source)
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        if row.get("expires_at"):
            expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expiry < datetime.now(expiry.tzinfo):
                return None
        return row["data"]
```

- [ ] **Step 4: Fix the status filter in `get_comparable_sales`**

In `backend/db/client.py`, locate the `get_comparable_sales` method and remove the hardcoded `.eq("status", "sold")` clause. The query construction becomes:
```python
        query = (
            self.client.table("properties")
            .select("*")
        )
```
(instead of previously chaining `.eq("status", "sold")` immediately). County-sourced parcels have `status=NULL`; callers filter on `sold_price`/`sold_date` presence via `sold_within_days` if needed.

- [ ] **Step 5: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_db_client_extensions.py -v`
Expected: 3 passed.

Note: these tests hit the real Supabase — the `.env` `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` must be set. The `provider="rentcast_test"` and `provider="testprov_*"` prefixes namespace test data.

- [ ] **Step 6: Commit**

```bash
git add backend/db/client.py backend/tests/test_db_client_extensions.py
git commit -m "feat(db): api response cache, budget accounting, upsert helpers"
```

---

## Task 4: Budget guard module

**Files:**
- Create: `backend/ingestion/budget.py`
- Test: `backend/tests/test_budget.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_budget.py`:
```python
import pytest
from datetime import date
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
```

- [ ] **Step 2: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_budget.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `budget.py`**

Create `backend/ingestion/budget.py`:
```python
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
        # Unlimited provider — no accounting needed
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
```

- [ ] **Step 4: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_budget.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/ingestion/budget.py backend/tests/test_budget.py
git commit -m "feat(ingestion): budget guard + cache-first get_or_fetch"
```

---

## Task 5: Base source adapter

**Files:**
- Create: `backend/ingestion/sources/__init__.py`
- Create: `backend/ingestion/sources/base.py`

- [ ] **Step 1: Create the package**

Create `backend/ingestion/sources/__init__.py` — empty.

- [ ] **Step 2: Create the abstract base**

Create `backend/ingestion/sources/base.py`:
```python
"""Abstract base for all ingestion source adapters."""
from abc import ABC, abstractmethod
from typing import Any


class SourceAdapter(ABC):
    """Contract every source adapter must satisfy.

    - `provider_name`: identifier stored in api_responses.provider or county_parcels.county
    - `fetch(**params)`: raw API call, may consume budget
    - `normalize(raw)`: transform raw response into rows for the normalized layer
    """

    provider_name: str

    @abstractmethod
    async def fetch(self, **params: Any) -> dict[str, Any]:
        """Fetch raw data from the source. Implementations should use budget.get_or_fetch."""

    @abstractmethod
    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Transform raw response into normalized rows suitable for upsert."""
```

- [ ] **Step 3: Sanity check import**

Run: `cd backend && source venv/bin/activate && python -c "from backend.ingestion.sources.base import SourceAdapter; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/ingestion/sources/__init__.py backend/ingestion/sources/base.py
git commit -m "feat(ingestion): SourceAdapter abstract base"
```

---

## Task 6: RentCast adapter

**Files:**
- Create: `backend/ingestion/sources/rentcast.py`
- Test: `backend/tests/sources/test_rentcast.py`
- Create: `backend/tests/fixtures/rentcast_markets.json`
- Create: `backend/tests/fixtures/rentcast_sale_listings.json`

**Note:** Exact RentCast endpoint paths and response shapes must be verified against https://developers.rentcast.io/reference before implementing. The endpoints listed below reflect the current documented API as of the spec date; adjust in the same task if the live docs differ.

- [ ] **Step 1: Capture fixture responses**

Verify current RentCast API endpoints:
- Markets stats: `GET /v1/markets?zipCode={zip}&historyRange=12&statsType=Sale`
- Sale listings (recent sold): `GET /v1/listings/sale?zipCode={zip}&status=Sold&limit=100`

If your team already has a RentCast key, `curl` one of each endpoint and save the responses as fixtures. Otherwise, use these minimal synthetic fixtures matching the documented shape.

Create `backend/tests/fixtures/rentcast_markets.json`:
```json
{
  "zipCode": "75205",
  "saleData": {
    "lastUpdatedDate": "2026-06-01",
    "averagePrice": 1450000,
    "medianPrice": 1250000,
    "medianPricePerSquareFoot": 425,
    "averageDaysOnMarket": 42,
    "newListings": 87,
    "totalListings": 203,
    "history": {
      "2026-06": {"medianPrice": 1250000, "averageDaysOnMarket": 42, "totalListings": 203},
      "2026-05": {"medianPrice": 1240000, "averageDaysOnMarket": 40, "totalListings": 198}
    }
  }
}
```

Create `backend/tests/fixtures/rentcast_sale_listings.json`:
```json
[
  {
    "id": "rc_abc123",
    "formattedAddress": "123 Beverly Dr, Highland Park, TX 75205",
    "addressLine1": "123 Beverly Dr",
    "city": "Highland Park",
    "state": "TX",
    "zipCode": "75205",
    "latitude": 32.8336,
    "longitude": -96.7880,
    "propertyType": "Single Family",
    "bedrooms": 4,
    "bathrooms": 3.5,
    "squareFootage": 3200,
    "lotSize": 8500,
    "yearBuilt": 1998,
    "status": "Sold",
    "price": 1350000,
    "listedDate": "2026-01-14",
    "removedDate": "2026-02-28",
    "daysOnMarket": 45,
    "lastSeenDate": "2026-02-28"
  }
]
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/sources/test_rentcast.py`:
```python
import json
import os
from pathlib import Path

import pytest
import respx
import httpx

from backend.ingestion.sources.rentcast import RentCastAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.asyncio
async def test_fetch_market_uses_cache_on_second_call(monkeypatch):
    monkeypatch.setenv("RENTCAST_API_KEY", "test_key")
    from backend.db.client import db as real_db

    # Clear any prior cache for this test key
    real_db.client.table("api_responses").delete().eq("provider", "rentcast").eq(
        "endpoint", "markets"
    ).execute()

    adapter = RentCastAdapter()
    market_response = load_fixture("rentcast_markets.json")

    with respx.mock(assert_all_called=False) as router:
        route = router.get("https://api.rentcast.io/v1/markets").mock(
            return_value=httpx.Response(200, json=market_response)
        )
        first = await adapter.fetch_market("75205")
        second = await adapter.fetch_market("75205")

    assert first == market_response
    assert second == market_response
    assert route.call_count == 1   # second call served from cache


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
```

- [ ] **Step 3: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_rentcast.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement the adapter**

Create `backend/ingestion/sources/rentcast.py`:
```python
"""RentCast API adapter — market stats + sold listings."""
import os
from typing import Any

import httpx

from backend.ingestion import config
from backend.ingestion.budget import get_or_fetch
from backend.ingestion.sources.base import SourceAdapter


class RentCastAdapter(SourceAdapter):
    provider_name = "rentcast"
    BASE_URL = "https://api.rentcast.io/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("RENTCAST_API_KEY", "")

    async def fetch(self, endpoint: str, **params: Any) -> dict[str, Any]:  # generic
        ttl = config.get_ttl("rentcast", endpoint)
        ttl_days = ttl.days if ttl else None
        return await get_or_fetch(
            provider="rentcast",
            endpoint=endpoint,
            params={"endpoint": endpoint, **params},
            ttl_days=ttl_days,
            fetcher=lambda p: self._http_get(endpoint, {k: v for k, v in p.items() if k != "endpoint"}),
        )

    async def fetch_market(self, zip_code: str) -> dict[str, Any]:
        return await self.fetch(
            "markets",
            zipCode=zip_code,
            historyRange=12,
            statsType="Sale",
        )

    async def fetch_sold_listings(self, zip_code: str, limit: int = 100) -> list[dict[str, Any]]:
        result = await self.fetch(
            "sale_listings",
            zipCode=zip_code,
            status="Sold",
            limit=limit,
        )
        # Response may be a list or wrapped
        if isinstance(result, list):
            return result
        return result.get("listings", []) if isinstance(result, dict) else []

    async def _http_get(self, endpoint: str, params: dict[str, Any]) -> Any:
        path = {
            "markets": "/markets",
            "sale_listings": "/listings/sale",
        }[endpoint]
        headers = {"X-Api-Key": self.api_key, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.BASE_URL}{path}", params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("Use normalize_market or normalize_sold_listings")

    async def normalize_market(self, zip_code: str, raw: dict[str, Any]) -> list[dict[str, Any]]:
        sale = raw.get("saleData") or {}
        history = sale.get("history") or {}
        rows: list[dict[str, Any]] = []
        for period_key, entry in history.items():
            # period_key like "2026-06"; store as first day of month
            year, month = period_key.split("-")
            period = f"{year}-{month.zfill(2)}-01"
            rows.append({
                "zip_code": zip_code,
                "period": period,
                "property_type": "all",
                "median_price": entry.get("medianPrice"),
                "avg_price": sale.get("averagePrice"),
                "sales_volume": entry.get("newListings"),
                "avg_days_on_market": entry.get("averageDaysOnMarket"),
                "median_price_per_sqft": sale.get("medianPricePerSquareFoot"),
                "active_listings_count": entry.get("totalListings"),
            })
        if not rows:
            # Fall back to a single current-period row if history is missing
            period_key = sale.get("lastUpdatedDate", "2026-01-01")[:7]
            year, month = period_key.split("-")
            rows.append({
                "zip_code": zip_code,
                "period": f"{year}-{month.zfill(2)}-01",
                "property_type": "all",
                "median_price": sale.get("medianPrice"),
                "avg_price": sale.get("averagePrice"),
                "sales_volume": sale.get("newListings"),
                "avg_days_on_market": sale.get("averageDaysOnMarket"),
                "median_price_per_sqft": sale.get("medianPricePerSquareFoot"),
                "active_listings_count": sale.get("totalListings"),
            })
        return rows

    async def normalize_sold_listings(
        self, listings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for listing in listings:
            lat = listing.get("latitude")
            lon = listing.get("longitude")
            location = f"POINT({lon} {lat})" if lat is not None and lon is not None else None
            row = {
                "source": "rentcast",
                "external_id": listing.get("id"),
                "address": listing.get("formattedAddress") or listing.get("addressLine1"),
                "city": listing.get("city"),
                "zip_code": listing.get("zipCode"),
                "location": location,
                "beds": listing.get("bedrooms"),
                "baths": listing.get("bathrooms"),
                "sqft": listing.get("squareFootage"),
                "year_built": listing.get("yearBuilt"),
                "property_type": (listing.get("propertyType") or "").lower().replace(" ", "_"),
                "status": (listing.get("status") or "").lower(),
                "sold_price": listing.get("price"),
                "sold_date": listing.get("removedDate") or listing.get("lastSeenDate"),
                "days_on_market": listing.get("daysOnMarket"),
                "list_date": listing.get("listedDate"),
                "source_updated_at": listing.get("lastSeenDate"),
            }
            if row["external_id"]:
                rows.append(row)
        return rows
```

- [ ] **Step 5: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_rentcast.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/ingestion/sources/rentcast.py backend/tests/sources/test_rentcast.py backend/tests/fixtures/rentcast_markets.json backend/tests/fixtures/rentcast_sale_listings.json
git commit -m "feat(ingestion): RentCast adapter with market + sold-listings endpoints"
```

---

## Task 7: DCAD adapter

**Files:**
- Create: `backend/ingestion/sources/dcad.py`
- Test: `backend/tests/sources/test_dcad.py`
- Create: `backend/tests/fixtures/dcad_parcel_sample.csv`

**Note:** DCAD publishes parcel data at https://www.dallascad.org/DataProducts.aspx. The bulk file's exact columns must be verified before running against production, since DCAD reformats between tax years. This task assumes the header names used below; adjust if the file has changed.

- [ ] **Step 1: Create a small fixture CSV**

Create `backend/tests/fixtures/dcad_parcel_sample.csv`:
```csv
ACCOUNT_NUM,SITUS_ADDRESS,SITUS_ZIP,SITUS_CITY,LAND_USE_CODE,LIVING_AREA_SQFT,LAND_SQFT,YEAR_BUILT,BEDROOMS,BATHROOMS,TOTAL_APPRAISED,LAND_VALUE,IMPROVEMENT_VALUE,TAX_YEAR,LATITUDE,LONGITUDE
00000012345,4712 BEVERLY DR,75205,HIGHLAND PARK,A1,3200,8500,1998,4,3.5,1450000,850000,600000,2026,32.8336,-96.7880
00000067890,3010 MOCKINGBIRD LN,75205,DALLAS,A1,2400,7200,1975,3,2.0,895000,520000,375000,2026,32.8360,-96.7855
00000099999,101 UNKNOWN ST,90210,BEVERLY HILLS,X,,,,,,,,2026,,
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/sources/test_dcad.py`:
```python
from pathlib import Path
import pytest

from backend.ingestion.sources.dcad import DCADAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_parse_csv_yields_normalized_rows():
    adapter = DCADAdapter()
    rows = list(adapter.parse_csv(FIXTURES / "dcad_parcel_sample.csv"))
    assert len(rows) == 3
    r0 = rows[0]
    assert r0["county"] == "dallas"
    assert r0["account_num"] == "00000012345"
    assert r0["situs_address"] == "4712 BEVERLY DR"
    assert r0["situs_zip"] == "75205"
    assert r0["living_area_sqft"] == 3200
    assert r0["bedrooms"] == 4
    assert r0["bathrooms"] == 3.5
    assert r0["total_appraised"] == 1450000
    assert r0["location"] == "POINT(-96.788 32.8336)"


@pytest.mark.asyncio
async def test_parse_csv_handles_missing_numerics():
    adapter = DCADAdapter()
    rows = list(adapter.parse_csv(FIXTURES / "dcad_parcel_sample.csv"))
    r2 = rows[2]
    assert r2["living_area_sqft"] is None
    assert r2["bedrooms"] is None
    assert r2["location"] is None


@pytest.mark.asyncio
async def test_normalize_to_property_row_from_parcel():
    adapter = DCADAdapter()
    parcel = {
        "county": "dallas",
        "account_num": "00000012345",
        "situs_address": "4712 BEVERLY DR",
        "situs_zip": "75205",
        "city": "HIGHLAND PARK",
        "living_area_sqft": 3200,
        "land_sqft": 8500,
        "year_built": 1998,
        "bedrooms": 4,
        "bathrooms": 3.5,
        "location": "POINT(-96.788 32.8336)",
    }
    row = adapter.to_property_row(parcel)
    assert row["source"] == "county"
    assert row["external_id"] == "dallas:00000012345"
    assert row["zip_code"] == "75205"
    assert row["beds"] == 4
    assert row["sqft"] == 3200
```

- [ ] **Step 3: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_dcad.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement the adapter**

Create `backend/ingestion/sources/dcad.py`:
```python
"""DCAD parcel bulk-export adapter."""
import csv
import io
import os
from pathlib import Path
from typing import Any, Iterator, Optional

import httpx

from backend.ingestion.sources.base import SourceAdapter


class DCADAdapter(SourceAdapter):
    provider_name = "dcad"
    county = "dallas"
    # DCAD's public parcel download URL. Override in tests / when DCAD changes hosts.
    DEFAULT_URL = os.getenv(
        "DCAD_BULK_URL",
        "https://www.dallascad.org/DataProducts/parcels_current.csv",
    )

    async def fetch(self, dest_path: Optional[str] = None) -> str:
        """Download the bulk CSV to disk. Returns the local file path."""
        dest = Path(dest_path or "/tmp/dcad_parcels.csv")
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get(self.DEFAULT_URL)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return str(dest)

    def parse_csv(self, path: str | Path) -> Iterator[dict[str, Any]]:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                yield self._row_to_parcel(r)

    def _row_to_parcel(self, r: dict[str, str]) -> dict[str, Any]:
        lat = _to_float(r.get("LATITUDE"))
        lon = _to_float(r.get("LONGITUDE"))
        location = f"POINT({lon} {lat})" if lat is not None and lon is not None else None
        return {
            "county": self.county,
            "account_num": (r.get("ACCOUNT_NUM") or "").strip(),
            "situs_address": (r.get("SITUS_ADDRESS") or "").strip(),
            "situs_zip": (r.get("SITUS_ZIP") or "").strip() or None,
            "city": (r.get("SITUS_CITY") or "").strip() or None,
            "land_use_code": (r.get("LAND_USE_CODE") or "").strip() or None,
            "living_area_sqft": _to_int(r.get("LIVING_AREA_SQFT")),
            "land_sqft": _to_int(r.get("LAND_SQFT")),
            "year_built": _to_int(r.get("YEAR_BUILT")),
            "bedrooms": _to_int(r.get("BEDROOMS")),
            "bathrooms": _to_float(r.get("BATHROOMS")),
            "total_appraised": _to_float(r.get("TOTAL_APPRAISED")),
            "land_value": _to_float(r.get("LAND_VALUE")),
            "improvement_value": _to_float(r.get("IMPROVEMENT_VALUE")),
            "tax_year": _to_int(r.get("TAX_YEAR")),
            "location": location,
            "raw": dict(r),
        }

    def to_property_row(self, parcel: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "county",
            "external_id": f"{parcel['county']}:{parcel['account_num']}",
            "address": parcel["situs_address"],
            "city": parcel.get("city"),
            "zip_code": parcel.get("situs_zip"),
            "location": parcel.get("location"),
            "beds": parcel.get("bedrooms"),
            "baths": parcel.get("bathrooms"),
            "sqft": parcel.get("living_area_sqft"),
            "lot_size_acres": _sqft_to_acres(parcel.get("land_sqft")),
            "year_built": parcel.get("year_built"),
            "property_type": None,
            "status": None,
        }

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("DCAD uses parse_csv + to_property_row directly")


def _to_int(v: Optional[str]) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _to_float(v: Optional[str]) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _sqft_to_acres(sqft: Optional[int]) -> Optional[float]:
    if sqft is None:
        return None
    return round(sqft / 43560, 3)
```

- [ ] **Step 5: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_dcad.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/ingestion/sources/dcad.py backend/tests/sources/test_dcad.py backend/tests/fixtures/dcad_parcel_sample.csv
git commit -m "feat(ingestion): DCAD parcel bulk-export adapter"
```

---

## Task 8: Census ACS adapter

**Files:**
- Create: `backend/ingestion/sources/census.py`
- Test: `backend/tests/sources/test_census.py`
- Create: `backend/tests/fixtures/census_acs_sample.json`

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/census_acs_sample.json`:
```json
[
  ["NAME","B01003_001E","B19013_001E","B25077_001E","B25064_001E","zip code tabulation area"],
  ["ZCTA5 75205","24831","162813","1250000","1875","75205"]
]
```

Column meanings: total population, median household income, median home value, median gross rent.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/sources/test_census.py`:
```python
import json
import pytest
import respx
import httpx
from pathlib import Path

from backend.ingestion.sources.census import CensusAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_zip_stats_hits_api_first_call(monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "test_key")
    from backend.db.client import db as real_db
    real_db.client.table("enrichment_cache").delete().eq("source", "census_acs").eq(
        "cache_key", "75205"
    ).execute()

    adapter = CensusAdapter()
    fixture = json.loads((FIXTURES / "census_acs_sample.json").read_text())

    with respx.mock(assert_all_called=False) as router:
        route = router.get("https://api.census.gov/data/2022/acs/acs5").mock(
            return_value=httpx.Response(200, json=fixture)
        )
        first = await adapter.fetch_zip_stats("75205")
        second = await adapter.fetch_zip_stats("75205")

    assert first["total_population"] == 24831
    assert first["median_household_income"] == 162813
    assert first["median_home_value"] == 1250000
    assert first["median_gross_rent"] == 1875
    assert first == second
    assert route.call_count == 1  # second call cached
```

- [ ] **Step 3: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_census.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

Create `backend/ingestion/sources/census.py`:
```python
"""US Census ACS 5-year adapter (zip-level enrichment)."""
import os
from typing import Any

import httpx

from backend.db.client import db
from backend.ingestion.sources.base import SourceAdapter


class CensusAdapter(SourceAdapter):
    provider_name = "census_acs"
    BASE_URL = "https://api.census.gov/data/2022/acs/acs5"
    VARS = ["B01003_001E", "B19013_001E", "B25077_001E", "B25064_001E"]

    def __init__(self, api_key: str | None = None):
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

    def _parse(self, raw: list[list[str]]) -> dict[str, Any]:
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
        raise NotImplementedError("Census enrichment is not written to properties/market_stats")
```

- [ ] **Step 5: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_census.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/ingestion/sources/census.py backend/tests/sources/test_census.py backend/tests/fixtures/census_acs_sample.json
git commit -m "feat(ingestion): Census ACS zip-level enrichment adapter"
```

---

## Task 9: FEMA NFHL adapter

**Files:**
- Create: `backend/ingestion/sources/fema.py`
- Test: `backend/tests/sources/test_fema.py`
- Create: `backend/tests/fixtures/fema_nfhl_sample.json`

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/fema_nfhl_sample.json`:
```json
{
  "features": [
    {
      "attributes": {
        "FLD_ZONE": "X",
        "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD",
        "SFHA_TF": "F",
        "STATIC_BFE": null
      }
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/sources/test_fema.py`:
```python
import json
from pathlib import Path
import pytest
import respx
import httpx

from backend.ingestion.sources.fema import FemaAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_flood_zone_returns_normalized_result(monkeypatch):
    from backend.db.client import db as real_db
    real_db.client.table("enrichment_cache").delete().eq("source", "fema_flood").execute()

    adapter = FemaAdapter()
    fixture = json.loads((FIXTURES / "fema_nfhl_sample.json").read_text())

    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith="https://hazards.fema.gov").mock(
            return_value=httpx.Response(200, json=fixture)
        )
        result = await adapter.fetch_flood_zone(lat=32.8336, lon=-96.7880)

    assert result["fld_zone"] == "X"
    assert result["is_sfha"] is False
```

- [ ] **Step 3: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_fema.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

Create `backend/ingestion/sources/fema.py`:
```python
"""FEMA National Flood Hazard Layer adapter (unauthenticated)."""
import hashlib
from typing import Any

import httpx

from backend.db.client import db
from backend.ingestion.sources.base import SourceAdapter


class FemaAdapter(SourceAdapter):
    provider_name = "fema_flood"
    # NFHL feature service — layer 28 is the flood hazard polygons layer.
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
        # 4 decimals ≈ 11m precision — dedup near-identical lookups
        return f"{round(lat, 4)},{round(lon, 4)}"

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError
```

- [ ] **Step 5: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_fema.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/ingestion/sources/fema.py backend/tests/sources/test_fema.py backend/tests/fixtures/fema_nfhl_sample.json
git commit -m "feat(ingestion): FEMA NFHL flood-zone lookup adapter"
```

---

## Task 10: Walk Score adapter

**Files:**
- Create: `backend/ingestion/sources/walkscore.py`
- Test: `backend/tests/sources/test_walkscore.py`
- Create: `backend/tests/fixtures/walkscore_sample.json`

- [ ] **Step 1: Create the fixture**

Create `backend/tests/fixtures/walkscore_sample.json`:
```json
{
  "status": 1,
  "walkscore": 72,
  "description": "Very Walkable",
  "transit": {"score": 45, "description": "Some Transit"},
  "bike": {"score": 60, "description": "Bikeable"}
}
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/sources/test_walkscore.py`:
```python
import json
from pathlib import Path
import pytest
import respx
import httpx

from backend.ingestion.sources.walkscore import WalkScoreAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_scores_parses_all_three_scores(monkeypatch):
    monkeypatch.setenv("WALKSCORE_API_KEY", "test_key")
    from backend.db.client import db as real_db
    real_db.client.table("enrichment_cache").delete().eq("source", "walkscore").execute()

    adapter = WalkScoreAdapter()
    fixture = json.loads((FIXTURES / "walkscore_sample.json").read_text())

    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith="https://api.walkscore.com").mock(
            return_value=httpx.Response(200, json=fixture)
        )
        result = await adapter.fetch_scores("4712 Beverly Dr, Highland Park, TX", 32.8336, -96.7880)

    assert result["walk_score"] == 72
    assert result["transit_score"] == 45
    assert result["bike_score"] == 60
```

- [ ] **Step 3: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_walkscore.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

Create `backend/ingestion/sources/walkscore.py`:
```python
"""Walk Score adapter (walk/transit/bike scores by address+coordinate)."""
import os
from typing import Any

import httpx

from backend.db.client import db
from backend.ingestion.sources.base import SourceAdapter


class WalkScoreAdapter(SourceAdapter):
    provider_name = "walkscore"
    URL = "https://api.walkscore.com/score"

    def __init__(self, api_key: str | None = None):
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
```

- [ ] **Step 5: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/sources/test_walkscore.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/ingestion/sources/walkscore.py backend/tests/sources/test_walkscore.py backend/tests/fixtures/walkscore_sample.json
git commit -m "feat(ingestion): Walk Score adapter"
```

---

## Task 11: Normalizer (address dedup + merge)

**Files:**
- Create: `backend/ingestion/normalize.py`
- Test: `backend/tests/test_normalize.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_normalize.py`:
```python
import pytest

from backend.ingestion.normalize import (
    normalize_address,
    merge_property_records,
)


def test_normalize_address_uppercases_and_strips_suffixes():
    assert normalize_address("4712 Beverly Dr, Highland Park, TX 75205") == "4712 BEVERLY DR HIGHLAND PARK TX 75205"


def test_normalize_address_removes_punctuation():
    assert normalize_address("123 Main St., Apt. 4B, Dallas, TX") == "123 MAIN ST APT 4B DALLAS TX"


def test_normalize_address_collapses_whitespace():
    assert normalize_address("  4712   Beverly    Dr  ") == "4712 BEVERLY DR"


def test_merge_favors_county_for_attributes_and_rentcast_for_price():
    county_row = {
        "source": "county",
        "external_id": "dallas:00000012345",
        "address": "4712 BEVERLY DR",
        "zip_code": "75205",
        "beds": 4,
        "baths": 3.5,
        "sqft": 3200,
        "year_built": 1998,
        "sold_price": None,
        "sold_date": None,
    }
    rentcast_row = {
        "source": "rentcast",
        "external_id": "rc_abc123",
        "address": "4712 BEVERLY DR",
        "zip_code": "75205",
        "beds": 4,
        "baths": 4.0,   # differs from county — county wins
        "sqft": 3250,   # differs — county wins
        "year_built": None,
        "sold_price": 1350000,
        "sold_date": "2026-02-28",
    }
    merged = merge_property_records(county_row, rentcast_row)
    assert merged["source"] == "merged"
    assert merged["external_id"] == "merged:dallas:00000012345"
    assert merged["beds"] == 4
    assert merged["baths"] == 3.5     # county wins
    assert merged["sqft"] == 3200     # county wins
    assert merged["year_built"] == 1998
    assert merged["sold_price"] == 1350000  # rentcast wins
    assert merged["sold_date"] == "2026-02-28"


def test_merge_handles_missing_county_fields():
    county_row = {
        "source": "county",
        "external_id": "dallas:00000067890",
        "address": "3010 MOCKINGBIRD LN",
        "zip_code": "75205",
        "beds": None,
        "sqft": None,
    }
    rentcast_row = {
        "source": "rentcast",
        "external_id": "rc_xyz",
        "beds": 3,
        "sqft": 2400,
        "sold_price": 895000,
    }
    merged = merge_property_records(county_row, rentcast_row)
    assert merged["beds"] == 3       # falls through to rentcast
    assert merged["sqft"] == 2400
    assert merged["sold_price"] == 895000
```

- [ ] **Step 2: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_normalize.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `normalize.py`**

Create `backend/ingestion/normalize.py`:
```python
"""Raw-layer -> normalized layer: address normalization, dedup, merge."""
import re
from typing import Any, Optional

from backend.db.client import db
from backend.ingestion import config
from backend.ingestion.sources.dcad import DCADAdapter
from backend.ingestion.sources.rentcast import RentCastAdapter


_PUNCT_RE = re.compile(r"[.,#]")
_WS_RE = re.compile(r"\s+")


def normalize_address(addr: str) -> str:
    """Uppercase, strip punctuation, collapse whitespace. Deterministic dedup key."""
    if not addr:
        return ""
    s = addr.upper()
    s = _PUNCT_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


# County wins for these physical-attribute fields.
COUNTY_PRIORITY_FIELDS = {"beds", "baths", "sqft", "year_built", "lot_size_acres", "property_type"}
# RentCast wins for these market/pricing fields.
RENTCAST_PRIORITY_FIELDS = {"sold_price", "sold_date", "price", "list_date", "days_on_market", "status"}


def merge_property_records(
    county_row: dict[str, Any],
    rentcast_row: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    all_keys = set(county_row) | set(rentcast_row)
    for k in all_keys:
        c_val = county_row.get(k)
        r_val = rentcast_row.get(k)
        if k in COUNTY_PRIORITY_FIELDS:
            merged[k] = c_val if c_val is not None else r_val
        elif k in RENTCAST_PRIORITY_FIELDS:
            merged[k] = r_val if r_val is not None else c_val
        else:
            # For neutral fields, prefer county but fall through to rentcast
            merged[k] = c_val if c_val is not None else r_val
    merged["source"] = "merged"
    merged["external_id"] = f"merged:{county_row['external_id']}"
    return merged


async def normalize_seeded_zips_from_dcad() -> int:
    """Read county_parcels for SEEDED_ZIPS, upsert to properties (source=county). Returns count."""
    zips = config.SEEDED_ZIPS
    result = (
        db.client.table("county_parcels")
        .select("*")
        .eq("county", "dallas")
        .in_("situs_zip", zips)
        .execute()
    )
    adapter = DCADAdapter()
    count = 0
    for parcel in result.data:
        prop = adapter.to_property_row(parcel)
        prop["last_synced_at"] = _now_iso()
        await db.upsert_property(prop)
        count += 1
    return count


async def normalize_rentcast_market_to_stats(zip_code: str, raw_market: dict[str, Any]) -> int:
    adapter = RentCastAdapter()
    rows = await adapter.normalize_market(zip_code, raw_market)
    for row in rows:
        await db.upsert_market_stat(row)
    return len(rows)


async def normalize_rentcast_listings_to_properties(listings: list[dict[str, Any]]) -> int:
    adapter = RentCastAdapter()
    rows = await adapter.normalize_sold_listings(listings)
    for row in rows:
        row["last_synced_at"] = _now_iso()
        await db.upsert_property(row)
    return len(rows)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_normalize.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/ingestion/normalize.py backend/tests/test_normalize.py
git commit -m "feat(ingestion): normalizer with address dedup and county+rentcast merge rules"
```

---

## Task 12: Ingestion CLI

**Files:**
- Create: `backend/ingestion/cli.py`

- [ ] **Step 1: Write the CLI**

Create `backend/ingestion/cli.py`:
```python
"""Ingestion CLI: `python -m backend.ingestion.cli <source> <command> [args]`."""
import argparse
import asyncio
import sys

from backend.db.client import db
from backend.ingestion import config, normalize
from backend.ingestion.sources.dcad import DCADAdapter
from backend.ingestion.sources.rentcast import RentCastAdapter


async def dcad_refresh(args: argparse.Namespace) -> int:
    adapter = DCADAdapter()
    path = args.file
    if not path:
        print("Downloading DCAD bulk export...")
        path = await adapter.fetch()
        print(f"Saved to {path}")
    print(f"Parsing {path}...")
    inserted = 0
    for parcel in adapter.parse_csv(path):
        if not parcel["account_num"]:
            continue
        await db.upsert_county_parcel(parcel)
        inserted += 1
        if inserted % 1000 == 0:
            print(f"  ... {inserted} parcels")
    print(f"Upserted {inserted} parcels into county_parcels.")
    print("Normalizing seeded zips into properties...")
    n = await normalize.normalize_seeded_zips_from_dcad()
    print(f"Upserted {n} rows into properties (source=county).")
    return 0


async def rentcast_seed(args: argparse.Namespace) -> int:
    adapter = RentCastAdapter()
    zips = args.zips.split(",") if args.zips else config.SEEDED_ZIPS
    total_calls = 0
    for zip_code in zips:
        print(f"Seeding {zip_code}...")
        raw_market = await adapter.fetch_market(zip_code)
        n_stats = await normalize.normalize_rentcast_market_to_stats(zip_code, raw_market)
        print(f"  market_stats: +{n_stats}")
        total_calls += 1

        raw_listings = await adapter.fetch_sold_listings(zip_code, limit=100)
        n_props = await normalize.normalize_rentcast_listings_to_properties(raw_listings)
        print(f"  properties:  +{n_props}")
        total_calls += 1
    print(f"Done. ~{total_calls} RentCast requests consumed (subject to cache hits).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="backend.ingestion.cli")
    sub = parser.add_subparsers(dest="source", required=True)

    dcad = sub.add_parser("dcad", help="DCAD parcel ingestion")
    dcad_sub = dcad.add_subparsers(dest="command", required=True)
    dcad_refresh_p = dcad_sub.add_parser("refresh", help="Download+ingest DCAD bulk parcels")
    dcad_refresh_p.add_argument("--file", help="Path to a local DCAD CSV (skip download)")

    rent = sub.add_parser("rentcast", help="RentCast API ingestion")
    rent_sub = rent.add_subparsers(dest="command", required=True)
    rent_seed_p = rent_sub.add_parser("seed", help="Seed market_stats + sold listings for zips")
    rent_seed_p.add_argument("--zips", help="Comma-separated zip codes (default: SEEDED_ZIPS)")

    return parser


async def _dispatch(args: argparse.Namespace) -> int:
    if args.source == "dcad" and args.command == "refresh":
        return await dcad_refresh(args)
    if args.source == "rentcast" and args.command == "seed":
        return await rentcast_seed(args)
    print(f"Unknown command: {args.source} {args.command}", file=sys.stderr)
    return 2


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(_dispatch(args))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify help works**

Run: `cd backend && source venv/bin/activate && python -m backend.ingestion.cli --help`
Expected: usage message with `dcad` and `rentcast` subcommands.

- [ ] **Step 3: Verify subcommand help**

Run: `cd backend && source venv/bin/activate && python -m backend.ingestion.cli dcad refresh --help`
Expected: help showing `--file` option.

- [ ] **Step 4: Commit**

```bash
git add backend/ingestion/cli.py
git commit -m "feat(ingestion): CLI with dcad refresh + rentcast seed commands"
```

---

## Task 13: Wire the agent tools to Supabase

**Files:**
- Modify: `backend/agent/tools.py`
- Test: `backend/tests/test_agent_tools_integration.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_agent_tools_integration.py`:
```python
import pytest
from datetime import date

from backend.db.client import db
from backend.agent.tools import fetch_market_data, get_comparable_sales


@pytest.mark.asyncio
async def test_fetch_market_data_returns_stats_from_supabase():
    # Arrange: insert a market_stats row for 75205
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

    # Act
    result = await fetch_market_data("75205")

    # Assert
    assert result["type"] == "market_data"
    assert result["zip_code"] == "75205"
    assert result["median_price"] == 1250000 or result["median_price"] == "1250000.00"


@pytest.mark.asyncio
async def test_get_comparable_sales_returns_county_sourced_rows():
    # Arrange: insert a county-sourced property (status is NULL — must still be returned
    # after the get_comparable_sales status-filter fix from Task 3)
    await db.upsert_property({
        "source": "county",
        "external_id": "dallas:00000012345",
        "address": "4712 BEVERLY DR",
        "city": "HIGHLAND PARK",
        "zip_code": "75205",
        "beds": 4,
        "baths": 3.5,
        "sqft": 3200,
    })

    # Act
    result = await get_comparable_sales(zip_code="75205")

    # Assert
    assert result["type"] == "comparable_sales"
    assert result["count"] >= 1
    addresses = [p["address"] for p in result["properties"]]
    assert "4712 BEVERLY DR" in addresses
```

- [ ] **Step 2: Run — should fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_agent_tools_integration.py -v`
Expected: FAIL — `fetch_market_data` currently returns hardcoded mocks that ignore Supabase, and/or `get_comparable_sales` filters out the NULL-status row.

- [ ] **Step 3: Rewrite `backend/agent/tools.py`**

Overwrite `backend/agent/tools.py` with the live-data implementation. This deletes the `MOCK_MARKET_DATA` and `MOCK_COMPARABLE_SALES` dicts:
```python
"""Tool definitions for the DFW Realtor Agent (live Supabase-backed)."""
from typing import Any, Dict, Optional

from backend.db.client import db


async def fetch_market_data(
    zip_code: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    property_type: str = "all",
) -> Dict[str, Any]:
    """Fetch aggregate market statistics for a DFW ZIP code."""
    stats = await db.get_market_stats(
        zip_code=zip_code, months=12, property_type=property_type
    )
    if not stats:
        # Lazy fetch via RentCast, budget permitting
        try:
            from backend.ingestion.sources.rentcast import RentCastAdapter
            from backend.ingestion import normalize
            raw = await RentCastAdapter().fetch_market(zip_code)
            await normalize.normalize_rentcast_market_to_stats(zip_code, raw)
            stats = await db.get_market_stats(
                zip_code=zip_code, months=12, property_type=property_type
            )
        except Exception as exc:
            return {
                "type": "market_data",
                "zip_code": zip_code,
                "error": f"No cached data and live fetch failed: {exc}",
            }
    if not stats:
        return {"type": "market_data", "zip_code": zip_code, "error": "No data available"}

    latest = stats[0]
    return {
        "type": "market_data",
        "zip_code": zip_code,
        "property_type": property_type,
        "median_price": latest.get("median_price"),
        "avg_price": latest.get("avg_price"),
        "sales_volume": latest.get("sales_volume"),
        "avg_days_on_market": latest.get("avg_days_on_market"),
        "median_price_per_sqft": latest.get("median_price_per_sqft"),
        "active_listings_count": latest.get("active_listings_count"),
        "history": stats,
    }


async def get_comparable_sales(
    zip_code: Optional[str] = None,
    beds_min: Optional[int] = None,
    beds_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    sqft_min: Optional[int] = None,
    sqft_max: Optional[int] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Retrieve comparable properties from the normalized layer."""
    return await db.get_comparable_sales(
        zip_code=zip_code,
        beds_min=beds_min,
        beds_max=beds_max,
        price_min=price_min,
        price_max=price_max,
        sqft_min=sqft_min,
        sqft_max=sqft_max,
        limit=limit,
    )


TOOLS = [
    {
        "name": "fetch_market_data",
        "description": "Fetch aggregate market statistics for a DFW ZIP code including median price, sales volume, days on market, and trends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zip_code": {"type": "string", "description": "The ZIP code to query (e.g., '75205' for Highland Park)"},
                "date_from": {"type": "string", "description": "Start date for data range (optional, format: YYYY-MM-DD)"},
                "date_to": {"type": "string", "description": "End date for data range (optional, format: YYYY-MM-DD)"},
                "property_type": {"type": "string", "enum": ["single_family", "condo", "townhome", "all"], "description": "Type of property to filter by"},
            },
            "required": ["zip_code"],
        },
    },
    {
        "name": "get_comparable_sales",
        "description": "Retrieve comparable properties from the normalized data layer, filtered by location and attributes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zip_code": {"type": "string", "description": "ZIP code to search in"},
                "beds_min": {"type": "integer", "description": "Minimum number of bedrooms"},
                "beds_max": {"type": "integer", "description": "Maximum number of bedrooms"},
                "price_min": {"type": "number", "description": "Minimum price in dollars"},
                "price_max": {"type": "number", "description": "Maximum price in dollars"},
                "sqft_min": {"type": "integer", "description": "Minimum square footage"},
                "sqft_max": {"type": "integer", "description": "Maximum square footage"},
                "limit": {"type": "integer", "description": "Maximum number of results to return", "default": 20},
            },
            "required": ["zip_code"],
        },
    },
]

TOOL_FUNCTIONS = {
    "fetch_market_data": fetch_market_data,
    "get_comparable_sales": get_comparable_sales,
}
```

- [ ] **Step 4: Run tests — should pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_agent_tools_integration.py -v`
Expected: 2 passed.

- [ ] **Step 5: Full test suite regression check**

Run: `cd backend && source venv/bin/activate && pytest -v`
Expected: all tests from prior tasks + these 2 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/agent/tools.py backend/tests/test_agent_tools_integration.py
git commit -m "feat(agent): wire fetch_market_data + get_comparable_sales to Supabase, delete mocks"
```

---

## Task 14: End-to-end smoke test

**Files:**
- (No new files — manual verification)

- [ ] **Step 1: Prime the DB with a small DCAD sample**

Run:
```bash
cd backend && source venv/bin/activate
python -m backend.ingestion.cli dcad refresh --file tests/fixtures/dcad_parcel_sample.csv
```
Expected output: `Upserted 3 parcels ... Upserted 2 rows into properties (source=county).` (Third parcel is 90210, skipped by the SEEDED_ZIPS filter.)

- [ ] **Step 2: Verify rows landed in Supabase**

In Supabase SQL editor:
```sql
SELECT county, account_num, situs_address, situs_zip FROM county_parcels WHERE county='dallas' ORDER BY account_num;
SELECT source, external_id, address, zip_code, beds, sqft FROM properties WHERE source='county' ORDER BY external_id;
```
Expected: 3 rows in `county_parcels`, 2 rows in `properties` (only 75205 zip; the 90210 parcel is filtered out).

- [ ] **Step 3: Seed RentCast (only if a real API key is configured)**

If `RENTCAST_API_KEY` is set in `.env` and you're willing to spend ~10 of your 50 monthly requests:
```bash
cd backend && source venv/bin/activate
python -m backend.ingestion.cli rentcast seed --zips 75205
```
Expected: `market_stats: +N`, `properties: +M`, followed by budget-consumption summary.

If no key yet, skip this step and verify by inserting one hand-crafted `market_stats` row via the SQL editor to mimic RentCast output.

- [ ] **Step 4: Start the backend**

Run: `cd backend && source venv/bin/activate && uvicorn main:app --reload`
Expected: server up on `http://localhost:8000`.

- [ ] **Step 5: Start the frontend**

In another terminal: `cd frontend && npm run dev`
Expected: Vite dev server up, chat UI reachable.

- [ ] **Step 6: Ask the agent a question**

In the chat UI: "Show me the market snapshot for 75205 and any comps you have."
Expected: agent calls `fetch_market_data` and `get_comparable_sales`, returns real numbers from Supabase, map markers render for any properties with `location`.

- [ ] **Step 7: Verify budget accounting (only if you ran step 3)**

In Supabase:
```sql
SELECT * FROM api_budget WHERE provider='rentcast' ORDER BY period DESC LIMIT 1;
```
Expected: `requests_used` reflects the calls made in step 3 minus cache hits.

- [ ] **Step 8: Commit (docs / README notes if any)**

If any incidental fixups were made to README or notes during smoke testing:
```bash
git add -u
git commit -m "docs: notes from ingestion smoke test"
```
If nothing changed, skip this step.

---

## Self-Review Notes

**Spec coverage check:**
- Report shapes 1–3 (neighborhood / property / advisory): agent-tool wiring in Task 13 covers all three via `fetch_market_data` + `get_comparable_sales`; the Hermes advisory layer is deferred per spec's non-goals.
- Raw + normalized architecture: Task 1 (schema) + Tasks 2–11 (adapters + normalizer) + Task 13 (agent).
- MVP-forward guarantees (new provider = new adapter file only): base adapter in Task 5, source-agnostic budget/cache in Task 4, source column in Task 1.
- All open items from the spec (verifying RentCast endpoints, DCAD format, 429 handling) are surfaced in per-task "Note:" callouts.

**Placeholder scan:** no TBDs, no "add error handling" hand-waves. Every code step contains the actual code. Endpoint URLs are best-current-knowledge and are called out for verification in Tasks 6 and 7.

**Type / naming consistency:**
- `SourceAdapter.provider_name` (base) matches usage in adapters.
- `db.get_or_create_budget_row(provider, period, monthly_limit)` signature is consistent between Task 3 (definition) and Task 4 (call site).
- `db.upsert_property` / `upsert_market_stat` / `upsert_county_parcel` / `upsert_enrichment` all defined in Task 3, called in Tasks 11–13.
- `hash_params` / `first_of_month_utc` defined and used in Task 4.
- Property row shape (source, external_id, address, city, zip_code, location, beds, baths, sqft, ...) consistent between DCAD adapter (Task 7), RentCast adapter (Task 6), normalizer (Task 11), and agent tools (Task 13).
- `market_stats` row shape matches the existing `001_initial_schema.sql` columns.
