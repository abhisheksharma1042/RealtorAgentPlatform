# DFW Realtor Agent Platform

An AI-powered market-research **control center** for novice real-estate license
holders in the Dallas–Fort Worth metroplex. Users talk to **Hermes** — a
LangGraph agent backed by Claude — and Hermes composes their workspace: maps,
comps tables, trend charts, and property cards appear on a widget canvas as
side effects of the conversation, grounded in 41k+ real Dallas County parcels.

📚 **Documentation**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — full system architecture, data model, design decisions
- [docs/SYSTEM-FLOWS.md](docs/SYSTEM-FLOWS.md) — end-to-end runtime flows (chat turn, memory, ingestion)
- [docs/DEMO-GUIDE.md](docs/DEMO-GUIDE.md) — demo script, talk track, troubleshooting

## Features

- 🤖 **Hermes agent** — Claude (claude-sonnet-4-5) + LangGraph with 9 tools:
  market stats, comparable sales, pins, saved searches, skill tracking, widget
  control, and data coverage
- 🧠 **Persistent memory** — pinned properties, named saved searches, and a
  per-concept skill profile survive across sessions; the whole memory is
  injected into every turn
- 🪟 **Widget canvas** — reducer-driven workspace (map / comps table / trend
  chart / property card / coverage map) with content-identity keys, driven by
  streamed tool results
- 🔍 **Hermes Knows panel** — inspect, edit, and delete everything the agent
  remembers; user corrections are authoritative
- 🗺️ **Truthful coverage** — a live SQL view of exactly which ZIPs/counties
  have data, injected into every prompt; out-of-coverage questions get an
  honest refusal plus a map of actual bounds
- 🏠 **Real data** — 41,292 DCAD (Dallas Central Appraisal District) parcels
  across 5 seeded ZIPs, 100% geocoded, plus RentCast market stats and sold
  listings; explicit handling of Texas non-disclosure (appraised vs sold)
- 📡 **SSE streaming** — token/tool events streamed to the UI in real time
- 🎓 **Learns-with-you teaching** — unknown concepts explained once in plain
  English; familiar concepts never re-explained

## Tech Stack

**Frontend** — React 19 + TypeScript, Vite, Tailwind CSS (shadcn tokens),
ECharts 6, react-map-gl / Mapbox GL 3, react-markdown, vitest

**Backend** — Python 3.11+, FastAPI, LangGraph + langchain-anthropic,
supabase-py, asyncpg, httpx, pytest + respx

**Database** — Supabase (PostgreSQL + PostGIS)

## Project Structure

```
RealtorAgentPlatform/
├── frontend/src/
│   ├── App.tsx                 # layout, widget reducer, memory sync
│   ├── widgets/                # widget types, reducer, tool-result mapper
│   ├── components/chat/        # ChatPanel (SSE consumer)
│   ├── components/canvas/      # WidgetCanvas + 5 widget bodies
│   ├── components/hermes/      # Hermes Knows memory panel
│   └── lib/memoryApi.ts        # memory REST helpers
├── backend/
│   ├── main.py                 # FastAPI app
│   ├── api/                    # chat (SSE) + memory/coverage REST
│   ├── agent/                  # LangGraph graph, tools, prompts
│   ├── hermes/                 # memory block builder, HERMES_USER_ID
│   ├── db/                     # Supabase client (data + memory methods)
│   ├── ingestion/              # DCAD/RentCast/Census pipeline + CLI
│   ├── migrations/             # 001–007 SQL migrations
│   └── tests/                  # 76 pytest tests
└── docs/                       # architecture, flows, demo guide
```

## Getting Started

### Prerequisites
- Python 3.11+ (backend venv is uv-managed at `backend/.venv`)
- Node.js 18+
- Supabase project (PostGIS enabled), Anthropic API key, Mapbox token,
  RentCast API key (optional, for ingestion/lazy fetches)

### Backend

```bash
cd backend
cp .env.example .env            # fill in keys
# apply migrations 001–007 (see backend/migrations/README.md)
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### Frontend

```bash
# from repo root (npm workspaces — single lockfile at the root)
npm install
npm run dev --workspace frontend   # → http://localhost:5173
```

### Seeding data (one-time, per ZIP set)

```bash
backend/.venv/bin/python -m backend.ingestion.cli dcad refresh
backend/.venv/bin/python -m backend.ingestion.cli geocode backfill
backend/.venv/bin/python -m backend.ingestion.cli geocode mapbox
backend/.venv/bin/python -m backend.ingestion.cli rentcast seed
backend/.venv/bin/python -m backend.ingestion.cli boundaries fetch
```

## API surface

| Endpoint | Purpose |
|---|---|
| `POST /api/chat/stream` | Agent conversation (SSE) |
| `GET/POST/DELETE /api/memory/pins…` | Pin CRUD |
| `GET/POST/DELETE /api/memory/searches…` | Saved-search CRUD |
| `GET/PUT/DELETE /api/memory/skills…` | Skill profile CRUD |
| `GET /api/coverage` | Coverage rows + ZIP boundary polygons |
| `GET /health` | Liveness + env sanity |

## Tests

```bash
backend/.venv/bin/python -m pytest backend/tests   # 76 tests
npm test --workspace frontend                      # 12 tests
```

## Current status

- Single-user proof of concept (fixed user ID; all memory tables carry
  `user_id`, so multi-user auth is a config flip, not a migration)
- Coverage: 5 Dallas County ZIPs — 75201, 75204, 75205, 75225, 75248
- Chat history is per-session; Hermes memory (pins/searches/skills) is
  persistent

## License

MIT
