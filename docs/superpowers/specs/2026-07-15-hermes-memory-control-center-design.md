# Hermes Memory Layer & Control Center — Design

**Date:** 2026-07-15
**Status:** Approved (brainstormed with visual companion; paradigm, memory scope, identity, transparency, canvas, and architecture each user-validated)

## Vision

Hermes is the conversational orchestrator of the platform: chat is the spine of the app, and Hermes — armed with persistent memory about the user and full knowledge of the data it has — composes the workspace in response to conversation. The user experiences a single interface and control center: ask a question, and the right analysis widgets appear; what Hermes knows about you is always visible and correctable.

## Decisions (from brainstorm)

| Question | Decision |
|---|---|
| Control-center paradigm | **Conversational orchestrator** — chat drives a dynamic workspace (over dashboard-first or insight-feed paradigms) |
| Memory scope v1 | **Pins & saved work** (explicit) + **skill model** (implicit). Profile/preferences are subsumed by named saved searches; episodic recall deferred to MVP |
| Identity | **Single-user mode**: fixed `HERMES_USER_ID` UUID constant in config; all tables carry `user_id UUID` so Supabase Auth at MVP is a config flip, not a migration |
| Memory transparency | **Visible & editable** — a "Hermes Knows" panel with per-item delete/correct |
| Workspace mechanics | **Dynamic widget canvas** — fixed widget vocabulary, tool results spawn/update widgets over the existing SSE channel |
| Architecture | **Approach 1: structured memory tables, full load into system prompt each turn, implicit widget mapping.** No embeddings/pgvector in v1; explicitly designed so episodic memory (pgvector `user_memory`) and a full `compose_workspace` protocol bolt on later without migration |
| Coverage awareness | Hermes always knows the bounds of its data (counties, zips, sources, freshness) and can express them visually |

## Data Model (migration 007)

All tables carry `user_id UUID NOT NULL`. Single-user mode uses a fixed UUID constant.

```sql
pinned_properties (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  note TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, property_id)
)

saved_searches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  name TEXT NOT NULL,              -- "Johnsons", "my farm"
  criteria JSONB NOT NULL,         -- zips, min_beds, min_baths, price band; same filter shape get_comparable_sales takes
  client_note TEXT,
  last_run_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, name)
)

skill_profile (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  concept TEXT NOT NULL,           -- normalized snake_case: dom, comps, absorption_rate, price_per_sqft, ...
  level TEXT NOT NULL CHECK (level IN ('novice', 'learning', 'familiar')),
  evidence_count INT NOT NULL DEFAULT 1,
  notes TEXT,                      -- last observation, e.g. "asked what DOM means"
  last_observed_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, concept)
)

zip_boundaries (
  zip VARCHAR(10) PRIMARY KEY,
  boundary JSONB NOT NULL,         -- GeoJSON polygon from Census TIGERweb ZCTA (free), fetched once per seeded zip
  fetched_at TIMESTAMPTZ DEFAULT now()
)

-- data_coverage: SQL VIEW aggregating live truth from the DB
--   per-zip parcel counts (county_parcels), county list, RentCast market_stats
--   date range, sold-listing counts, appraisal roll year. Never a hardcoded list.
```

Notes:

- A pin is a **reference**, not a copy — data refreshes flow through to pinned views.
- The skill-concept vocabulary is prompt guidance, not a DB constraint: Hermes can track an unanticipated concept without a migration.
- `saved_searches.criteria` covers farm-area/preference behavior: a search named "my farm" *is* a remembered preference.

## Backend

### Memory loader — `backend/hermes/memory.py`

On each `/api/chat` request, load all three memory tables (pins joined to `properties` for display addresses) plus the coverage view, and render a compact block into the system prompt:

- Saved searches with criteria and client notes.
- Pins with notes.
- Skill levels split into two prompt lists: "explain plainly on first use: ..." / "be terse about: ...".
- Coverage one-liner: counties, zips, parcel count, roll year, sold-price caveat (Texas non-disclosure).

Memory is small (dozens of rows, single user) so the **entire** state loads every turn — no retrieval step, no embeddings, deterministic. Empty memory renders an empty block (no "user has no pins" noise). The documented scale-up path is episodic `user_memory` + pgvector at MVP; it touches none of these tables.

### Agent tools — `backend/agent/memory_tools.py`

| Tool | Behavior |
|---|---|
| `pin_property(address_or_id, note?)` | Resolve address against `properties` (normalized exact match, coverage-scoped). Multiple matches → return candidates, Hermes asks. No match → "not found, ask user". Never pin a guess. |
| `unpin_property(address_or_id)` | Remove pin. |
| `save_search(name, criteria, client_note?)` | Upsert by name. Prompted behavior: Hermes *offers* to save when it notices repetition — explicit memory stays explicit, no silent saves. |
| `run_saved_search(name)` | Load criteria, stamp `last_run_at`, delegate to the existing `get_comparable_sales` path so results stream in the shape the frontend already consumes. |
| `record_skill_observation(concept, level, note?)` | Upsert + increment `evidence_count`. Called implicitly per prompt rules (user asks what a term means → novice; uses it correctly → nudge toward familiar). |
| `dismiss_widget(widget_key)` | Emit a widget-remove event over SSE (the one piece of explicit canvas control in v1). Keys are deterministic and content-derived (`map:75248`), so Hermes can name what it summoned. |
| `get_data_coverage()` | Return structured coverage (counties, per-zip counts, boundary refs, source freshness, known gaps) → spawns the `coverage_map` widget. Also the prompted response to out-of-bounds queries: say what is covered instead of returning zero rows. |

### REST CRUD — for the Hermes Knows panel

- `GET/DELETE /api/memory/pins`
- `GET/POST/PUT/DELETE /api/memory/searches`
- `GET/PUT/DELETE /api/memory/skills` (PUT = user corrects a level)
- `GET /api/coverage`

Panel actions hit REST directly (no LLM round-trip); Hermes sees changes on the next turn's memory load.

### System prompt additions

1. Memory block (above) injected per turn.
2. Coverage line injected per turn — the anti-hallucination guard.
3. Teaching rule: *first time a novice-level concept appears in an answer, add a one-sentence plain-English explanation; never re-explain concepts marked familiar; trust the panel (user-corrected levels) over inference.*
4. Skill-observation rule: when to call `record_skill_observation`, with a starter concept list (comps, dom, absorption_rate, price_per_sqft, appraised_vs_market, contingency, escrow).

## Frontend

### Widget canvas

`App.tsx`: chat pane stays left; center/right fixed panes are replaced by `WidgetCanvas`, a responsive 2-column grid driven by a **widget reducer**:

- State: `Widget[]` of `{ key, type, title, props, updatedAt }`.
- SSE tool results dispatch **upserts keyed by content identity** (`map:75248`, `trend:75248`, `card:<property_id>`) — reruns update widgets instead of stacking duplicates.
- `dismiss_widget` (agent) and the ✕ button (user) dispatch the same remove action.
- Unknown/malformed widget events are ignored (forward compatibility).

### Widget vocabulary (fixed, six types)

| Widget | Content | Source event |
|---|---|---|
| `map` | Markers from search/comps results; refine sliders attached; pins highlighted ★ | `comparable_sales` / `run_saved_search` |
| `comps_table` | Sortable rows; 📌 pin button per row (calls pin REST directly) | `comparable_sales` |
| `trend_chart` | `market_stats` time series | `market_data` |
| `property_card` | One property: appraisal, attributes, pin note | `pin_property`, or drill-in |
| `coverage_map` | Seeded-zip polygons (from `zip_boundaries`) + freshness card | `get_data_coverage` |
| `hermes_knows` | Memory panel (below) | header toggle (persistent) |

Existing `PropertyMap` and the comps table lift into widget bodies largely as-is.

### Hermes Knows panel

Persistent header toggle (not agent-summoned). Sections: saved searches (rerun ▶ injects a chat message; edit ✎; delete 🗑), pins (delete), skill profile (✎ level correction), coverage summary ("view map" summons `coverage_map`). Reads/writes the REST CRUD endpoints; per-section fetch errors show inline retry, never a blank drawer.

### History

The current `OutputPanel` (agent analysis + tool history) folds into the chat stream as collapsible blocks. The canvas always reflects *now*; chat scroll is the past.

## Error Handling

Governing rule: **memory must never break chat.**

- Memory/coverage load failure → run the turn without the block, log a warning, prepend "memory unavailable this turn" to the prompt.
- Memory tool failure → error string returned to the agent (existing pattern); Hermes tells the user plainly. No hidden retries.
- Ambiguous pin → candidates returned; Hermes asks; never guesses.
- Skill mis-learning → mitigated by `evidence_count` (one observation never jumps to `familiar`), the ✎ user override, and the prompt rule to trust corrections.
- Saved-search / coverage drift → criteria validated against `data_coverage` at run time; mismatches reported, not silently empty.
- Frontend → reducer ignores bad events; panel errors are per-section with retry.

## Testing

Extends the existing pytest suite (36 tests) with the same mock patterns:

- `test_memory.py` — prompt-block rendering (populated and empty), graceful degradation on DB error.
- `test_memory_tools.py` — every tool against a mocked db: pin resolve/ambiguous/not-found, upsert-by-name, evidence increment, saved-search delegation, coverage shape.
- `test_memory_api.py` — CRUD endpoints via FastAPI TestClient; deletes reflect in the next memory load.
- `test_coverage.py` — `data_coverage` view truthfulness against fixtures; out-of-bounds zip detection.
- **Frontend (first vitest tests):** widget reducer only — upsert-by-key, dismiss, unknown-type ignored. It is a pure function; everything else stays manual.
- **Live smoke ritual** (manual, documented): ask an out-of-coverage question → coverage widget; pin from the table → panel updates; rerun a saved search → widgets update in place; correct a skill level → next answer respects it.

## Out of Scope (v1) — with upgrade paths

- **Episodic recall** ("like last week") → `user_memory` + pgvector at MVP; additive.
- **Full workspace protocol** (`compose_workspace` add/update/arrange) → v2 once the widget vocabulary is proven; `dismiss_widget` is the thin end.
- **Supabase Auth / multi-user** → swap the fixed UUID; add RLS policies on the three memory tables.
- **Proactive insight feed / scheduled runs** → paradigm C features; the coverage view and saved searches are the natural substrate.
