# Demo Guide — DFW Realtor Agent Platform

> Companion docs: [ARCHITECTURE.md](./ARCHITECTURE.md) · [SYSTEM-FLOWS.md](./SYSTEM-FLOWS.md)

## The pitch (30 seconds)

"This is **Plutus** — an AI market-research control center for new real-estate
agents in DFW. You talk to it like a colleague, and it builds your workspace
for you: maps, comps tables, price trends, pinned properties. Three things make
it different from a chatbot:

1. **It remembers.** Pins, saved client searches, and what concepts you already
   know — permanently, across sessions — and you can inspect and edit every bit
   of that memory yourself.
2. **It's honest about its data.** It runs on 41,000+ real Dallas County
   appraisal parcels plus RentCast market data, it knows exactly which ZIPs it
   covers, and it will show you a map of its own limits rather than make
   something up.
3. **It teaches as you go.** Terms you don't know get one plain-English
   explanation, exactly once — and it stops explaining things you've learned."

## Pre-demo checklist

### 1. Start the servers

```bash
# Backend (from backend/ — uses the uv-managed venv)
cd backend
nohup .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level warning &

# Frontend (from repo root — npm workspaces)
npm run dev --workspace frontend    # → http://localhost:5173
```

Verify before going on screen:

```bash
curl -s http://localhost:8000/health
# expect: {"status":"healthy","anthropic_key_set":true,"supabase_url_set":true}
curl -s http://localhost:8000/api/coverage | head -c 200   # should return JSON, not an error
```

Open http://localhost:5173 and confirm the header + empty canvas render.

### 2. Environment (already configured in `backend/.env` / `frontend/.env.local`)

| Variable | Used for |
|---|---|
| `ANTHROPIC_API_KEY` | The agent (claude-sonnet-4-5) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DATABASE_URL` | Data + memory |
| `RENTCAST_API_KEY` | Lazy market fetches (budget-capped 50/mo) |
| `MAPBOX_TOKEN` (backend) / `VITE_MAPBOX_TOKEN` (frontend) | Geocoding fallback / map rendering |

### 3. Decide your starting memory

Current live memory (check via **Plutus Knows** button):
- Saved searches: **"Johnsons"** and **"Shergills"** (3+ bed, price-capped)
- Skill: **days_on_market = novice**, marked *set by user*

Two options:
- **Demo on top of it** (recommended): existing memory makes the "it remembers
  across sessions" story land immediately — open the panel first.
- **Clean slate**: delete items in the Plutus Knows panel before you start
  (each row has a delete control). There's no bulk reset.

## What the data actually is (say this confidently)

- **41,292 parcels** from the official DCAD (Dallas Central Appraisal District)
  2025 bulk export, across five seeded ZIPs — 75201 (Downtown), 75204
  (Uptown/East Dallas), 75205 (Highland Park), 75225 (University Park), 75248
  (North Dallas). **100% geocoded** (Census geocoder + Mapbox fallback).
- **RentCast** market statistics (monthly medians, volume, days-on-market
  through July 2026) and ~100 sold listings per ZIP.
- **Texas is a non-disclosure state** — sold prices aren't public record. The
  platform leads with appraised values and labels the RentCast sold subset
  explicitly. Plutus says which one it's using. This is a feature, not a
  limitation: it's the same reality every Texas agent works in.

---

## Demo script

Seven beats, ~10–12 minutes. Exact prompts in code blocks; expected behavior
under each. Beats 3–5 are the memory story — the heart of the demo.

### Beat 1 — Market question → living workspace

```
What are home prices doing in 75205?
```

**Expect:** Plutus calls `fetch_market_data`; a **trend chart widget**
(median price / DOM over 12+ months) appears on the canvas mid-answer. The
answer cites appraised vs sold sourcing. Note the separated follow-up
suggestion at the bottom of the reply.

**Say:** "Notice I didn't ask for a chart — Plutus composes the workspace as a
side effect of the conversation."

### Beat 2 — Comps → map + table

```
Show me 3-bedroom comps under $800K in 75248
```

**Expect:** `get_comparable_sales` → **map widget** (real geocoded pins, price
slider) + **comps table** appear. Re-ask with different filters and the same
ZIP: the widgets *update in place* rather than stacking duplicates.

**Say:** "Widgets have content identity — ask about 75248 twice and you get
one map of 75248, not two."

### Beat 3 — Pinning (memory, part 1)

Pick an address from the comps table, then:

```
Pin <address from the table> — note that the Johnsons liked the backyard
```

**Expect:** a **property card widget** appears; the pin button on that table
row lights up too (both views read the same memory). Also demo the direct
path: click a pin button on another row — no chat needed.

**Say:** "This pin is in the database, not the chat log. Kill the browser,
come back tomorrow, ask 'what properties am I tracking for the Johnsons?' —
it knows."

### Beat 4 — Saved searches (memory, part 2)

```
Save this search as "Johnsons" — it's for a family wanting 3+ beds under $800K
```

**Expect:** Plutus confirms the save (it never saves silently — if you just
repeat criteria twice, it *offers* to save instead).

Then open **Plutus Knows** → Saved searches → click **rerun** on "Johnsons".

**Expect:** a chat message is injected on your behalf, the agent runs the
saved criteria, and the map + table come back titled "— Johnsons".

**Say:** "The panel button routes through the agent on purpose — you get the
same narration and the same canvas behavior whether you type it or click it."

### Beat 5 — The teaching loop (memory, part 3)

```
What does price per square foot actually tell me?
```

**Expect:** a plain-English explanation, and (silently) a skill observation
recorded. Open **Plutus Knows** → Skill profile — the concept is now tracked.

Then show suppression the other way: `days_on_market` is already marked
*novice, set by user*. Correct it to **familiar** in the panel, then ask:

```
How's days on market trending in 75205?
```

**Expect:** no definition of DOM this time — terse, expert-level answer.

**Say:** "It explains a concept exactly once, stops when you've learned it,
and your own correction in the panel always beats its opinion — it can't
decide you're an expert on one data point either; it needs repeated evidence."

### Beat 6 — Coverage honesty (the trust moment)

```
What are prices like in Fort Worth?
```

**Expect:** a plain "I don't have Tarrant County data" — plus the **coverage
map widget**: the five ZCTA boundary polygons it *does* cover, with a per-ZIP
freshness table (parcel counts, appraisal year, stats range), and an offer of
what it can do instead.

**Say:** "This is the anti-hallucination story. Coverage is a live SQL view
injected into every prompt — the agent physically knows its own limits, and
when it says no, it shows you a map of why. Ingest a sixth ZIP and this map,
and the agent's self-knowledge, update automatically."

(Also point out the **Coverage** header button — same widget, no LLM call.)

### Beat 7 — Plutus Knows panel wrap-up

Open the panel and walk the four sections: pins, saved searches, skills,
coverage.

**Say:** "Everything the AI remembers about you is inspectable, editable, and
deletable — memory with a UI, not a black box. And every row already carries a
user ID, so turning this into a multi-user product is an auth flip, not a
rebuild."

---

## How far it's come (the arc, if asked)

1. **Foundation** — FastAPI + LangGraph agent with mock tools, SSE streaming,
   React shell.
2. **Real data** — ingestion pipeline: DCAD bulk parcels (41k), RentCast
   stats/listings, Census+Mapbox geocoding, response caching, API budget
   guards, PostGIS.
3. **Plutus memory & control center** (latest) — persistent memory (pins,
   searches, skills), truthful coverage, 7 new agent tools, memory REST API,
   the widget canvas, and the Plutus Knows panel. Built via TDD: **76 backend
   + 12 frontend tests**, all green.

## Known limitations (don't let these surprise you live)

- **Single user** — one fixed user ID; no login. (Schema is multi-user-ready.)
- **No conversation persistence** — refresh clears chat *and canvas*; memory
  (pins/searches/skills) survives. Frame it as "memory outlives the chat."
- **5 ZIPs, Dallas County only** — anything else is a coverage-refusal demo
  (which is Beat 6, so use it).
- **Sold prices only for the RentCast subset** (~100/ZIP); county rows show
  appraised values.
- Unpinning does **not** remove an existing property-card widget (dismiss it
  with the widget's ✕).
- First response after a long idle can be slow (cold API + iCloud
  re-materialization on this machine).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend up but no answers / SSE errors | Backend down — restart uvicorn (see checklist); check `curl localhost:8000/health` |
| Vite port open but page never loads | Zombie Vite process — `lsof -ti:5173 \| xargs kill`, then `npm run dev --workspace frontend` |
| Maps blank | `VITE_MAPBOX_TOKEN` missing in `frontend/.env.local` (restart Vite after adding) |
| Everything hangs on this Mac after idle / low disk | iCloud evicted files — run `brctl download ~/Desktop/KevinMcrea/RealtorAgentPlatform` and wait; keep >2–3 GB disk free |
| "Memory unavailable this turn" in answers | Supabase unreachable — chat still works; check `SUPABASE_URL`/keys, then retry |

## Quick reference

| Thing | Value |
|---|---|
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 (docs at `/docs`) |
| Model | claude-sonnet-4-5 (LangGraph, 9 tools) |
| Seeded ZIPs | 75201 · 75204 · 75205 · 75225 · 75248 |
| Dataset | 41,292 DCAD parcels (2025 roll), 100% geocoded, RentCast stats → 2026-07 |
| Tests | 76 backend (pytest) + 12 frontend (vitest) |
| Run tests | `backend/.venv/bin/python -m pytest backend/tests` · `npm test --workspace frontend` |
