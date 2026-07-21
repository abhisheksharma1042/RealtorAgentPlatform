# VPS Docker Deployment — Design

**Date:** 2026-07-21
**Status:** Approved design, pending implementation plan

## Goal

Deploy the DFW Realtor Agent Platform (React/Vite frontend + FastAPI/LangGraph
backend) on the existing Hostinger VPS as Docker containers, served through the
Nginx Proxy Manager (NPM) instance already running there, at
**https://realtor.shergillvps.com** with basic-auth protection.

## Target environment (verified via Hostinger API, 2026-07-21)

| Fact | Value |
|---|---|
| VPS | srv1395899.hstgr.cloud — KVM 2: 2 vCPU, 8 GB RAM, 100 GB disk |
| IP | 187.77.205.64 (IPv6 2a02:4780:4:205a::1) |
| OS | Ubuntu 24.04 with Docker template |
| Domain | shergillvps.com (Hostinger-registered, active) |
| Proxy | Nginx Proxy Manager, already running in Docker |
| Database | Supabase cloud (external) — **no Postgres container on the VPS** |
| Existing convention | Repos cloned under `/opt/`; helper scripts live in `~` (another project already deployed this way) |

8 GB RAM makes building images on the VPS (including the Vite build) safe.

## Decisions

| Decision | Choice |
|---|---|
| Domain layout | Single domain, path-routed: `realtor.shergillvps.com` → frontend, `/api/*` → backend. Same origin ⇒ no CORS complexity. |
| Containerization | Two containers via docker-compose: `frontend` (nginx serving Vite build) + `backend` (FastAPI/uvicorn). |
| Build & delivery | Build on the VPS: `git clone`/`pull` at `/opt/RealtorAgentPlatform`, `docker compose up -d --build`. No registry. |
| Access control | NPM Access List (basic auth) on the proxy host — the app has no login and an open endpoint would expose the Anthropic key to abuse. |
| Execution | Claude drives the deployment over SSH; NPM configured via its admin API or guided UI steps. |

## Architecture

```
Internet
  └── NPM (existing container: SSL/Let's Encrypt, force-SSL, Access List)
        ├── /       → realtor-frontend  (nginx:alpine, static Vite dist)
        └── /api/*  → realtor-backend   (uvicorn :8000, SSE)
                          └── outbound: Supabase cloud, Anthropic API,
                              RentCast / Census / Mapbox (ingestion)
```

- Both app containers join **NPM's existing docker network** (declared as an
  external network in compose), so NPM proxies to them by container name.
- **No host ports are published** — the only ingress is through NPM.
- NPM proxy host: `realtor.shergillvps.com` → `http://realtor-frontend:80`,
  plus a **custom location `/api`** → `http://realtor-backend:8000` with
  `proxy_buffering off`, `proxy_cache off`, `proxy_read_timeout 3600s` —
  required for the SSE chat stream to flow token-by-token.
- NPM's custom location passes the path through unchanged, so the backend
  receives `/api/chat/stream` exactly as its routes expect (no prefix strip).

## Components

### Frontend image (`frontend/Dockerfile`)

Multi-stage:

1. **Build stage** — `node:22-alpine`; `npm ci` at the **repo root** (npm
   workspaces, root lockfile), then build the frontend workspace. `VITE_*`
   values arrive as build args: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`,
   `VITE_MAPBOX_TOKEN`, and `VITE_API_URL` set for **same-origin** use (empty
   string / relative). *Implementation must verify how the code concatenates
   `VITE_API_URL` with `/api/...` paths and set the value accordingly.*
2. **Serve stage** — `nginx:alpine` with the built `dist/` and an SPA config:
   `try_files $uri /index.html`, gzip on, long-cache headers for hashed assets.

### Backend image (`backend/Dockerfile`)

- `python:3.11-slim`, deps from `backend/requirements.txt`.
- The image preserves the repo-root package layout (code at `/app/backend`,
  workdir `/app`) so both `uvicorn backend.main:app` and
  `python -m backend.ingestion.cli` resolve the same way they do in dev.
- Runs as a non-root user; `HEALTHCHECK` hits `GET /health`.
- Config via `env_file` → `/opt/RealtorAgentPlatform/backend/.env` created on
  the VPS from `.env.example`. Secrets never enter git or image layers.

### Compose (`docker-compose.yml`, repo root)

- Services `frontend` + `backend`, `restart: unless-stopped`, json-file log
  rotation limits, both attached to the external NPM network (actual network
  name discovered on the VPS during implementation) plus a default internal
  network.
- Frontend build args fed from a root `.env` on the VPS (compose
  interpolation), so `docker compose build` needs no flags.

## Deployment flow (over SSH)

1. Pre-flight: confirm Docker/compose versions, identify NPM's docker network
   name (`docker network ls` / inspect the NPM container).
2. Clone the repo at `/opt/RealtorAgentPlatform` (GitHub deploy key or HTTPS
   token if the repo is private).
3. Create `backend/.env` and root `.env` (frontend build args) from the
   examples; values supplied by the user at deploy time.
4. `docker compose up -d --build`; verify both containers healthy;
   `curl http://realtor-backend:8000/health` from inside the NPM network.
5. DNS: A record `realtor` → `187.77.205.64` via the Hostinger DNS API.
6. NPM: create the proxy host + `/api` custom location (SSE directives),
   request the Let's Encrypt cert, enable force-SSL, attach an Access List
   (credentials chosen by the user).
7. Helper script `~/deploy-realtor.sh` on the VPS: `git pull` + rebuild +
   restart in one step, matching the existing convention of scripts in `~`.

## Operations

- **Redeploy:** run `~/deploy-realtor.sh` (or Claude over SSH).
- **Data refresh (ingestion):** `docker compose exec backend python -m
  backend.ingestion.cli <source> <command>` — same CLI as dev; budget guards
  and caches live in Supabase, so nothing else changes.
- **Logs:** `docker compose logs -f backend` / `frontend`.

## Error handling & risks

| Risk | Mitigation |
|---|---|
| SSE stream buffered/stalled by NPM | Custom-location directives: buffering off, cache off, 3600s read timeout; verified end-to-end after deploy. |
| Vite build memory | Non-issue at 8 GB; if it ever fails, add a temporary swapfile or build the `dist/` locally and rsync. |
| Backend container dies | `restart: unless-stopped` + healthcheck; memory tools already degrade gracefully (never raise). |
| Chat history is in-memory | A container restart loses conversation state. Accepted for the POC (Plutus's persistent memory — pins/searches/skills — lives in Supabase and survives). |
| Anthropic-key abuse via public endpoint | NPM Access List in front of the whole site. |
| Disk creep from image rebuilds | Log rotation limits in compose; `docker image prune -f` in the deploy helper script. |

## Verification checklist (post-deploy)

1. Both containers `healthy` in `docker compose ps`.
2. `GET /health` returns 200 with `anthropic_key_set` / `supabase_url_set` true (checked from inside the docker network).
3. `https://realtor.shergillvps.com` prompts for basic auth, then loads the app over valid SSL.
4. A chat message streams **token-by-token** (SSE through NPM confirmed, not one buffered blob).
5. Map, comps table, and trend widgets render (Mapbox token valid in the built bundle).
6. Plutus Knows panel loads pins/searches/skills; pinning from the comps table works (memory REST API through `/api`).

## Out of scope

- Real authentication / multi-user (the `user_id` seam exists; POC stays single-user behind basic auth).
- CI/CD or container registry (build-on-VPS is the loop; GHCR is the documented upgrade path if deploys become frequent).
- Chat-session persistence (schema exists, not wired).
- Self-hosting Supabase — the cloud project remains the database.
