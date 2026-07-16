# Hermes Memory Layer & Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the agent ("Hermes") persistent per-user memory (pins, saved searches, skill profile), truthful data-coverage awareness, and a dynamic widget canvas frontend where tool results compose the workspace.

**Architecture:** Structured memory tables (no embeddings) loaded whole into the system prompt every turn; seven new agent tools write memory and control the canvas; a REST CRUD API backs an always-visible "Hermes Knows" panel; the frontend replaces its fixed panes with a reducer-driven widget grid keyed by content identity. Spec: `docs/superpowers/specs/2026-07-15-hermes-memory-control-center-design.md`.

**Tech Stack:** FastAPI + LangGraph + supabase-py (existing), asyncpg for migrations, httpx/respx, pytest; React 19 + react-map-gl + echarts (existing), vitest (new dev dep).

**Conventions for every task:**
- Run backend commands from the repo root: `/Users/abhishekshergill/Desktop/KevinMcrea/RealtorAgentPlatform`
- Backend python: `backend/.venv/bin/python` (uv-managed venv — never `pip`, use `uv pip` if a package is ever needed)
- Backend tests: `backend/.venv/bin/python -m pytest backend/tests/<file> -v`
- Frontend commands: run inside `frontend/`
- `backend/.env` is gitignored — never commit it. Migrations require explicit user approval before applying.
- Single-user constant: `HERMES_USER_ID = "00000000-0000-0000-0000-000000000001"`

---

## File Structure

**Backend — create:**
- `backend/migrations/007_hermes_memory.sql` — memory tables + `data_coverage` view
- `backend/hermes/__init__.py` — `HERMES_USER_ID` constant
- `backend/hermes/memory.py` — per-turn memory/coverage prompt block builder
- `backend/agent/memory_tools.py` — 7 Hermes tools + their JSON schemas
- `backend/api/memory.py` — REST CRUD for the Hermes Knows panel + `/api/coverage`
- `backend/ingestion/boundaries.py` — Census TIGERweb ZCTA polygon fetcher
- Tests: `backend/tests/test_db_memory.py`, `test_hermes_memory.py`, `test_memory_tools.py`, `test_memory_api.py`, `test_boundaries.py`

**Backend — modify:**
- `backend/db/client.py` — memory/coverage db methods; `find_property_by_address`; add `zip_code` to `get_comparable_sales` result
- `backend/agent/tools.py` — register memory tools
- `backend/agent/prompts.py` — memory, coverage, and teaching rules
- `backend/agent/graph.py` — load memory block once per request, inject into system prompt
- `backend/main.py` — mount the memory router
- `backend/ingestion/cli.py` — `boundaries fetch` subcommand

**Frontend — create:**
- `frontend/src/widgets/types.ts`, `widgetReducer.ts`, `toolResultToWidgets.ts` (+ `.test.ts` for both logic files)
- `frontend/src/lib/memoryApi.ts` — fetch helpers for the CRUD endpoints
- `frontend/src/components/canvas/WidgetFrame.tsx`, `WidgetCanvas.tsx`
- `frontend/src/components/canvas/MapWidget.tsx`, `CompsTableWidget.tsx`, `TrendChartWidget.tsx`, `PropertyCardWidget.tsx`, `CoverageMapWidget.tsx`
- `frontend/src/components/hermes/HermesKnowsPanel.tsx`

**Frontend — modify:**
- `frontend/src/App.tsx` — widget reducer wiring, header toggles, drawer
- `frontend/src/components/chat/ChatPanel.tsx` — full-message display, injected messages
- `frontend/package.json` — vitest
- Delete: `frontend/src/components/output/OutputPanel.tsx` and `frontend/src/components/map/FiltersAndMapPanel.tsx` (their guts move into widgets)

---

### Task 1: Migration 007 — memory tables + data_coverage view

**Files:**
- Create: `backend/migrations/007_hermes_memory.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Migration 007: Hermes memory layer.
-- pins / saved searches / skill profile all carry user_id so the MVP
-- Supabase Auth flip is a config change, not a migration.
-- data_coverage is a VIEW so coverage claims are always live DB truth.

BEGIN;

CREATE TABLE IF NOT EXISTS pinned_properties (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  note        TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, property_id)
);
CREATE INDEX IF NOT EXISTS idx_pinned_properties_user ON pinned_properties(user_id);

CREATE TABLE IF NOT EXISTS saved_searches (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  name        TEXT NOT NULL,
  criteria    JSONB NOT NULL,
  client_note TEXT,
  last_run_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_saved_searches_user ON saved_searches(user_id);

CREATE TABLE IF NOT EXISTS skill_profile (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL,
  concept          TEXT NOT NULL,
  level            TEXT NOT NULL CHECK (level IN ('novice', 'learning', 'familiar')),
  evidence_count   INTEGER NOT NULL DEFAULT 1,
  notes            TEXT,
  last_observed_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, concept)
);
CREATE INDEX IF NOT EXISTS idx_skill_profile_user ON skill_profile(user_id);

CREATE TABLE IF NOT EXISTS zip_boundaries (
  zip        VARCHAR(10) PRIMARY KEY,
  boundary   JSONB NOT NULL,   -- GeoJSON Feature from Census TIGERweb ZCTA
  fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE VIEW data_coverage AS
SELECT
  cp.county,
  cp.situs_zip                              AS zip,
  COUNT(*)::int                             AS parcel_count,
  COUNT(cp.location)::int                   AS geocoded_count,
  MAX(cp.tax_year)                          AS appraisal_year,
  (SELECT COUNT(*)::int FROM properties p
     WHERE p.zip_code = cp.situs_zip AND p.sold_price IS NOT NULL)      AS sold_listing_count,
  (SELECT MIN(ms.period) FROM market_stats ms
     WHERE ms.zip_code = cp.situs_zip)                                  AS stats_from,
  (SELECT MAX(ms.period) FROM market_stats ms
     WHERE ms.zip_code = cp.situs_zip)                                  AS stats_to
FROM county_parcels cp
WHERE cp.situs_zip IS NOT NULL
GROUP BY cp.county, cp.situs_zip;

COMMIT;
```

- [ ] **Step 2: Ask the user to approve, then apply**

Migrations require explicit user approval. Then:

Run: `backend/.venv/bin/python -m backend.migrations.apply backend/migrations/007_hermes_memory.sql`
Expected: the runner's success output with no error.

- [ ] **Step 3: Verify the view returns live truth**

Run:
```bash
backend/.venv/bin/python - <<'EOF'
import asyncio, os, asyncpg
from dotenv import load_dotenv
load_dotenv("backend/.env")
async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch("SELECT * FROM data_coverage ORDER BY zip")
    for r in rows:
        print(dict(r))
    await conn.close()
asyncio.run(main())
EOF
```
Expected: 5 rows (75201, 75204, 75205, 75225, 75248), county `dallas`, parcel_count summing to ~41,292, non-null stats_from/stats_to for zips seeded via RentCast.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/007_hermes_memory.sql
git commit -m "feat(hermes): migration 007 - memory tables + data_coverage view"
```

---

### Task 2: Hermes package + db client memory methods

**Files:**
- Create: `backend/hermes/__init__.py`
- Modify: `backend/db/client.py` (add methods to `SupabaseDB`, before the `_LazyDB` class at line ~430; add `import re, uuid as uuid_mod` to the imports at the top)
- Test: `backend/tests/test_db_memory.py`

- [ ] **Step 1: Create the hermes package**

```python
# backend/hermes/__init__.py
"""Hermes: the agent memory + orchestration layer."""

# Fixed single-user id for the POC. At MVP, Supabase Auth user UUIDs replace
# this constant - the schema already carries user_id everywhere.
HERMES_USER_ID = "00000000-0000-0000-0000-000000000001"
```

- [ ] **Step 2: Write failing integration tests**

These follow the live-Supabase pattern of `test_db_client_extensions.py` (conftest loads `backend/.env`). Each test cleans up after itself.

```python
# backend/tests/test_db_memory.py
"""Integration tests for Hermes memory db methods (live Supabase, migration 007)."""
import pytest

TEST_USER = "00000000-0000-0000-0000-000000009999"


@pytest.mark.asyncio
async def test_pin_roundtrip(db):
    prop = db.client.table("properties").select("id, address").limit(1).execute().data[0]
    try:
        pin = await db.upsert_pin(TEST_USER, prop["id"], note="integration test")
        assert pin["property_id"] == prop["id"]
        pins = await db.list_pins(TEST_USER)
        assert any(p["property_id"] == prop["id"] for p in pins)
        # joined property payload present for display
        joined = next(p for p in pins if p["property_id"] == prop["id"])
        assert joined["properties"]["address"] == prop["address"]
    finally:
        assert await db.delete_pin(TEST_USER, prop["id"]) is True
    assert all(p["property_id"] != prop["id"] for p in await db.list_pins(TEST_USER))


@pytest.mark.asyncio
async def test_saved_search_roundtrip(db):
    try:
        row = await db.upsert_saved_search(
            TEST_USER, "itest-johnsons",
            {"zip_code": "75248", "beds_min": 3, "price_max": 800000},
            client_note="integration",
        )
        assert row["name"] == "itest-johnsons"
        fetched = await db.get_saved_search(TEST_USER, "itest-johnsons")
        assert fetched["criteria"]["zip_code"] == "75248"
        await db.touch_saved_search(TEST_USER, "itest-johnsons")
        assert (await db.get_saved_search(TEST_USER, "itest-johnsons"))["last_run_at"] is not None
        # upsert by name updates, not duplicates
        await db.upsert_saved_search(TEST_USER, "itest-johnsons", {"zip_code": "75205"})
        rows = [s for s in await db.list_saved_searches(TEST_USER) if s["name"] == "itest-johnsons"]
        assert len(rows) == 1 and rows[0]["criteria"]["zip_code"] == "75205"
    finally:
        assert await db.delete_saved_search(TEST_USER, "itest-johnsons") is True


@pytest.mark.asyncio
async def test_skill_evidence_and_familiar_guard(db):
    try:
        first = await db.upsert_skill(TEST_USER, "itest_dom", "novice", note="asked what DOM means")
        assert first["evidence_count"] == 1 and first["level"] == "novice"
        # One observation never jumps straight to familiar
        second = await db.upsert_skill(TEST_USER, "itest_dom", "familiar")
        assert second["evidence_count"] == 2 and second["level"] == "learning"
        third = await db.upsert_skill(TEST_USER, "itest_dom", "familiar")
        assert third["evidence_count"] == 3 and third["level"] == "familiar"
        # User correction via set_skill_level sticks
        corrected = await db.set_skill_level(TEST_USER, "itest_dom", "novice")
        assert corrected["level"] == "novice"
    finally:
        assert await db.delete_skill(TEST_USER, "itest_dom") is True


@pytest.mark.asyncio
async def test_data_coverage_and_boundaries(db):
    rows = await db.get_data_coverage()
    assert len(rows) >= 5
    zips = {r["zip"] for r in rows}
    assert {"75201", "75204", "75205", "75225", "75248"} <= zips
    assert all(r["parcel_count"] > 0 for r in rows)
    # boundaries table exists (may be empty until Task 3's CLI runs)
    boundaries = await db.get_zip_boundaries()
    assert isinstance(boundaries, list)


@pytest.mark.asyncio
async def test_find_property_by_address(db):
    sample = db.client.table("properties").select("id, address").limit(1).execute().data[0]
    matches = await db.find_property_by_address(sample["address"])
    assert any(m["id"] == sample["id"] for m in matches)
    # UUID fast-path
    by_id = await db.find_property_by_address(sample["id"])
    assert len(by_id) == 1 and by_id[0]["id"] == sample["id"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_db_memory.py -v`
Expected: FAIL / ERROR with `AttributeError: 'SupabaseDB' object has no attribute 'upsert_pin'` (and siblings).

- [ ] **Step 4: Implement the db methods**

At the top of `backend/db/client.py` add to the imports:

```python
import re
import uuid as uuid_mod
```

Inside `class SupabaseDB`, after the existing budget/enrichment methods and before `_LazyDB`:

```python
    # ------------------------------------------------------------------
    # Hermes memory (migration 007)
    # ------------------------------------------------------------------

    async def list_pins(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("pinned_properties")
            .select("*, properties(id, address, city, zip_code, beds, baths, sqft, "
                    "year_built, appraised_value, sold_price, price, lat, lon, source)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data

    async def upsert_pin(
        self, user_id: str, property_id: str, note: Optional[str] = None
    ) -> Dict[str, Any]:
        response = (
            self.client.table("pinned_properties")
            .upsert(
                {"user_id": user_id, "property_id": property_id, "note": note},
                on_conflict="user_id,property_id",
            )
            .execute()
        )
        return response.data[0]

    async def delete_pin(self, user_id: str, property_id: str) -> bool:
        response = (
            self.client.table("pinned_properties")
            .delete()
            .eq("user_id", user_id)
            .eq("property_id", property_id)
            .execute()
        )
        return len(response.data) > 0

    async def list_saved_searches(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("saved_searches")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        return response.data

    async def get_saved_search(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("saved_searches")
            .select("*")
            .eq("user_id", user_id)
            .eq("name", name)
            .execute()
        )
        return response.data[0] if response.data else None

    async def upsert_saved_search(
        self,
        user_id: str,
        name: str,
        criteria: Dict[str, Any],
        client_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        response = (
            self.client.table("saved_searches")
            .upsert(
                {
                    "user_id": user_id,
                    "name": name,
                    "criteria": criteria,
                    "client_note": client_note,
                    "updated_at": datetime.now().isoformat(),
                },
                on_conflict="user_id,name",
            )
            .execute()
        )
        return response.data[0]

    async def touch_saved_search(self, user_id: str, name: str) -> None:
        (
            self.client.table("saved_searches")
            .update({"last_run_at": datetime.now().isoformat()})
            .eq("user_id", user_id)
            .eq("name", name)
            .execute()
        )

    async def delete_saved_search(self, user_id: str, name: str) -> bool:
        response = (
            self.client.table("saved_searches")
            .delete()
            .eq("user_id", user_id)
            .eq("name", name)
            .execute()
        )
        return len(response.data) > 0

    async def list_skills(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("skill_profile")
            .select("*")
            .eq("user_id", user_id)
            .order("concept")
            .execute()
        )
        return response.data

    async def upsert_skill(
        self, user_id: str, concept: str, level: str, note: Optional[str] = None
    ) -> Dict[str, Any]:
        """Agent observation: increments evidence; one observation never jumps
        straight to 'familiar' (needs >= 3 observations unless already there)."""
        existing = (
            self.client.table("skill_profile")
            .select("*")
            .eq("user_id", user_id)
            .eq("concept", concept)
            .execute()
        ).data
        evidence = (existing[0]["evidence_count"] + 1) if existing else 1
        prev_level = existing[0]["level"] if existing else None
        if level == "familiar" and prev_level != "familiar" and evidence < 3:
            level = "learning"
        response = (
            self.client.table("skill_profile")
            .upsert(
                {
                    "user_id": user_id,
                    "concept": concept,
                    "level": level,
                    "evidence_count": evidence,
                    "notes": note,
                    "last_observed_at": datetime.now().isoformat(),
                },
                on_conflict="user_id,concept",
            )
            .execute()
        )
        return response.data[0]

    async def set_skill_level(self, user_id: str, concept: str, level: str) -> Dict[str, Any]:
        """User correction from the panel: sets level directly, no evidence math."""
        response = (
            self.client.table("skill_profile")
            .upsert(
                {"user_id": user_id, "concept": concept, "level": level,
                 "notes": "set by user"},
                on_conflict="user_id,concept",
            )
            .execute()
        )
        return response.data[0]

    async def delete_skill(self, user_id: str, concept: str) -> bool:
        response = (
            self.client.table("skill_profile")
            .delete()
            .eq("user_id", user_id)
            .eq("concept", concept)
            .execute()
        )
        return len(response.data) > 0

    async def get_data_coverage(self) -> List[Dict[str, Any]]:
        response = self.client.table("data_coverage").select("*").execute()
        return response.data

    async def get_zip_boundaries(self) -> List[Dict[str, Any]]:
        response = self.client.table("zip_boundaries").select("*").execute()
        return response.data

    async def upsert_zip_boundary(self, zip_code: str, boundary: Dict[str, Any]) -> None:
        (
            self.client.table("zip_boundaries")
            .upsert({"zip": zip_code, "boundary": boundary}, on_conflict="zip")
            .execute()
        )

    async def find_property_by_address(
        self, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Resolve a pin target. UUID fast-path, else normalized ILIKE match."""
        try:
            uuid_mod.UUID(query)
            response = (
                self.client.table("properties").select("*").eq("id", query).execute()
            )
            return response.data
        except (ValueError, AttributeError, TypeError):
            pass
        normalized = re.sub(r"[.,#]", "", (query or "").upper())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return []
        response = (
            self.client.table("properties")
            .select("*")
            .ilike("address", f"%{normalized}%")
            .limit(limit)
            .execute()
        )
        return response.data
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_db_memory.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/hermes/__init__.py backend/db/client.py backend/tests/test_db_memory.py
git commit -m "feat(hermes): memory db methods - pins, saved searches, skill profile, coverage"
```

---

### Task 3: Zip boundary fetcher (Census TIGERweb) + CLI

**Files:**
- Create: `backend/ingestion/boundaries.py`
- Modify: `backend/ingestion/cli.py`
- Test: `backend/tests/test_boundaries.py`

- [ ] **Step 1: Write the failing test**

Uses the `mock_http` respx fixture from `conftest.py`. IMPORTANT: match with `router.route(host=...)` — `url__startswith` silently fails to match in this codebase's respx version.

```python
# backend/tests/test_boundaries.py
import httpx
import pytest

from backend.ingestion import boundaries


FAKE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"ZCTA5": "75205"},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[-96.8, 32.8], [-96.79, 32.8], [-96.79, 32.84], [-96.8, 32.8]]]},
        }
    ],
}


@pytest.mark.asyncio
async def test_fetch_boundary_returns_feature(mock_http):
    mock_http.route(host="tigerweb.geo.census.gov").mock(
        return_value=httpx.Response(200, json=FAKE_GEOJSON)
    )
    feature = await boundaries.fetch_boundary("75205")
    assert feature["properties"]["ZCTA5"] == "75205"
    assert feature["geometry"]["type"] == "Polygon"


@pytest.mark.asyncio
async def test_fetch_boundary_no_match_returns_none(mock_http):
    mock_http.route(host="tigerweb.geo.census.gov").mock(
        return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": []})
    )
    assert await boundaries.fetch_boundary("00000") is None


@pytest.mark.asyncio
async def test_backfill_boundaries_upserts(mock_http, monkeypatch):
    mock_http.route(host="tigerweb.geo.census.gov").mock(
        return_value=httpx.Response(200, json=FAKE_GEOJSON)
    )
    saved = []

    class FakeDB:
        async def upsert_zip_boundary(self, zip_code, boundary):
            saved.append((zip_code, boundary))

    monkeypatch.setattr(boundaries, "db", FakeDB())
    count = await boundaries.backfill_boundaries(["75205", "75201"])
    assert count == 2
    assert saved[0][0] == "75205"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_boundaries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.ingestion.boundaries'`.

- [ ] **Step 3: Implement**

```python
# backend/ingestion/boundaries.py
"""Fetch ZCTA boundary polygons from Census TIGERweb (free, no key).

Stored once per seeded zip in zip_boundaries; the coverage_map widget
renders them. TIGERweb layer note: layer 4 of PUMA_TAD_TAZ_UGA_ZCTA is
'2020 Census ZIP Code Tabulation Areas'. If a live run returns no
features, list layers at .../MapServer?f=json and update the layer id.
"""
from typing import Any, Optional

import httpx

from backend.db.client import db

TIGERWEB_ZCTA_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "PUMA_TAD_TAZ_UGA_ZCTA/MapServer/4/query"
)


async def fetch_boundary(zip_code: str) -> Optional[dict[str, Any]]:
    """Return the GeoJSON Feature for one ZCTA, or None if not found."""
    params = {
        "where": f"ZCTA5='{zip_code}'",
        "outFields": "ZCTA5",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(TIGERWEB_ZCTA_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    features = data.get("features") or []
    if not features:
        return None
    return features[0]


async def backfill_boundaries(zips: list[str]) -> int:
    """Fetch + upsert boundaries for the given zips. Returns count stored."""
    count = 0
    for zip_code in zips:
        feature = await fetch_boundary(zip_code)
        if feature is None:
            print(f"  {zip_code}: no ZCTA boundary found")
            continue
        await db.upsert_zip_boundary(zip_code, feature)
        count += 1
        print(f"  {zip_code}: boundary stored")
    return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_boundaries.py -v`
Expected: 3 passed.

- [ ] **Step 5: Add the CLI subcommand**

In `backend/ingestion/cli.py`:

Add import (with the other ingestion imports):
```python
from backend.ingestion import boundaries  # noqa: E402
```

Add the handler (after `rentcast_seed`):
```python
async def boundaries_fetch(args: argparse.Namespace) -> int:
    zips = args.zips.split(",") if args.zips else config.SEEDED_ZIPS
    print(f"Fetching ZCTA boundaries for {zips}...")
    n = await boundaries.backfill_boundaries(zips)
    print(f"Stored {n}/{len(zips)} boundaries.")
    return 0
```

In `build_parser()` (after the `rent` block):
```python
    bnd = sub.add_parser("boundaries", help="Census ZCTA boundary polygons")
    bnd_sub = bnd.add_subparsers(dest="command", required=True)
    bnd_fetch = bnd_sub.add_parser("fetch", help="Fetch + store boundaries for zips")
    bnd_fetch.add_argument("--zips", help="Comma-separated zip codes (default: SEEDED_ZIPS)")
```

In `_dispatch()` (before the unknown-command fallthrough):
```python
    if args.source == "boundaries" and args.command == "fetch":
        return await boundaries_fetch(args)
```

- [ ] **Step 6: Run the CLI live**

Run: `backend/.venv/bin/python -m backend.ingestion.cli boundaries fetch`
Expected: `Stored 5/5 boundaries.` If 0 stored, the layer id drifted — fetch `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer?f=json`, find the layer named like "2020 Census ZIP Code Tabulation Areas", update `TIGERWEB_ZCTA_URL`, rerun.

- [ ] **Step 7: Commit**

```bash
git add backend/ingestion/boundaries.py backend/ingestion/cli.py backend/tests/test_boundaries.py
git commit -m "feat(hermes): zip boundary fetcher via Census TIGERweb + CLI command"
```

---

### Task 4: `zip_code` passthrough in get_comparable_sales

The tool result currently omits `zip_code` (App.tsx already reads it and gets `undefined`); widget keys need it.

**Files:**
- Modify: `backend/db/client.py:147-157` (the `get_comparable_sales` return dict)
- Test: `backend/tests/test_db_memory.py` (append)

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_db_memory.py`)

```python
@pytest.mark.asyncio
async def test_comparable_sales_includes_zip_code(db):
    result = await db.get_comparable_sales(zip_code="75205", limit=3)
    assert result["type"] == "comparable_sales"
    assert result["zip_code"] == "75205"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_db_memory.py::test_comparable_sales_includes_zip_code -v`
Expected: FAIL with `KeyError: 'zip_code'`.

- [ ] **Step 3: Implement**

In `backend/db/client.py`, the `get_comparable_sales` return statement becomes:

```python
        return {
            "type": "comparable_sales",
            "zip_code": zip_code,
            "count": len(properties),
            "properties": properties,
            "map_markers": map_markers,
            "visualization_hint": {
                "chart_type": "scatter",
                "x_axis": "sqft",
                "y_axis": "sold_price"
            }
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_db_memory.py::test_comparable_sales_includes_zip_code -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/client.py backend/tests/test_db_memory.py
git commit -m "fix(db): include zip_code in comparable_sales result for widget keying"
```

---

### Task 5: Memory block builder

**Files:**
- Create: `backend/hermes/memory.py`
- Test: `backend/tests/test_hermes_memory.py`

- [ ] **Step 1: Write the failing tests** (unit tests — FakeDB, no live Supabase)

```python
# backend/tests/test_hermes_memory.py
import pytest

from backend.hermes import memory


class FakeDB:
    def __init__(self, pins=None, searches=None, skills=None, coverage=None, fail=False):
        self._pins = pins or []
        self._searches = searches or []
        self._skills = skills or []
        self._coverage = coverage if coverage is not None else [
            {"county": "dallas", "zip": "75205", "parcel_count": 5000,
             "appraisal_year": 2025, "geocoded_count": 5000,
             "sold_listing_count": 100, "stats_from": "2021-07-01", "stats_to": "2026-06-01"},
        ]
        self._fail = fail

    async def list_pins(self, user_id):
        if self._fail:
            raise RuntimeError("db down")
        return self._pins

    async def list_saved_searches(self, user_id):
        return self._searches

    async def list_skills(self, user_id):
        return self._skills

    async def get_data_coverage(self):
        return self._coverage


@pytest.mark.asyncio
async def test_block_renders_all_sections(monkeypatch):
    monkeypatch.setattr(memory, "db", FakeDB(
        pins=[{"note": "clients liked it",
               "properties": {"address": "4024 DRUID LN", "zip_code": "75205"}}],
        searches=[{"name": "Johnsons",
                   "criteria": {"zip_code": "75248", "beds_min": 3, "price_max": 800000},
                   "client_note": "first-time buyers"}],
        skills=[{"concept": "dom", "level": "novice"},
                {"concept": "comps", "level": "familiar"}],
    ))
    block = await memory.build_memory_block()
    assert "Johnsons" in block and "75248" in block
    assert "4024 DRUID LN" in block and "clients liked it" in block
    assert "dom" in block and "comps" in block
    assert "75205" in block  # coverage line
    assert "non-disclosure" in block


@pytest.mark.asyncio
async def test_empty_memory_still_has_coverage(monkeypatch):
    monkeypatch.setattr(memory, "db", FakeDB())
    block = await memory.build_memory_block()
    assert "Saved searches" not in block
    assert "Pinned" not in block
    assert "skill profile" not in block
    assert "75205" in block  # coverage always present


@pytest.mark.asyncio
async def test_db_failure_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(memory, "db", FakeDB(fail=True))
    block = await memory.build_memory_block()
    assert "Memory unavailable" in block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_hermes_memory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.hermes.memory'`.

- [ ] **Step 3: Implement**

```python
# backend/hermes/memory.py
"""Per-turn memory + coverage block injected into the system prompt.

All memory loads whole every turn - it is dozens of rows for a single
user, so there is no retrieval step and behavior is deterministic. The
scale-up path (episodic user_memory + pgvector) is additive and touches
none of this.
"""
import logging

from backend.db.client import db
from backend.hermes import HERMES_USER_ID

logger = logging.getLogger(__name__)


async def build_memory_block(user_id: str = HERMES_USER_ID) -> str:
    try:
        pins = await db.list_pins(user_id)
        searches = await db.list_saved_searches(user_id)
        skills = await db.list_skills(user_id)
        coverage = await db.get_data_coverage()
    except Exception:
        logger.warning("Hermes memory load failed; running without memory", exc_info=True)
        return (
            "\n\n[Memory unavailable this turn - do not reference pins, saved "
            "searches, or the user's skill profile.]"
        )

    lines: list[str] = [
        "", "",
        "# Hermes context (loaded from memory - trust this over inference)",
    ]

    if searches:
        lines.append("## Saved searches (rerun with run_saved_search)")
        for s in searches:
            crit = ", ".join(f"{k}={v}" for k, v in (s.get("criteria") or {}).items())
            note = f" - client note: {s['client_note']}" if s.get("client_note") else ""
            lines.append(f'- "{s["name"]}": {crit}{note}')

    if pins:
        lines.append("## Pinned properties")
        for p in pins:
            prop = p.get("properties") or {}
            note = f' - note: "{p["note"]}"' if p.get("note") else ""
            lines.append(f"- {prop.get('address')} ({prop.get('zip_code')}){note}")

    if skills:
        plain = [s["concept"] for s in skills if s["level"] in ("novice", "learning")]
        terse = [s["concept"] for s in skills if s["level"] == "familiar"]
        lines.append("## User skill profile (user-corrected levels are authoritative)")
        if plain:
            lines.append(f"- Explain plainly on first use: {', '.join(plain)}")
        if terse:
            lines.append(f"- Familiar - do NOT re-explain: {', '.join(terse)}")

    lines.append("## Data coverage (hard bounds - never claim data outside this)")
    if coverage:
        counties = sorted({c["county"] for c in coverage if c.get("county")})
        zips = sorted({c["zip"] for c in coverage if c.get("zip")})
        total = sum(c.get("parcel_count") or 0 for c in coverage)
        year = max((c.get("appraisal_year") or 0) for c in coverage)
        lines.append(
            f"- Counties: {', '.join(counties)} | Zips: {', '.join(zips)} | "
            f"{total:,} parcels | {year} appraisal roll"
        )
    else:
        lines.append("- No coverage rows found - treat all data claims cautiously")
    lines.append(
        "- Texas is a non-disclosure state: sold prices exist only for a small "
        "RentCast-sourced subset; DCAD appraised values are the public fallback signal."
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_hermes_memory.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/hermes/memory.py backend/tests/test_hermes_memory.py
git commit -m "feat(hermes): per-turn memory + coverage prompt block builder"
```

---

### Task 6: Memory tools

**Files:**
- Create: `backend/agent/memory_tools.py`
- Test: `backend/tests/test_memory_tools.py`

- [ ] **Step 1: Write the failing tests** (unit — FakeDB via monkeypatch)

```python
# backend/tests/test_memory_tools.py
import pytest

from backend.agent import memory_tools


class FakeDB:
    def __init__(self):
        self.pins = {}
        self.searches = {}
        self.skills = {}
        self.matches = []
        self.coverage = [{"county": "dallas", "zip": "75248", "parcel_count": 9000,
                          "appraisal_year": 2025, "geocoded_count": 9000,
                          "sold_listing_count": 50, "stats_from": None, "stats_to": None}]
        self.boundaries = [{"zip": "75248", "boundary": {"type": "Feature"}}]
        self.comps_calls = []

    async def find_property_by_address(self, query, limit=5):
        return self.matches

    async def upsert_pin(self, user_id, property_id, note=None):
        self.pins[property_id] = note
        return {"property_id": property_id, "note": note}

    async def delete_pin(self, user_id, property_id):
        return self.pins.pop(property_id, "absent") != "absent"

    async def get_saved_search(self, user_id, name):
        return self.searches.get(name)

    async def list_saved_searches(self, user_id):
        return list(self.searches.values())

    async def upsert_saved_search(self, user_id, name, criteria, client_note=None):
        row = {"name": name, "criteria": criteria, "client_note": client_note}
        self.searches[name] = row
        return row

    async def touch_saved_search(self, user_id, name):
        self.searches[name]["last_run_at"] = "now"

    async def upsert_skill(self, user_id, concept, level, note=None):
        self.skills[concept] = level
        return {"concept": concept, "level": level, "evidence_count": 1}

    async def get_data_coverage(self):
        return self.coverage

    async def get_zip_boundaries(self):
        return self.boundaries

    async def get_comparable_sales(self, **kwargs):
        self.comps_calls.append(kwargs)
        return {"type": "comparable_sales", "zip_code": kwargs.get("zip_code"),
                "count": 1, "properties": [], "map_markers": []}


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(memory_tools, "db", fake)
    return fake


@pytest.mark.asyncio
async def test_pin_property_single_match(fake_db):
    fake_db.matches = [{"id": "abc-123", "address": "4024 DRUID LN", "zip_code": "75205"}]
    result = await memory_tools.pin_property("4024 Druid Ln", note="clients liked it")
    assert result["type"] == "pin_update" and result["action"] == "pinned"
    assert fake_db.pins["abc-123"] == "clients liked it"


@pytest.mark.asyncio
async def test_pin_property_ambiguous_returns_candidates(fake_db):
    fake_db.matches = [
        {"id": "a", "address": "1 DRUID LN", "zip_code": "75205"},
        {"id": "b", "address": "2 DRUID LN", "zip_code": "75205"},
    ]
    result = await memory_tools.pin_property("Druid Ln")
    assert "error" in result and len(result["candidates"]) == 2
    assert fake_db.pins == {}  # never pin a guess


@pytest.mark.asyncio
async def test_pin_property_no_match(fake_db):
    fake_db.matches = []
    result = await memory_tools.pin_property("999 Nowhere St")
    assert "error" in result and "candidates" not in result


@pytest.mark.asyncio
async def test_save_search_warns_out_of_coverage(fake_db):
    result = await memory_tools.save_search("FortWorth", {"zip_code": "76102"})
    assert result["action"] == "saved"
    assert "76102" in result["warning"]
    ok = await memory_tools.save_search("Johnsons", {"zip_code": "75248", "beds_min": 3})
    assert ok["warning"] is None


@pytest.mark.asyncio
async def test_run_saved_search_delegates_and_touches(fake_db):
    fake_db.searches["Johnsons"] = {
        "name": "Johnsons",
        "criteria": {"zip_code": "75248", "beds_min": 3, "bogus_key": True},
    }
    result = await memory_tools.run_saved_search("Johnsons")
    assert result["type"] == "comparable_sales"
    assert result["saved_search_name"] == "Johnsons"
    assert fake_db.comps_calls == [{"zip_code": "75248", "beds_min": 3}]  # bogus_key filtered
    assert fake_db.searches["Johnsons"]["last_run_at"] == "now"


@pytest.mark.asyncio
async def test_run_saved_search_unknown_name(fake_db):
    result = await memory_tools.run_saved_search("Nope")
    assert "error" in result


@pytest.mark.asyncio
async def test_record_skill_observation_normalizes_concept(fake_db):
    result = await memory_tools.record_skill_observation("Days On Market", "novice")
    assert result["type"] == "skill_update"
    assert "days_on_market" in fake_db.skills


@pytest.mark.asyncio
async def test_dismiss_widget_shape():
    result = await memory_tools.dismiss_widget("map:75248")
    assert result == {"type": "widget_dismiss", "widget_key": "map:75248"}


@pytest.mark.asyncio
async def test_get_data_coverage_shape(fake_db):
    result = await memory_tools.get_data_coverage()
    assert result["type"] == "data_coverage"
    assert result["coverage"][0]["zip"] == "75248"
    assert result["boundaries"] == [{"type": "Feature"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_memory_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.agent.memory_tools'`.

- [ ] **Step 3: Implement**

```python
# backend/agent/memory_tools.py
"""Hermes memory tools: pins, saved searches, skill observations, canvas, coverage.

Every tool returns a dict with a 'type' key - the frontend widget reducer
maps types to widgets. Errors come back as strings for the agent to relay;
tools never raise into the graph.
"""
import re
from typing import Any, Dict, Optional

from backend.db.client import db
from backend.hermes import HERMES_USER_ID

# get_comparable_sales kwargs a saved search may carry
_SEARCH_KEYS = {
    "zip_code", "beds_min", "beds_max", "price_min", "price_max",
    "sqft_min", "sqft_max", "limit",
}


def _normalize_concept(concept: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (concept or "").lower())
    return s.strip("_")


async def pin_property(address_or_id: str, note: Optional[str] = None) -> Dict[str, Any]:
    try:
        matches = await db.find_property_by_address(address_or_id)
        if not matches:
            return {
                "type": "pin_update",
                "error": f"No property found matching '{address_or_id}'. "
                         "Ask the user to clarify the address.",
            }
        if len(matches) > 1:
            return {
                "type": "pin_update",
                "error": "Multiple properties match - ask the user which one.",
                "candidates": [
                    {"id": m["id"], "address": m["address"], "zip_code": m.get("zip_code")}
                    for m in matches
                ],
            }
        prop = matches[0]
        await db.upsert_pin(HERMES_USER_ID, prop["id"], note)
        return {"type": "pin_update", "action": "pinned", "property": prop, "note": note}
    except Exception as exc:
        return {"type": "pin_update", "error": str(exc)}


async def unpin_property(address_or_id: str) -> Dict[str, Any]:
    try:
        matches = await db.find_property_by_address(address_or_id)
        if len(matches) != 1:
            return {
                "type": "pin_update",
                "error": f"Could not uniquely resolve '{address_or_id}' "
                         f"({len(matches)} matches).",
            }
        removed = await db.delete_pin(HERMES_USER_ID, matches[0]["id"])
        if not removed:
            return {"type": "pin_update", "error": "That property was not pinned."}
        return {"type": "pin_update", "action": "unpinned", "property": matches[0]}
    except Exception as exc:
        return {"type": "pin_update", "error": str(exc)}


async def save_search(
    name: str, criteria: Dict[str, Any], client_note: Optional[str] = None
) -> Dict[str, Any]:
    try:
        coverage = await db.get_data_coverage()
        covered = {c["zip"] for c in coverage}
        warning = None
        zip_code = (criteria or {}).get("zip_code")
        if zip_code and zip_code not in covered:
            warning = (
                f"zip {zip_code} is outside current coverage "
                f"({', '.join(sorted(covered))}) - the search will return no rows"
            )
        row = await db.upsert_saved_search(HERMES_USER_ID, name, criteria, client_note)
        return {"type": "saved_search_update", "action": "saved",
                "search": row, "warning": warning}
    except Exception as exc:
        return {"type": "saved_search_update", "error": str(exc)}


async def run_saved_search(name: str) -> Dict[str, Any]:
    try:
        search = await db.get_saved_search(HERMES_USER_ID, name)
        if not search:
            names = [s["name"] for s in await db.list_saved_searches(HERMES_USER_ID)]
            return {
                "type": "saved_search_update",
                "error": f"No saved search named '{name}'. Saved searches: {names}",
            }
        kwargs = {k: v for k, v in (search.get("criteria") or {}).items()
                  if k in _SEARCH_KEYS}
        result = await db.get_comparable_sales(**kwargs)
        await db.touch_saved_search(HERMES_USER_ID, name)
        result["saved_search_name"] = name
        return result
    except Exception as exc:
        return {"type": "saved_search_update", "error": str(exc)}


async def record_skill_observation(
    concept: str, level: str, note: Optional[str] = None
) -> Dict[str, Any]:
    try:
        normalized = _normalize_concept(concept)
        if not normalized or level not in ("novice", "learning", "familiar"):
            return {"type": "skill_update",
                    "error": f"invalid concept/level: {concept!r}/{level!r}"}
        row = await db.upsert_skill(HERMES_USER_ID, normalized, level, note)
        return {"type": "skill_update", "skill": row}
    except Exception as exc:
        return {"type": "skill_update", "error": str(exc)}


async def dismiss_widget(widget_key: str) -> Dict[str, Any]:
    return {"type": "widget_dismiss", "widget_key": widget_key}


async def get_data_coverage() -> Dict[str, Any]:
    try:
        coverage = await db.get_data_coverage()
        boundaries = await db.get_zip_boundaries()
        return {
            "type": "data_coverage",
            "coverage": coverage,
            "boundaries": [b["boundary"] for b in boundaries],
            "notes": (
                "Texas is a non-disclosure state: sold prices exist only for the "
                "RentCast-sourced subset; DCAD appraised values are public."
            ),
        }
    except Exception as exc:
        return {"type": "data_coverage", "error": str(exc)}


MEMORY_TOOLS = [
    {
        "name": "pin_property",
        "description": (
            "Pin a property to the user's persistent workspace. Resolves the address "
            "first; if it is ambiguous or unmatched you get an error to relay - never guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address_or_id": {"type": "string",
                                  "description": "Street address or property UUID"},
                "note": {"type": "string",
                         "description": "Optional note, e.g. 'the Johnsons liked this one'"},
            },
            "required": ["address_or_id"],
        },
    },
    {
        "name": "unpin_property",
        "description": "Remove a pinned property from the user's workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address_or_id": {"type": "string",
                                  "description": "Street address or property UUID"},
            },
            "required": ["address_or_id"],
        },
    },
    {
        "name": "save_search",
        "description": (
            "Save/update a named search (criteria = get_comparable_sales filters). "
            "OFFER to save when the user repeats criteria - never save silently. "
            "A search named for a client ('Johnsons') acts as their profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short unique name, e.g. 'Johnsons'"},
                "criteria": {
                    "type": "object",
                    "description": "Filter keys: zip_code, beds_min, beds_max, price_min, "
                                   "price_max, sqft_min, sqft_max, limit",
                },
                "client_note": {"type": "string",
                                "description": "Optional client context"},
            },
            "required": ["name", "criteria"],
        },
    },
    {
        "name": "run_saved_search",
        "description": "Run a saved search by name and return comparable sales.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "record_skill_observation",
        "description": (
            "Record what the user knows. Call when they ask what a concept means "
            "(novice), engage with an explanation (learning), or use a term correctly "
            "unprompted (familiar). Concepts: comps, days_on_market, absorption_rate, "
            "price_per_sqft, appraised_vs_market, contingency, escrow - or others you observe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "concept": {"type": "string"},
                "level": {"type": "string", "enum": ["novice", "learning", "familiar"]},
                "note": {"type": "string", "description": "What you observed"},
            },
            "required": ["concept", "level"],
        },
    },
    {
        "name": "dismiss_widget",
        "description": (
            "Remove a stale widget from the user's canvas when the conversation moves on. "
            "Keys are content-derived: map:<zip>, table:<zip>, trend:<zip>, "
            "card:<property_id>, coverage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"widget_key": {"type": "string"}},
            "required": ["widget_key"],
        },
    },
    {
        "name": "get_data_coverage",
        "description": (
            "Return the live bounds of available data (counties, zips, parcel counts, "
            "freshness) with zip boundary polygons. Call when the user asks what data "
            "you have, or when their question falls outside coverage - show, don't apologize."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

MEMORY_TOOL_FUNCTIONS = {
    "pin_property": pin_property,
    "unpin_property": unpin_property,
    "save_search": save_search,
    "run_saved_search": run_saved_search,
    "record_skill_observation": record_skill_observation,
    "dismiss_widget": dismiss_widget,
    "get_data_coverage": get_data_coverage,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_memory_tools.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/memory_tools.py backend/tests/test_memory_tools.py
git commit -m "feat(hermes): seven memory/canvas/coverage agent tools"
```

---

### Task 7: Register tools, extend prompt, inject memory into the graph

**Files:**
- Modify: `backend/agent/tools.py` (bottom — TOOLS/TOOL_FUNCTIONS)
- Modify: `backend/agent/prompts.py` (SYSTEM_PROMPT)
- Modify: `backend/agent/graph.py` (`call_agent`, `stream_agent_response`)
- Test: `backend/tests/test_memory_tools.py` (append)

- [ ] **Step 1: Write the failing registration tests** (append to `backend/tests/test_memory_tools.py`)

```python
def test_memory_tools_registered_in_agent():
    from backend.agent.tools import TOOLS, TOOL_FUNCTIONS
    names = {t["name"] for t in TOOLS}
    expected = {"pin_property", "unpin_property", "save_search", "run_saved_search",
                "record_skill_observation", "dismiss_widget", "get_data_coverage"}
    assert expected <= names
    assert expected <= set(TOOL_FUNCTIONS)


def test_prompt_contains_teaching_and_coverage_rules():
    from backend.agent.prompts import get_system_prompt
    prompt = get_system_prompt()
    assert "record_skill_observation" in prompt
    assert "novice" in prompt
    assert "coverage" in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_memory_tools.py::test_memory_tools_registered_in_agent backend/tests/test_memory_tools.py::test_prompt_contains_teaching_and_coverage_rules -v`
Expected: FAIL (memory tool names missing from TOOLS; prompt lacks the rules).

- [ ] **Step 3: Register the tools**

At the bottom of `backend/agent/tools.py`, replace:

```python
TOOL_FUNCTIONS = {
    "fetch_market_data": fetch_market_data,
    "get_comparable_sales": get_comparable_sales,
}
```

with:

```python
from backend.agent.memory_tools import MEMORY_TOOLS, MEMORY_TOOL_FUNCTIONS

TOOLS = TOOLS + MEMORY_TOOLS

TOOL_FUNCTIONS = {
    "fetch_market_data": fetch_market_data,
    "get_comparable_sales": get_comparable_sales,
    **MEMORY_TOOL_FUNCTIONS,
}
```

- [ ] **Step 4: Rewrite `backend/agent/prompts.py`**

```python
"""System prompts for the DFW Realtor Agent (Hermes)."""

SYSTEM_PROMPT = """You are Hermes, an expert real estate assistant for the Dallas-Fort Worth (DFW) metroplex. You help novice real estate license holders run data-driven analysis - and you learn WITH each user: you remember their saved work and adapt explanations to what they already know.

## Your Tools

Data:
1. **fetch_market_data**: aggregate market statistics for a ZIP (median price, volume, DOM, trends)
2. **get_comparable_sales**: comparable properties filtered by location/attributes

Memory (persistent - survives across conversations):
3. **pin_property / unpin_property**: keep specific properties in the user's workspace
4. **save_search / run_saved_search**: named, reusable search criteria ("Johnsons", "my farm")
5. **record_skill_observation**: track which real-estate concepts the user knows

Canvas & coverage:
6. **dismiss_widget**: clear a stale widget when the conversation moves on
7. **get_data_coverage**: show exactly what data you have (zips, counts, freshness) on a map

## Memory Rules

- The "Hermes context" block appended below this prompt is your memory - trust it over inference. User-corrected skill levels are authoritative.
- OFFER to save searches when you notice repeated criteria ("You've filtered 75248 under $800K twice - want me to save this as a search?"). Never save silently.
- Pin only when asked, or offer when the user shows strong interest in a property. Never pin a guess - if address resolution is ambiguous, ask.

## Teaching Rules (learns-with-you)

- The first time a concept the user does NOT know (novice/learning in the skill profile, or never seen) appears in your answer, add ONE plain-English sentence explaining it.
- Never re-explain concepts marked familiar. Be terse with experts, patient with beginners.
- Call record_skill_observation when the user: asks what a term means (novice), engages with your explanation (learning), or uses a term correctly unprompted (familiar).

## Coverage Rules

- The coverage block below lists the ONLY data you have. Never imply data beyond it.
- If a question falls outside coverage (wrong county, unseeded zip), say so plainly, call get_data_coverage to SHOW the bounds, and offer what you can do instead.
- Texas is a non-disclosure state: sold prices exist only for a small RentCast subset. Lead with appraised values for county-sourced rows and say which you're using.

## Response Format

1. Analyze the question, call tools, interpret results clearly.
2. Always separate your final follow-up suggestion from the main analysis with the exact delimiter `---SUGGESTION---` on its own line.

Remember: you are the user's control center - compose the workspace for them, keep their memory truthful and visible, and teach as you go."""


def get_system_prompt() -> str:
    """Get the system prompt for the agent"""
    return SYSTEM_PROMPT
```

- [ ] **Step 5: Inject memory into the graph**

In `backend/agent/graph.py`:

Add import (after the existing `from agent.tools import ...`):
```python
from backend.hermes.memory import build_memory_block
```

In `call_agent`, replace:
```python
    system_message = {"role": "system", "content": get_system_prompt()}
```
with:
```python
    memory_block = state.get("context", {}).get("memory_block", "")
    system_message = {"role": "system", "content": get_system_prompt() + memory_block}
```

In `stream_agent_response`, replace:
```python
    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_message)],
        "user_query": user_message,
        "context": {},
        "tools_used": []
    }
```
with:
```python
    # Load memory once per request (not per agent-node hop) - it is small
    # and deterministic; failure degrades to a no-memory turn.
    memory_block = await build_memory_block()

    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_message)],
        "user_query": user_message,
        "context": {"memory_block": memory_block},
        "tools_used": []
    }
```

- [ ] **Step 6: Run the new tests + full backend suite**

Run: `backend/.venv/bin/python -m pytest backend/tests -v`
Expected: all pass (36 existing + new).

- [ ] **Step 7: Live smoke — agent uses memory**

Restart the backend (kill the running uvicorn, then from `backend/`: `.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000` in background), then:

```bash
curl -s -N -X POST http://localhost:8000/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message": "Save a search called Johnsons: 3 bed minimum under $800K in 75248, then run it."}' | head -50
```
Expected: SSE events include `tool_call` for `save_search` and `run_saved_search`, and a `tool_result` with `"type": "comparable_sales"` and `"saved_search_name": "Johnsons"`.

- [ ] **Step 8: Commit**

```bash
git add backend/agent/tools.py backend/agent/prompts.py backend/agent/graph.py backend/tests/test_memory_tools.py
git commit -m "feat(hermes): register memory tools, teaching/coverage prompt rules, per-turn memory injection"
```

---

### Task 8: Memory REST API

**Files:**
- Create: `backend/api/memory.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_memory_api.py`

- [ ] **Step 1: Write the failing tests** (integration — TestClient over live db)

```python
# backend/tests/test_memory_api.py
"""Integration tests for the Hermes Knows CRUD API (live Supabase)."""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
API_TEST_SEARCH = "apitest-search"
API_TEST_CONCEPT = "apitest_concept"


def test_saved_search_crud_roundtrip():
    try:
        created = client.post("/api/memory/searches", json={
            "name": API_TEST_SEARCH,
            "criteria": {"zip_code": "75205", "beds_min": 2},
            "client_note": "api test",
        })
        assert created.status_code == 200
        listed = client.get("/api/memory/searches").json()
        assert any(s["name"] == API_TEST_SEARCH for s in listed)
    finally:
        deleted = client.delete(f"/api/memory/searches/{API_TEST_SEARCH}")
        assert deleted.status_code == 200
    assert all(s["name"] != API_TEST_SEARCH
               for s in client.get("/api/memory/searches").json())


def test_skill_put_and_delete():
    try:
        put = client.put(f"/api/memory/skills/{API_TEST_CONCEPT}", json={"level": "familiar"})
        assert put.status_code == 200 and put.json()["level"] == "familiar"
        listed = client.get("/api/memory/skills").json()
        assert any(s["concept"] == API_TEST_CONCEPT for s in listed)
    finally:
        assert client.delete(f"/api/memory/skills/{API_TEST_CONCEPT}").status_code == 200


def test_pins_and_coverage_endpoints_respond():
    assert isinstance(client.get("/api/memory/pins").json(), list)
    cov = client.get("/api/coverage").json()
    assert "coverage" in cov and "boundaries" in cov
    assert any(row["zip"] == "75205" for row in cov["coverage"])


def test_delete_missing_search_404s():
    assert client.delete("/api/memory/searches/does-not-exist-xyz").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_memory_api.py -v`
Expected: FAIL with 404s (routes don't exist yet).

- [ ] **Step 3: Implement the router**

```python
# backend/api/memory.py
"""REST CRUD backing the Hermes Knows panel + coverage endpoint.

Panel actions hit these directly (no LLM round-trip); Hermes sees the
changes on the next turn's memory load.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.client import db
from backend.hermes import HERMES_USER_ID

router = APIRouter(prefix="/api", tags=["memory"])


class PinCreate(BaseModel):
    property_id: str
    note: Optional[str] = None


class SearchUpsert(BaseModel):
    name: str
    criteria: Dict[str, Any]
    client_note: Optional[str] = None


class SkillPut(BaseModel):
    level: str  # novice | learning | familiar


@router.get("/memory/pins")
async def get_pins():
    return await db.list_pins(HERMES_USER_ID)


@router.post("/memory/pins")
async def create_pin(body: PinCreate):
    return await db.upsert_pin(HERMES_USER_ID, body.property_id, body.note)


@router.delete("/memory/pins/{property_id}")
async def remove_pin(property_id: str):
    if not await db.delete_pin(HERMES_USER_ID, property_id):
        raise HTTPException(status_code=404, detail="pin not found")
    return {"deleted": property_id}


@router.get("/memory/searches")
async def get_searches():
    return await db.list_saved_searches(HERMES_USER_ID)


@router.post("/memory/searches")
async def upsert_search(body: SearchUpsert):
    return await db.upsert_saved_search(
        HERMES_USER_ID, body.name, body.criteria, body.client_note
    )


@router.delete("/memory/searches/{name}")
async def remove_search(name: str):
    if not await db.delete_saved_search(HERMES_USER_ID, name):
        raise HTTPException(status_code=404, detail="saved search not found")
    return {"deleted": name}


@router.get("/memory/skills")
async def get_skills():
    return await db.list_skills(HERMES_USER_ID)


@router.put("/memory/skills/{concept}")
async def put_skill(concept: str, body: SkillPut):
    if body.level not in ("novice", "learning", "familiar"):
        raise HTTPException(status_code=422, detail="level must be novice|learning|familiar")
    return await db.set_skill_level(HERMES_USER_ID, concept, body.level)


@router.delete("/memory/skills/{concept}")
async def remove_skill(concept: str):
    if not await db.delete_skill(HERMES_USER_ID, concept):
        raise HTTPException(status_code=404, detail="skill not found")
    return {"deleted": concept}


@router.get("/coverage")
async def get_coverage():
    coverage = await db.get_data_coverage()
    boundaries = await db.get_zip_boundaries()
    return {"coverage": coverage, "boundaries": [b["boundary"] for b in boundaries]}
```

- [ ] **Step 4: Mount the router in `backend/main.py`**

After `from api.chat import router as chat_router` add:
```python
from api.memory import router as memory_router
```
After `app.include_router(chat_router)` add:
```python
app.include_router(memory_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_memory_api.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/api/memory.py backend/main.py backend/tests/test_memory_api.py
git commit -m "feat(hermes): REST CRUD for pins, searches, skills + coverage endpoint"
```

---

### Task 9: Frontend — vitest + widget reducer + tool-result mapper

**Files:**
- Modify: `frontend/package.json` (vitest dev dep + test script)
- Create: `frontend/src/widgets/types.ts`
- Create: `frontend/src/widgets/widgetReducer.ts` + `frontend/src/widgets/widgetReducer.test.ts`
- Create: `frontend/src/widgets/toolResultToWidgets.ts` + `frontend/src/widgets/toolResultToWidgets.test.ts`

- [ ] **Step 1: Install vitest and add the script**

Run (in `frontend/`): `npm install -D vitest`
In `package.json` `"scripts"`, add: `"test": "vitest run"`

- [ ] **Step 2: Write the types**

```ts
// frontend/src/widgets/types.ts
export type WidgetType =
  | 'map'
  | 'comps_table'
  | 'trend_chart'
  | 'property_card'
  | 'coverage_map'

export interface Widget {
  key: string        // content identity: map:75248, table:75248, trend:75248, card:<id>, coverage
  type: WidgetType
  title: string
  props: any         // the raw tool result the widget body renders
  updatedAt: number
}

export type WidgetAction =
  | { type: 'upsert'; widget: Widget }
  | { type: 'dismiss'; key: string }
  | { type: 'clear' }
```

- [ ] **Step 3: Write the failing reducer tests**

```ts
// frontend/src/widgets/widgetReducer.test.ts
import { describe, it, expect } from 'vitest'
import { widgetReducer } from './widgetReducer'
import type { Widget } from './types'

const w = (key: string, updatedAt = 1): Widget =>
  ({ key, type: 'map', title: key, props: {}, updatedAt })

describe('widgetReducer', () => {
  it('appends a new widget', () => {
    const next = widgetReducer([], { type: 'upsert', widget: w('map:75248') })
    expect(next).toHaveLength(1)
  })

  it('upserts by key in place - no duplicates, position preserved', () => {
    const state = [w('map:75248'), w('table:75248')]
    const next = widgetReducer(state, { type: 'upsert', widget: w('map:75248', 2) })
    expect(next).toHaveLength(2)
    expect(next[0].updatedAt).toBe(2)
    expect(next[0].key).toBe('map:75248')
  })

  it('dismisses by key', () => {
    const state = [w('map:75248'), w('table:75248')]
    const next = widgetReducer(state, { type: 'dismiss', key: 'map:75248' })
    expect(next.map(x => x.key)).toEqual(['table:75248'])
  })

  it('dismiss of unknown key is a no-op', () => {
    const state = [w('map:75248')]
    expect(widgetReducer(state, { type: 'dismiss', key: 'nope' })).toHaveLength(1)
  })

  it('clear empties the canvas', () => {
    expect(widgetReducer([w('a'), w('b')], { type: 'clear' })).toEqual([])
  })
})
```

- [ ] **Step 4: Run tests to verify they fail**

Run (in `frontend/`): `npm run test`
Expected: FAIL — cannot resolve `./widgetReducer`.

- [ ] **Step 5: Implement the reducer**

```ts
// frontend/src/widgets/widgetReducer.ts
import type { Widget, WidgetAction } from './types'

// Pure - React StrictMode double-invokes reducers in dev; upsert-by-key
// makes that harmless (same action twice yields the same state).
export function widgetReducer(state: Widget[], action: WidgetAction): Widget[] {
  switch (action.type) {
    case 'upsert': {
      const idx = state.findIndex(w => w.key === action.widget.key)
      if (idx >= 0) return state.map((w, i) => (i === idx ? action.widget : w))
      return [...state, action.widget]
    }
    case 'dismiss':
      return state.filter(w => w.key !== action.key)
    case 'clear':
      return []
    default:
      return state
  }
}
```

- [ ] **Step 6: Write the failing mapper tests**

```ts
// frontend/src/widgets/toolResultToWidgets.test.ts
import { describe, it, expect } from 'vitest'
import { toolResultToActions } from './toolResultToWidgets'

describe('toolResultToActions', () => {
  it('comparable_sales spawns map + table keyed by zip', () => {
    const actions = toolResultToActions(
      { type: 'comparable_sales', zip_code: '75248', properties: [], map_markers: [] }, 10)
    expect(actions.map(a => a.type === 'upsert' && a.widget.key))
      .toEqual(['map:75248', 'table:75248'])
  })

  it('market_data spawns a trend widget', () => {
    const actions = toolResultToActions(
      { type: 'market_data', zip_code: '75205', history: [] }, 10)
    expect(actions).toHaveLength(1)
    expect(actions[0].type === 'upsert' && actions[0].widget.type).toBe('trend_chart')
  })

  it('market_data with error spawns nothing', () => {
    expect(toolResultToActions({ type: 'market_data', zip_code: 'x', error: 'nope' }, 1))
      .toEqual([])
  })

  it('pin_update spawns a property card; errors do not', () => {
    const ok = toolResultToActions(
      { type: 'pin_update', action: 'pinned', property: { id: 'abc', address: 'X' } }, 1)
    expect(ok[0].type === 'upsert' && ok[0].widget.key).toBe('card:abc')
    expect(toolResultToActions({ type: 'pin_update', error: 'ambiguous' }, 1)).toEqual([])
  })

  it('data_coverage spawns the coverage widget', () => {
    const actions = toolResultToActions(
      { type: 'data_coverage', coverage: [], boundaries: [] }, 1)
    expect(actions[0].type === 'upsert' && actions[0].widget.key).toBe('coverage')
  })

  it('widget_dismiss maps to a dismiss action', () => {
    expect(toolResultToActions({ type: 'widget_dismiss', widget_key: 'map:75248' }, 1))
      .toEqual([{ type: 'dismiss', key: 'map:75248' }])
  })

  it('unknown or malformed results are ignored', () => {
    expect(toolResultToActions({ type: 'something_new' }, 1)).toEqual([])
    expect(toolResultToActions(null, 1)).toEqual([])
    expect(toolResultToActions('junk', 1)).toEqual([])
  })
})
```

- [ ] **Step 7: Run tests to verify they fail**

Run (in `frontend/`): `npm run test`
Expected: reducer tests pass; mapper tests FAIL — cannot resolve `./toolResultToWidgets`.

- [ ] **Step 8: Implement the mapper**

```ts
// frontend/src/widgets/toolResultToWidgets.ts
import type { Widget, WidgetAction } from './types'

const widget = (
  key: string, type: Widget['type'], title: string, props: any, updatedAt: number,
): WidgetAction => ({ type: 'upsert', widget: { key, type, title, props, updatedAt } })

// Pure mapping: SSE tool result -> reducer actions. Unknown types are
// ignored so new backend widgets can't break an old frontend.
export function toolResultToActions(result: any, now: number): WidgetAction[] {
  if (!result || typeof result !== 'object') return []
  switch (result.type) {
    case 'comparable_sales': {
      const zip = result.zip_code ?? 'latest'
      const label = result.saved_search_name ? ` — ${result.saved_search_name}` : ''
      return [
        widget(`map:${zip}`, 'map', `Map — ${zip}${label}`, result, now),
        widget(`table:${zip}`, 'comps_table', `Comps — ${zip}${label} (${result.count ?? 0})`, result, now),
      ]
    }
    case 'market_data': {
      if (result.error) return []
      const zip = result.zip_code ?? 'latest'
      return [widget(`trend:${zip}`, 'trend_chart', `Trend — ${zip}`, result, now)]
    }
    case 'pin_update': {
      if (result.error || !result.property || result.action !== 'pinned') return []
      return [widget(
        `card:${result.property.id}`, 'property_card',
        result.property.address ?? 'Pinned property', result, now,
      )]
    }
    case 'data_coverage': {
      if (result.error) return []
      return [widget('coverage', 'coverage_map', 'Data coverage', result, now)]
    }
    case 'widget_dismiss':
      return [{ type: 'dismiss', key: result.widget_key }]
    default:
      return []
  }
}
```

- [ ] **Step 9: Run all frontend tests**

Run (in `frontend/`): `npm run test`
Expected: 12 passed (5 reducer + 7 mapper).

- [ ] **Step 10: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/widgets/
git commit -m "feat(canvas): widget reducer + tool-result mapper with vitest coverage"
```

---

### Task 10: Frontend — memory API client + WidgetFrame + WidgetCanvas

**Files:**
- Create: `frontend/src/lib/memoryApi.ts`
- Create: `frontend/src/components/canvas/WidgetFrame.tsx`
- Create: `frontend/src/components/canvas/WidgetCanvas.tsx`
- Create: placeholder widget bodies (replaced in Tasks 11–12)

(No tests beyond the compile check here — these are wiring, not logic.)

- [ ] **Step 1: Memory API client**

```ts
// frontend/src/lib/memoryApi.ts
const BASE = 'http://localhost:8000/api'

async function req(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${path}: ${res.status}`)
  return res.json()
}

export const getPins = () => req('/memory/pins')
export const createPin = (propertyId: string, note?: string) =>
  req('/memory/pins', { method: 'POST', body: JSON.stringify({ property_id: propertyId, note }) })
export const deletePin = (propertyId: string) =>
  req(`/memory/pins/${propertyId}`, { method: 'DELETE' })

export const getSearches = () => req('/memory/searches')
export const deleteSearch = (name: string) =>
  req(`/memory/searches/${encodeURIComponent(name)}`, { method: 'DELETE' })

export const getSkills = () => req('/memory/skills')
export const setSkillLevel = (concept: string, level: string) =>
  req(`/memory/skills/${encodeURIComponent(concept)}`, { method: 'PUT', body: JSON.stringify({ level }) })
export const deleteSkill = (concept: string) =>
  req(`/memory/skills/${encodeURIComponent(concept)}`, { method: 'DELETE' })

export const getCoverage = () => req('/coverage')
```

- [ ] **Step 2: WidgetFrame**

```tsx
// frontend/src/components/canvas/WidgetFrame.tsx
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

interface WidgetFrameProps {
  title: string
  onClose: () => void
  children: ReactNode
}

export default function WidgetFrame({ title, onClose, children }: WidgetFrameProps) {
  return (
    <div className="bg-card border border-border rounded-xl shadow-sm flex flex-col overflow-hidden min-h-[280px]">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-secondary/10 flex-shrink-0">
        <span className="text-sm font-semibold text-card-foreground truncate">{title}</span>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors"
          aria-label={`Close ${title}`}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">{children}</div>
    </div>
  )
}
```

- [ ] **Step 3: WidgetCanvas**

```tsx
// frontend/src/components/canvas/WidgetCanvas.tsx
import type { Dispatch } from 'react'
import type { Widget, WidgetAction } from '../../widgets/types'
import WidgetFrame from './WidgetFrame'
import MapWidget from './MapWidget'
import CompsTableWidget from './CompsTableWidget'
import TrendChartWidget from './TrendChartWidget'
import PropertyCardWidget from './PropertyCardWidget'
import CoverageMapWidget from './CoverageMapWidget'
import { LayoutGrid } from 'lucide-react'

interface WidgetCanvasProps {
  widgets: Widget[]
  dispatch: Dispatch<WidgetAction>
  onMemoryChange: () => void
}

function WidgetBody({ w, onMemoryChange }: { w: Widget; onMemoryChange: () => void }) {
  switch (w.type) {
    case 'map': return <MapWidget result={w.props} />
    case 'comps_table': return <CompsTableWidget result={w.props} onMemoryChange={onMemoryChange} />
    case 'trend_chart': return <TrendChartWidget result={w.props} />
    case 'property_card': return <PropertyCardWidget result={w.props} />
    case 'coverage_map': return <CoverageMapWidget result={w.props} />
    default:
      return <pre className="text-xs p-3 overflow-auto">{JSON.stringify(w.props, null, 2)}</pre>
  }
}

export default function WidgetCanvas({ widgets, dispatch, onMemoryChange }: WidgetCanvasProps) {
  if (widgets.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <div className="text-center space-y-3">
          <LayoutGrid className="h-12 w-12 text-muted-foreground mx-auto" />
          <p className="text-sm text-muted-foreground max-w-xs">
            Ask Hermes a question - analysis widgets will appear here.
          </p>
        </div>
      </div>
    )
  }
  return (
    <div className="h-full overflow-y-auto p-3 bg-background">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {widgets.map(w => (
          <WidgetFrame key={w.key} title={w.title}
                       onClose={() => dispatch({ type: 'dismiss', key: w.key })}>
            <WidgetBody w={w} onMemoryChange={onMemoryChange} />
          </WidgetFrame>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create placeholder widget bodies so the build compiles** (each is fully replaced in Tasks 11–12; placeholders render raw JSON)

Create each of `MapWidget.tsx`, `TrendChartWidget.tsx`, `PropertyCardWidget.tsx`, `CoverageMapWidget.tsx` in `frontend/src/components/canvas/` with this shape (rename the component per file):

```tsx
// placeholder - replaced in Task 11/12
export default function MapWidget({ result }: { result: any }) {
  return <pre className="text-xs p-3 overflow-auto">{JSON.stringify(result, null, 2)}</pre>
}
```

And `CompsTableWidget.tsx` (extra prop):

```tsx
// placeholder - replaced in Task 11
export default function CompsTableWidget(
  { result }: { result: any; onMemoryChange: () => void },
) {
  return <pre className="text-xs p-3 overflow-auto">{JSON.stringify(result, null, 2)}</pre>
}
```

- [ ] **Step 5: Verify the frontend builds**

Run (in `frontend/`): `npx tsc -b && npm run test`
Expected: typecheck clean, 12 tests still pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/memoryApi.ts frontend/src/components/canvas/
git commit -m "feat(canvas): memory API client, widget frame + canvas shell"
```

---

### Task 11: Frontend — map, comps table, trend chart, property card widgets

**Files:**
- Replace: `frontend/src/components/canvas/MapWidget.tsx`, `CompsTableWidget.tsx`, `TrendChartWidget.tsx`, `PropertyCardWidget.tsx`

- [ ] **Step 1: MapWidget** (refine sliders live here now; Null Island guard moves here from the old App.tsx)

```tsx
// frontend/src/components/canvas/MapWidget.tsx
import { useMemo, useState } from 'react'
import PropertyMap from '../map/PropertyMap'

// result: a comparable_sales tool result ({ zip_code, map_markers, ... })
export default function MapWidget({ result }: { result: any }) {
  const [maxPrice, setMaxPrice] = useState(5000000)
  const [minBeds, setMinBeds] = useState(0)

  const markers = useMemo(() => {
    const raw: any[] = result?.map_markers ?? []
    return raw
      // Null lat/lon renders at (0,0) "Null Island" - drop ungeocodable rows
      .filter(m => typeof m.lat === 'number' && typeof m.lon === 'number'
        && !Number.isNaN(m.lat) && !Number.isNaN(m.lon))
      .filter(m => {
        const price = m.price ?? m.appraised_value ?? 0
        return price <= maxPrice && (m.beds ?? 0) >= minBeds
      })
      .map(m => ({ ...m, price: m.price ?? m.appraised_value }))
  }, [result, maxPrice, minBeds])

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 min-h-[220px] p-2">
        <PropertyMap zipCode={result?.zip_code} markers={markers} height="100%" />
      </div>
      <div className="px-3 pb-2 grid grid-cols-2 gap-x-4 flex-shrink-0">
        <div>
          <label className="text-xs text-muted-foreground">
            Max price: ${(maxPrice / 1000).toLocaleString()}K
          </label>
          <input type="range" min="100000" max="5000000" step="50000" value={maxPrice}
            onChange={e => setMaxPrice(parseInt(e.target.value))}
            className="w-full accent-primary h-1.5" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Min beds: {minBeds}+</label>
          <input type="range" min="0" max="5" step="1" value={minBeds}
            onChange={e => setMinBeds(parseInt(e.target.value))}
            className="w-full accent-primary h-1.5" />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: CompsTableWidget** (sortable table renders from `result.properties` so rows carry ids; 📌 per row hits the pin REST endpoint directly — no LLM round-trip)

```tsx
// frontend/src/components/canvas/CompsTableWidget.tsx
import { useState } from 'react'
import { ChevronUp, ChevronDown, Pin } from 'lucide-react'
import { createPin } from '../../lib/memoryApi'

type SortKey = 'price' | 'beds' | 'baths' | 'sqft' | 'address'
type SortDir = 'asc' | 'desc'

// Texas is non-disclosure: most county rows only have appraised_value.
const displayPrice = (p: any): number | null =>
  p.sold_price ?? p.price ?? p.appraised_value ?? null

export default function CompsTableWidget(
  { result, onMemoryChange }: { result: any; onMemoryChange: () => void },
) {
  const [sortKey, setSortKey] = useState<SortKey>('price')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [pinned, setPinned] = useState<Set<string>>(new Set())

  const rows: any[] = [...(result?.properties ?? [])].sort((a, b) => {
    const val = (p: any) =>
      sortKey === 'price' ? (displayPrice(p) ?? 0)
      : sortKey === 'address' ? (p.address ?? '')
      : (p[sortKey] ?? 0)
    const [av, bv] = [val(a), val(b)]
    return (av < bv ? -1 : av > bv ? 1 : 0) * (sortDir === 'asc' ? 1 : -1)
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('desc') }
  }

  const handlePin = async (p: any) => {
    try {
      await createPin(p.id)
      setPinned(prev => new Set(prev).add(p.id))
      onMemoryChange()
    } catch (e) {
      console.error('pin failed', e)
    }
  }

  const Th = ({ label, k }: { label: string; k: SortKey }) => (
    <th onClick={() => handleSort(k)}
        className="px-2 py-2 text-xs font-semibold text-muted-foreground cursor-pointer select-none hover:text-foreground whitespace-nowrap text-left">
      <span className="inline-flex items-center gap-1">
        {label}
        {sortKey === k
          ? (sortDir === 'asc'
              ? <ChevronUp className="h-3 w-3 text-primary" />
              : <ChevronDown className="h-3 w-3 text-primary" />)
          : <ChevronUp className="h-3 w-3 opacity-20" />}
      </span>
    </th>
  )

  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground p-4">No matching properties.</p>
  }

  return (
    <table className="w-full text-sm border-collapse">
      <thead className="sticky top-0 bg-card z-10 shadow-sm">
        <tr className="border-b border-border">
          <Th label="Address" k="address" />
          <Th label="Price" k="price" />
          <Th label="Beds" k="beds" />
          <Th label="Baths" k="baths" />
          <Th label="Sqft" k="sqft" />
          <th className="px-2 py-2 text-xs font-semibold text-muted-foreground">Pin</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p: any) => {
          const price = displayPrice(p)
          const appraisedOnly = !p.sold_price && !p.price && p.appraised_value
          return (
            <tr key={p.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
              <td className="px-2 py-1.5 font-medium max-w-[140px] truncate" title={p.address}>
                {p.address ?? '—'}
              </td>
              <td className="px-2 py-1.5 whitespace-nowrap">
                {price ? (
                  <span className="inline-flex flex-col leading-tight">
                    <span className="text-primary font-semibold">${(price / 1000).toFixed(0)}K</span>
                    {appraisedOnly && (
                      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">appraised</span>
                    )}
                  </span>
                ) : '—'}
              </td>
              <td className="px-2 py-1.5">{p.beds ?? '—'}</td>
              <td className="px-2 py-1.5">{p.baths ?? '—'}</td>
              <td className="px-2 py-1.5 whitespace-nowrap">{p.sqft ? p.sqft.toLocaleString() : '—'}</td>
              <td className="px-2 py-1.5">
                <button onClick={() => handlePin(p)} disabled={pinned.has(p.id)}
                        aria-label={`Pin ${p.address}`}
                        className={pinned.has(p.id)
                          ? 'text-primary'
                          : 'text-muted-foreground hover:text-primary transition-colors'}>
                  <Pin className="h-3.5 w-3.5" fill={pinned.has(p.id) ? 'currentColor' : 'none'} />
                </button>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
```

- [ ] **Step 3: TrendChartWidget** (reuses TimeSeriesChart; `market_data.history` rows carry `period`/`median_price`)

```tsx
// frontend/src/components/canvas/TrendChartWidget.tsx
import TimeSeriesChart from '../charts/TimeSeriesChart'

export default function TrendChartWidget({ result }: { result: any }) {
  const history: any[] = result?.history ?? []
  if (history.length === 0) {
    return <p className="text-sm text-muted-foreground p-4">No trend history available.</p>
  }
  return (
    <div className="p-2">
      <TimeSeriesChart data={history} metric="median_price" zipCode={result?.zip_code} />
      <div className="px-2 pb-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>Median: ${result?.median_price?.toLocaleString() ?? '—'}</span>
        <span>Avg DOM: {result?.avg_days_on_market ?? '—'}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: PropertyCardWidget** (renders a `pin_update` result)

```tsx
// frontend/src/components/canvas/PropertyCardWidget.tsx
export default function PropertyCardWidget({ result }: { result: any }) {
  const p = result?.property ?? {}
  const price = p.sold_price ?? p.price
  const rows: Array<[string, any]> = [
    ['Beds', p.beds], ['Baths', p.baths],
    ['Sqft', p.sqft?.toLocaleString()], ['Year built', p.year_built],
    ['Zip', p.zip_code], ['Source', p.source],
  ]
  return (
    <div className="p-4 space-y-3">
      <div>
        <p className="font-semibold text-foreground">{p.address ?? 'Unknown address'}</p>
        {result?.note && <p className="text-xs text-muted-foreground italic">"{result.note}"</p>}
      </div>
      <div>
        {price ? (
          <p className="text-xl font-bold text-primary">
            ${Number(price).toLocaleString()}{' '}
            <span className="text-xs font-normal text-muted-foreground">sold</span>
          </p>
        ) : p.appraised_value ? (
          <p className="text-xl font-bold text-primary">
            ${Number(p.appraised_value).toLocaleString()}{' '}
            <span className="text-xs font-normal text-muted-foreground uppercase">appraised</span>
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">No price data</p>
        )}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {rows.filter(([, v]) => v != null).map(([k, v]) => (
          <div key={k} className="flex justify-between border-b border-border/40 py-0.5">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="text-foreground font-medium">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
```

- [ ] **Step 5: Verify build + tests**

Run (in `frontend/`): `npx tsc -b && npm run test`
Expected: clean typecheck, 12 tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/canvas/
git commit -m "feat(canvas): map, comps table (with pin buttons), trend chart, property card widgets"
```

---

### Task 12: Frontend — CoverageMapWidget

**Files:**
- Replace: `frontend/src/components/canvas/CoverageMapWidget.tsx`

- [ ] **Step 1: Implement** (zip polygons via react-map-gl Source/Layer + freshness table)

```tsx
// frontend/src/components/canvas/CoverageMapWidget.tsx
import { useMemo } from 'react'
import Map, { Source, Layer } from 'react-map-gl/mapbox'
import 'mapbox-gl/dist/mapbox-gl.css'

// result: a data_coverage tool result ({ coverage: rows, boundaries: [GeoJSON Feature] })
export default function CoverageMapWidget({ result }: { result: any }) {
  const mapboxToken = import.meta.env.VITE_MAPBOX_TOKEN
  const rows: any[] = result?.coverage ?? []
  const features: any[] = result?.boundaries ?? []

  const fc = useMemo(
    () => ({ type: 'FeatureCollection' as const, features }),
    [features],
  )

  return (
    <div className="flex flex-col h-full">
      {mapboxToken && features.length > 0 && (
        <div className="h-52 flex-shrink-0 p-2">
          <div className="h-full rounded-lg overflow-hidden border border-border">
            <Map
              mapboxAccessToken={mapboxToken}
              initialViewState={{ longitude: -96.79, latitude: 32.85, zoom: 9.5 }}
              mapStyle="mapbox://styles/mapbox/light-v11"
            >
              <Source id="coverage-zips" type="geojson" data={fc}>
                <Layer id="coverage-fill" type="fill"
                       paint={{ 'fill-color': '#3b82f6', 'fill-opacity': 0.2 }} />
                <Layer id="coverage-line" type="line"
                       paint={{ 'line-color': '#3b82f6', 'line-width': 2 }} />
              </Source>
            </Map>
          </div>
        </div>
      )}
      <div className="p-3 flex-1 overflow-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="text-left py-1 px-2">Zip</th>
              <th className="text-right py-1 px-2">Parcels</th>
              <th className="text-right py-1 px-2">Sold listings</th>
              <th className="text-right py-1 px-2">Stats through</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any) => (
              <tr key={r.zip} className="border-b border-border/40">
                <td className="py-1 px-2 font-medium">
                  {r.zip} <span className="text-muted-foreground">({r.county})</span>
                </td>
                <td className="py-1 px-2 text-right">{r.parcel_count?.toLocaleString()}</td>
                <td className="py-1 px-2 text-right">{r.sold_listing_count ?? 0}</td>
                <td className="py-1 px-2 text-right">{r.stats_to ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[11px] text-muted-foreground mt-2">
          {rows[0]?.appraisal_year} appraisal roll. {result?.notes}
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run (in `frontend/`): `npx tsc -b && npm run test`
Expected: clean, 12 tests pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/canvas/CoverageMapWidget.tsx
git commit -m "feat(canvas): coverage map widget with zip polygons + freshness table"
```

---

### Task 13: Frontend — Hermes Knows panel

**Files:**
- Create: `frontend/src/components/hermes/HermesKnowsPanel.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/src/components/hermes/HermesKnowsPanel.tsx
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { X, Trash2, Play, Brain, MapPinned } from 'lucide-react'
import {
  getPins, deletePin, getSearches, deleteSearch,
  getSkills, setSkillLevel, deleteSkill, getCoverage,
} from '../../lib/memoryApi'

interface HermesKnowsPanelProps {
  open: boolean
  onClose: () => void
  version: number                 // bump to refetch (memory changed elsewhere)
  onRerunSearch: (name: string) => void
  onShowCoverage: () => void
}

const LEVELS = ['novice', 'learning', 'familiar'] as const

function Section({ title, error, onRetry, children }: {
  title: string; error: boolean; onRetry: () => void; children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {error
        ? <button onClick={onRetry} className="text-xs text-destructive underline">Failed to load — retry</button>
        : children}
    </div>
  )
}

export default function HermesKnowsPanel({
  open, onClose, version, onRerunSearch, onShowCoverage,
}: HermesKnowsPanelProps) {
  const [pins, setPins] = useState<any[] | null>(null)
  const [searches, setSearches] = useState<any[] | null>(null)
  const [skills, setSkills] = useState<any[] | null>(null)
  const [coverage, setCoverage] = useState<any | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    if (!open) return
    getPins().then(setPins).catch(() => setPins(null))
    getSearches().then(setSearches).catch(() => setSearches(null))
    getSkills().then(setSkills).catch(() => setSkills(null))
    getCoverage().then(setCoverage).catch(() => setCoverage(null))
  }, [open, version, reload])

  if (!open) return null
  const retry = () => setReload(r => r + 1)

  return (
    <div className="fixed inset-y-0 right-0 w-96 max-w-full bg-card border-l border-border shadow-xl z-50 flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-border flex-shrink-0">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <Brain className="h-4 w-4" /> Hermes Knows
        </h2>
        <button onClick={onClose} aria-label="Close panel"
                className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <Section title="Saved searches" error={searches === null} onRetry={retry}>
          {searches?.length === 0 && (
            <p className="text-xs text-muted-foreground">None yet — ask Hermes to save one.</p>
          )}
          {searches?.map((s: any) => (
            <div key={s.name} className="border border-border rounded-lg p-2 text-sm space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-medium">{s.name}</span>
                <span className="flex gap-2">
                  <button onClick={() => { onRerunSearch(s.name); onClose() }}
                          aria-label={`Rerun ${s.name}`}
                          className="text-muted-foreground hover:text-primary">
                    <Play className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => deleteSearch(s.name).then(retry)}
                          aria-label={`Delete ${s.name}`}
                          className="text-muted-foreground hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {Object.entries(s.criteria ?? {}).map(([k, v]) => `${k}=${v}`).join(' · ')}
              </p>
              {s.client_note && (
                <p className="text-xs italic text-muted-foreground">"{s.client_note}"</p>
              )}
            </div>
          ))}
        </Section>

        <Section title="Pinned properties" error={pins === null} onRetry={retry}>
          {pins?.length === 0 && (
            <p className="text-xs text-muted-foreground">Nothing pinned yet.</p>
          )}
          {pins?.map((p: any) => (
            <div key={p.property_id} className="border border-border rounded-lg p-2 text-sm space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-medium truncate">{p.properties?.address ?? p.property_id}</span>
                <button onClick={() => deletePin(p.property_id).then(retry)}
                        aria-label="Unpin"
                        className="text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              {p.note && <p className="text-xs italic text-muted-foreground">"{p.note}"</p>}
            </div>
          ))}
        </Section>

        <Section title="Your skill profile" error={skills === null} onRetry={retry}>
          {skills?.length === 0 && (
            <p className="text-xs text-muted-foreground">Hermes hasn't observed anything yet.</p>
          )}
          {skills?.map((s: any) => (
            <div key={s.concept}
                 className="flex items-center justify-between text-sm border-b border-border/40 py-1">
              <span>{s.concept}</span>
              <span className="flex items-center gap-2">
                <select value={s.level}
                        aria-label={`Level for ${s.concept}`}
                        onChange={e => setSkillLevel(s.concept, e.target.value).then(retry)}
                        className="text-xs bg-secondary rounded px-1 py-0.5 border border-border">
                  {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
                </select>
                <button onClick={() => deleteSkill(s.concept).then(retry)}
                        aria-label={`Forget ${s.concept}`}
                        className="text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-3 w-3" />
                </button>
              </span>
            </div>
          ))}
        </Section>

        <Section title="Data coverage" error={coverage === null} onRetry={retry}>
          {coverage && (
            <div className="text-xs text-muted-foreground space-y-1">
              <p>
                {[...new Set(coverage.coverage.map((r: any) => r.county))].join(', ')} ·{' '}
                {coverage.coverage.length} zips ·{' '}
                {coverage.coverage
                  .reduce((n: number, r: any) => n + (r.parcel_count ?? 0), 0)
                  .toLocaleString()} parcels
              </p>
              <button onClick={() => { onShowCoverage(); onClose() }}
                      className="inline-flex items-center gap-1 text-primary hover:underline">
                <MapPinned className="h-3 w-3" /> View coverage map
              </button>
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run (in `frontend/`): `npx tsc -b`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/hermes/
git commit -m "feat(hermes): Hermes Knows panel - editable pins, searches, skills, coverage"
```

---

### Task 14: Frontend — rewire App + ChatPanel, remove old panels

**Files:**
- Modify: `frontend/src/App.tsx` (full replacement below)
- Modify: `frontend/src/components/chat/ChatPanel.tsx`
- Delete: `frontend/src/components/output/OutputPanel.tsx`, `frontend/src/components/map/FiltersAndMapPanel.tsx`

- [ ] **Step 1: Replace `frontend/src/App.tsx`**

```tsx
import { useReducer, useState } from 'react'
import ChatPanel from './components/chat/ChatPanel'
import WidgetCanvas from './components/canvas/WidgetCanvas'
import HermesKnowsPanel from './components/hermes/HermesKnowsPanel'
import { widgetReducer } from './widgets/widgetReducer'
import { toolResultToActions } from './widgets/toolResultToWidgets'
import { getCoverage } from './lib/memoryApi'
import { Brain, MapPinned } from 'lucide-react'
import './index.css'

function App() {
  const [widgets, dispatch] = useReducer(widgetReducer, [])
  const [hermesOpen, setHermesOpen] = useState(false)
  const [memoryVersion, setMemoryVersion] = useState(0)
  const [injectedMessage, setInjectedMessage] =
    useState<{ text: string; id: number } | null>(null)

  const bumpMemory = () => setMemoryVersion(v => v + 1)

  const handleToolResult = (result: any) => {
    for (const action of toolResultToActions(result, Date.now())) dispatch(action)
    if (result?.type === 'pin_update' || result?.type === 'saved_search_update'
        || result?.type === 'skill_update') {
      bumpMemory()
    }
  }

  // Skill observations may land silently during a turn - refresh after each stream.
  const handleStreamComplete = () => bumpMemory()

  const handleRerunSearch = (name: string) =>
    setInjectedMessage({ text: `Run my saved search "${name}"`, id: Date.now() })

  const handleShowCoverage = async () => {
    try {
      const cov = await getCoverage()
      dispatch({
        type: 'upsert',
        widget: {
          key: 'coverage', type: 'coverage_map', title: 'Data coverage',
          props: { type: 'data_coverage', ...cov }, updatedAt: Date.now(),
        },
      })
    } catch (e) {
      console.error('coverage fetch failed', e)
    }
  }

  return (
    <div className="h-screen w-screen bg-background">
      <header className="border-b border-border px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">DFW Realtor Agent</h1>
            <p className="text-xs text-muted-foreground">
              Hermes — your market research control center
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleShowCoverage}
                    className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-border hover:bg-accent transition-colors">
              <MapPinned className="h-4 w-4" /> Coverage
            </button>
            <button onClick={() => setHermesOpen(true)}
                    className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-border hover:bg-accent transition-colors">
              <Brain className="h-4 w-4" /> Hermes Knows
            </button>
          </div>
        </div>
      </header>

      <div className="h-[calc(100vh-61px)] grid grid-cols-12">
        <div className="col-span-4 xl:col-span-3 border-r border-border overflow-hidden">
          <ChatPanel
            onToolResult={handleToolResult}
            onStreamComplete={handleStreamComplete}
            injectedMessage={injectedMessage}
          />
        </div>
        <div className="col-span-8 xl:col-span-9 overflow-hidden">
          <WidgetCanvas widgets={widgets} dispatch={dispatch} onMemoryChange={bumpMemory} />
        </div>
      </div>

      <HermesKnowsPanel
        open={hermesOpen}
        onClose={() => setHermesOpen(false)}
        version={memoryVersion}
        onRerunSearch={handleRerunSearch}
        onShowCoverage={handleShowCoverage}
      />
    </div>
  )
}

export default App
```

- [ ] **Step 2: Update `ChatPanel.tsx`**

Three changes — props, injected messages, and full-message display:

Replace the props interface and signature:
```tsx
interface ChatPanelProps {
  onToolResult: (result: any) => void
  onStreamComplete: () => void
  injectedMessage?: { text: string; id: number } | null
}

export default function ChatPanel({
  onToolResult,
  onStreamComplete,
  injectedMessage,
}: ChatPanelProps) {
```

Delete the `parseAgentResponse` function entirely. In the SSE handler, replace the `agent_message` branch with (full message shown in chat — the canvas is *now*, chat scroll is the past):
```tsx
              if (event.type === 'agent_message') {
                assistantContent = event.content.replace('---SUGGESTION---', '\n\n')
                setMessages(prev => {
                  const newMessages = [...prev]
                  const existingIndex = newMessages.findIndex(
                    (m, i) => i === assistantMessageIndex && m.role === 'assistant'
                  )
                  if (existingIndex >= 0) {
                    newMessages[existingIndex].content = assistantContent
                  } else {
                    newMessages.push({
                      role: 'assistant',
                      content: assistantContent,
                      timestamp: new Date(),
                    })
                  }
                  return newMessages
                })
              } else if (event.type === 'tool_result') {
```

Remove the `onStreamStart()` call and any remaining `onAgentMessage` references. Add the injected-message effect after the `handleSendMessage` definition:
```tsx
  useEffect(() => {
    if (injectedMessage?.text) {
      handleSendMessage(injectedMessage.text)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [injectedMessage?.id])
```

- [ ] **Step 3: Delete the superseded components**

```bash
git rm frontend/src/components/output/OutputPanel.tsx frontend/src/components/map/FiltersAndMapPanel.tsx
```
(`PropertyMap.tsx` and the chart components stay — widgets use them.)

- [ ] **Step 4: Verify build + tests**

Run (in `frontend/`): `npx tsc -b && npm run test`
Expected: clean typecheck (no dangling OutputPanel/FiltersAndMapPanel imports), 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/chat/ChatPanel.tsx
git commit -m "feat(canvas): App on widget reducer, Hermes header controls, chat as history"
```

---

### Task 15: Full verification + live smoke ritual

- [ ] **Step 1: Full backend suite**

Run: `backend/.venv/bin/python -m pytest backend/tests -v`
Expected: all pass (36 pre-existing + ~24 new).

- [ ] **Step 2: Full frontend check**

Run (in `frontend/`): `npx tsc -b && npm run test && npm run lint`
Expected: all clean.

- [ ] **Step 3: Restart both servers**

Kill the running uvicorn, then start backend (`backend/`: `.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000`) and frontend (`frontend/`: `npm run dev`) in the background.

- [ ] **Step 4: Live smoke ritual** (from the spec — the four flows that exercise every new seam; ask the user to drive, or drive via curl + browser)

1. **Out-of-coverage question**: ask "What are prices like in Fort Worth 76102?" → Hermes states the bounds, calls `get_data_coverage`, a coverage widget with 5 zip polygons appears.
2. **Pin from the table**: ask "Show me 3 bed homes in 75248", click 📌 on a row → Hermes Knows panel shows the pin; ask "what do you know about me?" → Hermes mentions it.
3. **Saved search rerun**: ask Hermes to save the 75248 search as "Johnsons", open Hermes Knows, click ▶ → chat sends the rerun, map/table widgets *update in place* (no duplicates).
4. **Skill correction**: ask "what does DOM mean?" (skill recorded as novice) → in the panel, set `days_on_market` to familiar → ask a DOM question again; Hermes doesn't re-explain.

- [ ] **Step 5: Commit any smoke-test fixes**

```bash
git add -A && git commit -m "chore(hermes): smoke-test fixes"
```

---

## Self-Review (completed at plan time)

- **Spec coverage:** tables+view (T1), db methods+identity (T2), boundaries (T3), zip passthrough (T4), memory block+degradation (T5), 7 tools incl. familiar-guard/ambiguity/coverage-validation (T6, T2), prompt teaching/coverage rules + per-turn injection (T7), REST CRUD+coverage endpoint (T8), reducer+keyed upserts+unknown-type tolerance (T9), canvas+frame (T10), widgets incl. pin-without-LLM and refine sliders (T11), coverage polygons (T12), editable panel with per-section retry (T13), chat-as-history + OutputPanel removal (T14), smoke ritual (T15). Saved-search coverage drift is validated in `save_search` (warn on save); a drifted run returns a truthful zero-count result the agent reports.
- **Placeholder scan:** Task 10 Step 4 uses explicitly-labeled temporary bodies that Tasks 11–12 fully replace within this same plan — intentional sequencing, not a TBD.
- **Type consistency:** `widget_key` everywhere (tool arg, SSE event field, reducer key); tool result `type` strings match mapper cases (`comparable_sales`, `market_data`, `pin_update`, `data_coverage`, `widget_dismiss`; `saved_search_update`/`skill_update` intentionally spawn no widget, only a memory-panel refresh); `HERMES_USER_ID` imported from `backend.hermes` in all backend modules.
