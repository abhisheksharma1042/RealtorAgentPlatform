# System Flows — DFW Realtor Agent Platform

> Companion docs: [ARCHITECTURE.md](./ARCHITECTURE.md) · [DEMO-GUIDE.md](./DEMO-GUIDE.md)

Every important runtime path through the system, end to end. Diagrams are
Mermaid (rendered by GitHub / VS Code preview).

---

## 1. A chat turn, end to end

The core loop of the whole product. Everything the user sees on the canvas is
a side effect of this flow.

```mermaid
sequenceDiagram
    actor U as User
    participant CP as ChatPanel
    participant API as POST /api/chat/stream
    participant MB as build_memory_block()
    participant G as LangGraph (agent ⇄ tools)
    participant C as Claude sonnet-4-5
    participant DB as Supabase
    participant App as App.tsx (reducer)

    U->>CP: types "Show me 3-bed comps under $800K in 75248"
    CP->>API: {"message": "..."}
    API->>MB: load memory once for this request
    MB->>DB: pins + searches + skills + coverage (data_coverage view)
    MB-->>API: markdown memory block (or degradation fallback)
    loop until Claude stops calling tools
        API->>G: agent node
        G->>C: system prompt + memory block + messages (9 tools bound)
        C-->>G: text and/or tool_calls
        G-->>CP: SSE agent_message / tool_call
        opt tool_calls present
            G->>DB: execute tool (e.g. get_comparable_sales)
            G-->>CP: SSE tool_result {"type": "comparable_sales", ...}
            CP->>App: onToolResult(result)
            App->>App: toolResultToActions → dispatch upsert(map:75248), upsert(table:75248)
        end
    end
    G-->>CP: SSE complete
    CP->>App: onStreamComplete → bump memoryVersion
    Note over App: panel + pin buttons re-fetch memory
```

Key facts:
- **Memory is loaded once per request**, not per agent hop, and appended to
  the system prompt. Panel edits made between turns are picked up automatically.
- The final answer ends with `---SUGGESTION---` + a follow-up suggestion; the
  ChatPanel renders it as a visually separate block.
- Each turn is stateless server-side (no session persistence yet) — the
  durable state is Plutus memory, not conversation history.

### SSE event protocol

| Event | Payload | Frontend reaction |
|---|---|---|
| `agent_message` | `{content, node}` | Append/replace assistant bubble text |
| `tool_call` | `{tool, args}` | Inline "Plutus is running X" activity row |
| `tool_result` | `{tool, result}` | `toolResultToActions(result)` → widget dispatch; memory bump for `pin_update` / `saved_search_update` / `skill_update` |
| `complete` | `{}` | End stream, bump `memoryVersion` |
| `error` | `{error}` | Show error state in chat |

### Tool result → widget mapping

| `result.type` | Canvas effect (content-identity keys) |
|---|---|
| `comparable_sales` | upsert `map:<zip>` + `table:<zip>` — same ZIP replaces, new ZIP adds |
| `market_data` | upsert `trend:<zip>` |
| `pin_update` (action `pinned`) | upsert `card:<property_id>` |
| `data_coverage` | upsert `coverage` |
| `widget_dismiss` | dismiss `widget_key` |
| unknown | ignored (forward compatibility) |

---

## 2. Memory writes — two paths, one substrate

Both the agent (via tools) and the user (via the Plutus Knows panel / pin
buttons) write the **same Supabase tables**. Neither path is a cache of the
other, so they can never disagree for more than one turn.

```mermaid
flowchart TB
    subgraph AgentPath["Path A — through conversation"]
        A1[User asks Plutus to pin / save / teach] --> A2[Claude calls memory tool]
        A2 --> A3[pin_property / save_search / record_skill_observation]
    end
    subgraph PanelPath["Path B — direct manipulation (no LLM)"]
        B1[Plutus Knows panel or comps-table pin button] --> B2[REST /api/memory/*]
    end
    A3 --> DB[(pinned_properties<br/>saved_searches<br/>skill_profile)]
    B2 --> DB
    DB -->|next turn: build_memory_block| P[System prompt block<br/>”Plutus context”]
    DB -->|memoryVersion bump → refetch| UI[Panel + pin buttons]
```

Consistency mechanisms:
- **`memoryVersion`** (an integer in `App.tsx`) bumps on memory-mutating tool
  results, on stream completion, and on any REST mutation. The panel and pin
  hydration re-fetch when it changes.
- **Preserve-on-omit upserts**: re-saving a pin/search/skill without the
  optional note keeps the stored note (PostgREST updates only payload-present
  columns).
- **User authority**: a skill level edited in the panel is stamped
  `notes = "set by user"`; `upsert_skill` refuses to let agent observations
  override it. Separately, the agent can't claim `familiar` until
  `evidence_count >= 3` (demoted to `learning`).

---

## 3. Saved-search rerun from the panel

The rerun button doesn't call the search API directly — it routes through the
chat so the agent runs it, narrates it, and the results land on the canvas
like any other turn.

```mermaid
sequenceDiagram
    actor U as User
    participant P as PlutusKnowsPanel
    participant App as App.tsx
    participant CP as ChatPanel
    participant G as Agent

    U->>P: clicks ⟳ on "Johnsons"
    P->>App: onRerunSearch("Johnsons")
    App->>CP: injectedMessage = 'Run my saved search "Johnsons"'
    alt a stream is already running
        CP->>CP: queue in pendingInjectedRef, drain after current stream
    end
    CP->>G: sends the message as a normal chat turn
    G->>G: run_saved_search("Johnsons") → criteria → get_comparable_sales
    G-->>CP: tool_result comparable_sales (saved_search_name = "Johnsons")
    Note over App: map + table widgets titled “— Johnsons”, last_run_at stamped
```

---

## 4. The teaching loop ("learns-with-you")

```mermaid
flowchart TB
    Q["User asks: what does days on market mean?"] --> O1[Agent explains plainly +<br/>record_skill_observation days_on_market, novice]
    O1 --> S[(skill_profile)]
    S --> N[Next turns: memory block says<br/>explain plainly on first use]
    N --> E[User starts using the term correctly] --> O2[record_skill_observation → learning → familiar<br/>needs evidence_count ≥ 3 for familiar]
    O2 --> S
    S --> T[Once familiar: never re-explained, terse answers]
    U[User corrects level in panel<br/>PUT /api/memory/skills] -->|notes = set by user| S
    U -.-> A[Agent observations can no longer override it]
```

Demo-visible consequences:
- First mention of an unknown concept → one plain-English sentence, exactly once.
- Concepts marked `familiar` are never re-explained (familiar-suppression).
- A panel correction beats the agent's opinion permanently.

---

## 5. Coverage honesty flow

Two entry points, one widget.

**In-chat (agent-driven):** the user asks about somewhere the platform has no
data (e.g. Fort Worth / Tarrant County). The memory block already told the
agent its hard bounds, so it (1) says plainly it has no data there, (2) calls
`get_data_coverage` so the canvas *shows* the actual bounds, (3) offers what it
can do instead.

**Header button (direct):** `Coverage` button → `GET /api/coverage` →
dispatches the `coverage` widget without involving the agent.

```mermaid
flowchart LR
    V[data_coverage VIEW<br/>live per-zip truth from county_parcels/properties/market_stats] --> MB[Memory block<br/>hard bounds in every prompt]
    V --> T[get_data_coverage tool]
    V --> R[GET /api/coverage]
    B[(zip_boundaries<br/>ZCTA GeoJSON)] --> T
    B --> R
    T --> W[CoverageMapWidget:<br/>boundary polygons + freshness table + non-disclosure note]
    R --> W
```

Because coverage is a VIEW, ingesting a new ZIP instantly updates the agent's
self-knowledge, the coverage map, and the refusal behavior — no config change.

---

## 6. Pin flow (both directions)

```mermaid
sequenceDiagram
    actor U as User
    participant T as CompsTableWidget
    participant REST as /api/memory/pins
    participant G as Agent

    Note over T: pin buttons hydrate from GET /api/memory/pins (keyed on memoryVersion)
    alt via table button
        U->>T: clicks pin on a row
        T->>T: optimistic in-flight state
        T->>REST: POST {property_id}
        T->>T: bump memoryVersion → re-hydrate
    else via chat
        U->>G: "Pin 5217 Milam St for the Johnsons"
        G->>G: pin_property → find_property_by_address (UUID fast-path, ILIKE; asks if ambiguous)
        G-->>T: tool_result pin_update → card widget + memory bump
    end
    Note over G: next turn, the pin appears in the memory block:<br/>“Pinned properties: 5217 Milam St (75204) — note: …”
```

---

## 7. Data ingestion pipeline (offline, CLI)

How the database got its 41k parcels. Run order for seeding a new ZIP:

```mermaid
flowchart TB
    subgraph Step1["1 · dcad refresh"]
        D1[Download DCAD bulk export ~196MB zip] --> D2[Stream-parse, filter to SEEDED_ZIPS]
        D2 --> D3[asyncpg batch upsert 500/batch → county_parcels]
        D3 --> D4[normalize → properties source=county<br/>appraised values, no sold prices]
    end
    subgraph Step2["2 · geocode backfill → geocode mapbox"]
        G1[Census batch geocoder] --> G2[county_parcels.location]
        G3[Mapbox fallback for misses] --> G2
        G2 --> G4[re-normalize → properties.lat/lon]
    end
    subgraph Step3["3 · rentcast seed (budget-guarded, 50 req/mo)"]
        R1[markets endpoint] --> R2[market_stats monthly rows]
        R3[sold listings ≤100/zip] --> R4[properties source=rentcast<br/>the only real sold prices]
    end
    subgraph Step4["4 · boundaries fetch"]
        B1[Census TIGERweb ZCTA layer] --> B2[zip_boundaries GeoJSON]
    end
    Step1 --> Step2 --> Step3 --> Step4 --> V[data_coverage VIEW updates automatically<br/>→ Plutus knows about the new ZIP next turn]
```

Cross-cutting behavior:
- **Response cache** (`api_responses`): every external call cached with
  per-endpoint TTLs (RentCast markets 30d, listings 90d; Census/FEMA/WalkScore
  365d). Re-runs are cheap and idempotent.
- **Budget guard** (`api_budget`): RentCast capped at 50 requests/month;
  exceeding raises before the HTTP call.

### Lazy market-data fallback (runtime)

If the agent calls `fetch_market_data` for a ZIP with no cached stats, the tool
tries a live RentCast fetch + normalize inline (budget permitting) before
returning "no data" — so a coverage-adjacent ZIP can cold-start during a
conversation.

---

## 8. Failure & degradation paths

| Failure | Behavior |
|---|---|
| Memory/DB load fails at turn start | Static fallback block: "do not reference pins/searches/skills; coverage unknown this turn" + non-disclosure caveat retained. Chat still works |
| A memory tool fails mid-turn | Tool returns `{"type": …, "error": …}`; agent explains; stream survives |
| Unknown tool-result type reaches frontend | Ignored by `toolResultToActions` — no crash |
| Comps rows with missing/(0,0) coords | MapWidget filters them out (Null-Island guard) |
| Saved-search/skill names containing `/` | `:path` route converters + `encodeURIComponent` on the client |
| Rerun clicked mid-stream | Queued in `pendingInjectedRef`, drained after the active stream completes |
| RentCast budget exhausted | Lazy fetch fails gracefully → tool returns explicit error payload |
