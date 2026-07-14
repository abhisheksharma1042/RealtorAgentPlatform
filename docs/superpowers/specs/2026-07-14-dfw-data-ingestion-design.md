# DFW Real Estate Data Ingestion — Design

**Status:** Approved for planning
**Date:** 2026-07-14
**Scope:** POC, built MVP-forward (no provider-specific or county-specific lock-in)

## Purpose

Replace the hardcoded mock dictionaries in `backend/agent/tools.py` with a real
data pipeline that populates Supabase from two anchor sources — RentCast (paid
API, tight budget) and Dallas Central Appraisal District (DCAD, free bulk
export) — enriched with free federal/city datasets. Deliver a POC that can
answer neighborhood-snapshot, property-deep-dive, and buyer/seller-advisory
questions across 4–5 hand-picked Dallas County zip codes, without repainting
the schema when we add TAD/CCAD/DALCAD counties, ATTOM data, or MLS/RESO
access at MVP stage.

## Non-goals

- Hermes learning-agent memory layer (separate spec).
- Auth / per-user data scoping (separate spec).
- Scheduled/automated refresh — POC runs CLI manually.
- Integrations with Tarrant/Collin/Denton appraisal districts, ATTOM, or
  MLS/RESO. Schema accommodates them; no code in this cycle.
- Active-listings freshness beyond what RentCast's cache TTL gives us.

## Report shapes the POC must serve, ranked

1. **Neighborhood snapshot** by zip code — market stats, recent comps,
   demographics, trend. Cheapest per query.
2. **Property deep-dive** by address — valuation, sold comps within radius,
   rent estimate, tax/assessment history, flood risk, walkability.
3. **Buyer/seller advisory search** — natural-language scenario mapped to
   matching listings with pricing commentary.

Caching strategy has to serve both pre-seeded demo queries and lazy on-demand
lookups against arbitrary addresses.

## Architecture

Three-layer pipeline into Supabase:

```
┌─────────────────────── Sources ────────────────────────┐
│ DCAD parcel bulk export     (free, refreshed annually) │
│ RentCast API                (50 req/mo free tier)      │
│ Census ACS / FEMA NFHL / Walk Score (free, per-key)    │
└──────────────────────────┬─────────────────────────────┘
                           │ backend/ingestion/sources/*.py
                           ▼
┌────────────────── Raw layer (Supabase) ────────────────┐
│ county_parcels                                         │
│ api_responses                                          │
│ api_budget                                             │
│ enrichment_cache                                       │
└──────────────────────────┬─────────────────────────────┘
                           │ backend/ingestion/normalize.py
                           ▼
┌────────── Normalized layer (existing tables) ──────────┐
│ properties         (altered)                           │
│ market_stats       (unchanged)                         │
└──────────────────────────┬─────────────────────────────┘
                           │ backend/db/client.py (already wired)
                           ▼
                     Agent tools (unchanged signatures)
```

**Key invariants:**

- Adding a new API provider is one new file in `sources/` + one new value
  in the `provider` column. No schema change, no agent-tool change.
- Adding a new county appraisal district is one new file in `sources/` +
  one new value in the `county` column. No schema change.
- All API calls flow through one `with_budget(provider)` context. Rate
  limiting is a property of the pipeline, not of any single adapter.
- The agent tools never call APIs directly — they read from the normalized
  layer, and the normalized layer is populated by ingestion runs. On-demand
  lazy fetch is a fallback wired inside the tools when a normalized row is
  missing and budget permits.

## Schema

### New raw-layer tables

```sql
CREATE TABLE county_parcels (
  county            VARCHAR(20)  NOT NULL,     -- 'dallas' now; extensible
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
CREATE INDEX idx_county_parcels_zip     ON county_parcels(situs_zip);
CREATE INDEX idx_county_parcels_address ON county_parcels
  USING GIN(to_tsvector('english', situs_address));
CREATE INDEX idx_county_parcels_loc     ON county_parcels USING GIST(location);

CREATE TABLE api_responses (
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
CREATE INDEX idx_api_responses_provider_endpoint ON api_responses(provider, endpoint);
CREATE INDEX idx_api_responses_expires           ON api_responses(expires_at);

CREATE TABLE api_budget (
  provider       VARCHAR(30)  NOT NULL,
  period         DATE         NOT NULL,   -- first of month, UTC
  requests_used  INTEGER      DEFAULT 0,
  monthly_limit  INTEGER      NOT NULL,
  updated_at     TIMESTAMPTZ  DEFAULT NOW(),
  PRIMARY KEY (provider, period)
);

CREATE TABLE enrichment_cache (
  source     VARCHAR(30)  NOT NULL,       -- 'census_acs', 'fema_flood', 'walkscore'
  cache_key  TEXT         NOT NULL,
  data       JSONB        NOT NULL,
  fetched_at TIMESTAMPTZ  DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  PRIMARY KEY (source, cache_key)
);
```

### Modifications to existing `properties`

```sql
ALTER TABLE properties ALTER COLUMN mls_id DROP NOT NULL;
ALTER TABLE properties ADD COLUMN external_id       VARCHAR(64);
ALTER TABLE properties ADD COLUMN source            VARCHAR(30); -- 'county','rentcast','merged'
ALTER TABLE properties ADD COLUMN source_updated_at TIMESTAMPTZ;
ALTER TABLE properties ADD COLUMN last_synced_at    TIMESTAMPTZ;
CREATE UNIQUE INDEX idx_properties_source_external ON properties(source, external_id);
```

`market_stats` is unchanged — RentCast's market-stats response maps onto its
existing columns.

### One fix to `db/client.py`

`get_comparable_sales()` currently filters `.eq("status", "sold")`. County-
sourced parcel rows have `status=NULL`. Drop the status filter; rely on the
presence of `sold_price`/`sold_date` if we need to distinguish sold from
attribute-only records.

### TTL policy (applied at write time in code, not schema)

| Endpoint | TTL |
|---|---|
| RentCast markets | 30 days |
| RentCast sale-comparables / sold-listings | 90 days |
| RentCast property attributes | 365 days |
| RentCast AVM value / rent | 30 days |
| Census ACS | 365 days |
| FEMA flood | 365 days |
| Walk Score | 365 days |
| DCAD parcels | manual (per tax year) |

## Code layout

```
backend/ingestion/
  __init__.py
  config.py           # SEEDED_ZIPS, COUNTIES_ACTIVE, API_BUDGETS, TTLs
  budget.py           # with_budget(), get_or_fetch(), BudgetExhausted
  normalize.py        # raw -> properties/market_stats, dedup logic
  cli.py              # `python -m backend.ingestion.cli <source> <command>`
  sources/
    __init__.py
    base.py           # SourceAdapter abstract: fetch(), normalize()
    dcad.py
    rentcast.py
    census.py
    fema.py
    walkscore.py
```

### Config defaults (`config.py`, env-overridable)

```python
SEEDED_ZIPS      = ["75201", "75205", "75225", "75093", "75024"]
COUNTIES_ACTIVE  = ["dallas"]
API_BUDGETS      = {"rentcast": 50, "attom": None, "census": None}
TTLS = {
    ("rentcast", "markets"): timedelta(days=30),
    ("rentcast", "sale_comparables"): timedelta(days=90),
    ("rentcast", "properties"): timedelta(days=365),
    ("rentcast", "avm_value"): timedelta(days=30),
    ("rentcast", "avm_rent"): timedelta(days=30),
    ("census_acs", "*"): timedelta(days=365),
    ("fema_flood", "*"): timedelta(days=365),
    ("walkscore", "*"): timedelta(days=365),
}
```

## Ingestion flows

### DCAD flow — `python -m backend.ingestion.cli dcad refresh`

1. Download DCAD's public parcel bulk export.
2. Parse rows; geocode any missing coordinates (defer if export ships lat/lon).
3. Bulk upsert into `county_parcels` with `county='dallas'`,
   `ON CONFLICT (county, account_num) DO UPDATE`.
4. Call `normalize_seeded_zips()`: read parcels WHERE `situs_zip IN SEEDED_ZIPS`,
   upsert into `properties` with `source='county'`,
   `external_id='dallas:<account_num>'`. Attributes only — no price data
   (Texas is a non-disclosure state).

### RentCast seed flow — `python -m backend.ingestion.cli rentcast seed`

Per zip in `SEEDED_ZIPS`:
- 1 call to market-stats endpoint → writes `market_stats` rows.
- 1–2 paginated calls to sold-listings endpoint → writes `properties` rows
  with `source='rentcast'`.

Target usage: ~3 calls × 5 zips ≈ 15 upfront; ~35 reserved for on-demand.
All responses cached in `api_responses` under `provider='rentcast'`.

### RentCast on-demand flow

Triggered from `backend/agent/tools.py` when a normalized row is missing:

1. Compute `cache_key` from normalized query params.
2. `SELECT` from `api_responses`; if unexpired hit, return it.
3. Miss → `with_budget('rentcast')` → fetch → cache → normalize → return.
4. Budget exhausted → return best-effort cached data + `data_freshness_warning`.

### Enrichment flows (lazy, free)

- **Census ACS**: first time a zip is touched, pull demographics, cache by zip.
- **FEMA NFHL**: first time an address is touched, look up flood zone by
  lat/lon, cache by geohash.
- **Walk Score**: first time an address is touched, pull walk/transit/bike
  scores, cache by address.

### Normalization & dedup

`normalize.py` merges county and RentCast rows describing the same physical
property using **normalized address** (uppercase, stripped suffixes, no
punctuation) + **house number** match. When both sources describe the same
property:

- County wins for attributes (beds, baths, sqft, lot, year_built).
- RentCast wins for valuation, sold price, comps, rent estimate.
- The merged row is written with `source='merged'`; the constituent rows
  remain in the raw layer for audit.

## Budget & rate-limit strategy

Single provider-agnostic module `backend/ingestion/budget.py`:

```python
@contextmanager
def with_budget(provider: str):
    period = first_of_month_utc()
    row = get_or_create_budget_row(provider, period)
    if row.requests_used >= row.monthly_limit:
        raise BudgetExhausted(provider)
    increment_atomic(provider, period)
    try:
        yield
    except Exception:
        decrement_atomic(provider, period)
        raise

async def get_or_fetch(provider, endpoint, params, ttl, fetcher):
    key = hash_params(params)
    cached = await db.fetch_api_response(provider, endpoint, key)
    if cached and not expired(cached):
        return cached.response
    with with_budget(provider):
        response = await fetcher(params)
    await db.save_api_response(provider, endpoint, key, params, response, ttl)
    return response
```

**Behavior on exhaustion:**

- **Agent-tool path** — return cached data plus a `data_freshness_warning`
  field so the agent can tell the user the source and staleness. Never fail
  a user query if any cached data exists.
- **Seeding CLI path** — fail loudly with non-zero exit. Never silently
  over-spend.

## Agent wiring

Replace the mock functions in `backend/agent/tools.py`:

```python
from backend.db.client import db

async def fetch_market_data(zip_code, ...):
    stats = await db.get_market_stats(zip_code=zip_code, ...)
    if not stats:
        from backend.ingestion.sources.rentcast import RentCastAdapter
        stats = await RentCastAdapter().fetch_market_lazy(zip_code)
    return format_response(stats)

async def get_comparable_sales(zip_code, ...):
    return await db.get_comparable_sales(zip_code=zip_code, ...)
```

Delete `MOCK_MARKET_DATA` and `MOCK_COMPARABLE_SALES`.

## Environment variables

Additions to `backend/.env`:

```
RENTCAST_API_KEY=
CENSUS_API_KEY=
WALKSCORE_API_KEY=
# FEMA NFHL is unauthenticated
# DCAD is a public download, no key
```

## Testing

- **Unit** (per source adapter): mock HTTP with `respx` / `httpx.MockTransport`,
  feed a captured RentCast/DCAD response fixture, assert the normalized row.
- **Budget guard**: unit test that hits `with_budget('rentcast')` 51 times,
  asserts the 51st raises `BudgetExhausted` and the DB counter stops at 50.
- **Cache-first**: assert that a cache hit does not increment the budget row.
- **Integration**: `pytest` fixture that seeds a small `county_parcels` +
  `api_responses` set into a test Supabase schema, calls
  `fetch_market_data("75205")` and `get_comparable_sales(zip_code="75205")`,
  asserts response shape and values.
- **Dedup**: given one county row and one RentCast row for the same address,
  the normalizer produces exactly one `properties` row with `source='merged'`.
- **Manual smoke**: run `python -m backend.ingestion.cli dcad refresh` and
  `rentcast seed`, then chat "Show me comps in 75205 under $1.5M."

## Migrations

- `003_ingestion_schema.sql` — new tables + `ALTER TABLE properties`.
- `002_seed_sample_data.py` — mark sample-only, do not run in POC.

## MVP-forward guarantees

The following extensions should require no schema change and no agent code
change, only new files under `backend/ingestion/sources/` and rows in the
existing `provider` / `county` columns:

- Adding TAD, CCAD, or DALCAD as county sources.
- Adding ATTOM as an API provider.
- Adding Bridge Interactive / MLS/RESO as an API provider (once a design
  partner brokerage sponsors access).
- Adding new enrichment sources (school ratings, crime, transit).

## Open items to revisit before implementation

- Exact endpoint names, response shapes, and pagination behavior of
  RentCast's current API — verified during the writing-plans step against
  the live docs, not assumed here.
- DCAD's export format and refresh cadence — confirmed against the actual
  published files during the writing-plans step. Fallback if DCAD's bulk
  export is behind a form: switch to per-parcel API against DCAD's public
  search endpoint, still free but slower to ingest.
- Whether the RentCast free tier's monthly quota is enforced by RentCast
  server-side (our budget guard is a courtesy either way, but affects how
  we handle 429 responses).
