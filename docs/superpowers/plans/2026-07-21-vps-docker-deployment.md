# VPS Docker Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the platform as a two-container Docker stack on the Hostinger VPS (187.77.205.64), served at https://realtor.shergillvps.com through the existing Nginx Proxy Manager with basic-auth protection.

**Architecture:** `realtor-frontend` (nginx:alpine serving the Vite build) + `realtor-backend` (uvicorn/FastAPI) join NPM's existing docker network — no host ports published. NPM path-routes `/` → frontend and `/api` → backend (SSE-safe proxy directives). Supabase stays in the cloud; images build on the VPS from a clone at `/opt/RealtorAgentPlatform`.

**Tech Stack:** Docker + compose, nginx, node:22-alpine, python:3.11-slim, Nginx Proxy Manager (existing), Hostinger DNS API.

**Spec:** `docs/superpowers/specs/2026-07-21-vps-docker-deployment-design.md`

## Prerequisites (user-provided, needed from Task 7 onward)

- SSH access to the VPS (`ssh root@187.77.205.64` or equivalent user/key)
- NPM admin credentials (email + password for the :81 admin UI/API)
- Chosen basic-auth username/password for the public site
- Real secret values (already in local `backend/.env` and `frontend/.env.local`)

## File structure

| File | Responsibility |
|---|---|
| `frontend/src/lib/apiBase.ts` (new) | Single source of the API base URL; `''` = same-origin |
| `frontend/src/lib/apiBase.test.ts` (new) | Unit tests for the base-URL resolution |
| `frontend/src/lib/memoryApi.ts` (edit) | Use `API_BASE` instead of hardcoded localhost |
| `frontend/src/components/chat/ChatPanel.tsx` (edit) | Use `API_BASE` for the SSE fetch |
| `backend/main.py` (edit) | Add production origin to CORS allowlist |
| `backend/tests/test_cors.py` (new) | CORS contract for the production domain |
| `.dockerignore` (new, root) | Keep secrets/venv/node_modules out of build context |
| `frontend/nginx.conf` (new) | SPA serving config inside the frontend container |
| `frontend/Dockerfile` (new) | Multi-stage: workspace npm build → nginx static |
| `backend/Dockerfile` (new) | python:3.11-slim, repo-root layout, non-root, healthcheck |
| `docker-compose.yml` (new, root) | Two services on NPM's external network |
| `.env.example` (new, root) | Compose interpolation vars (build args + network name) |
| `deploy/deploy-realtor.sh` (new) | Pull + rebuild + prune helper (copied to `~` on the VPS) |

Tasks 1–6 are local repo changes (commit each). Tasks 7–12 are VPS-side execution over SSH — no code, but each has exact commands and expected output.

---

### Task 1: Configurable frontend API base

The frontend hardcodes `http://localhost:8000` in two places. Production needs same-origin calls (`/api/...` on the current domain) so NPM can path-route.

**Files:**
- Create: `frontend/src/lib/apiBase.ts`
- Create: `frontend/src/lib/apiBase.test.ts`
- Modify: `frontend/src/lib/memoryApi.ts:2`
- Modify: `frontend/src/components/chat/ChatPanel.tsx:93`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/apiBase.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { resolveApiBase } from './apiBase'

describe('resolveApiBase', () => {
  it('defaults to the local backend when VITE_API_URL is unset', () => {
    expect(resolveApiBase({})).toBe('http://localhost:8000')
  })

  it('returns empty string (same-origin) when VITE_API_URL is empty', () => {
    expect(resolveApiBase({ VITE_API_URL: '' })).toBe('')
  })

  it('returns an explicit URL unchanged', () => {
    expect(resolveApiBase({ VITE_API_URL: 'https://api.example.com' })).toBe(
      'https://api.example.com',
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -w frontend -- src/lib/apiBase.test.ts`
Expected: FAIL — cannot resolve `./apiBase`

- [ ] **Step 3: Implement `apiBase.ts`**

Create `frontend/src/lib/apiBase.ts`:

```ts
// frontend/src/lib/apiBase.ts
type EnvLike = { VITE_API_URL?: string }

// '' (empty string) is a valid, meaningful value: same-origin. The production
// build sets VITE_API_URL='' so all calls hit /api/* on the current domain and
// the reverse proxy routes them to the backend container.
export function resolveApiBase(env: EnvLike): string {
  return env.VITE_API_URL ?? 'http://localhost:8000'
}

export const API_BASE = resolveApiBase(import.meta.env as EnvLike)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -w frontend -- src/lib/apiBase.test.ts`
Expected: 3 tests PASS

- [ ] **Step 5: Use `API_BASE` at both call sites**

In `frontend/src/lib/memoryApi.ts`, replace line 2:

```ts
// before
const BASE = 'http://localhost:8000/api'
// after
import { API_BASE } from './apiBase'

const BASE = `${API_BASE}/api`
```

In `frontend/src/components/chat/ChatPanel.tsx`, add to the imports at the top:

```ts
import { API_BASE } from '../../lib/apiBase'
```

and replace the fetch at line ~93:

```ts
// before
const response = await fetch('http://localhost:8000/api/chat/stream', {
// after
const response = await fetch(`${API_BASE}/api/chat/stream`, {
```

- [ ] **Step 6: Verify no hardcoded URLs remain, full frontend suite + build pass**

Run: `grep -rn "localhost:8000" frontend/src` — Expected: no matches
Run: `npm run test -w frontend` — Expected: all tests pass (12 existing + 3 new)
Run: `npm run build -w frontend` — Expected: tsc + vite build succeed

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/apiBase.ts frontend/src/lib/apiBase.test.ts frontend/src/lib/memoryApi.ts frontend/src/components/chat/ChatPanel.tsx
git commit -m "feat(frontend): configurable API base via VITE_API_URL (same-origin in prod)"
```

### Task 2: CORS allowlist for the production domain

Same-origin path routing means CORS is never actually exercised in production, but the allowlist should still name the real domain (and it protects the localhost-dev-against-prod-API case).

**Files:**
- Modify: `backend/main.py:39-43`
- Create: `backend/tests/test_cors.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_cors.py`:

```python
"""CORS contract: the production domain must be an allowed origin."""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_cors_preflight_allows_production_origin():
    res = client.options(
        "/api/memory/pins",
        headers={
            "Origin": "https://realtor.shergillvps.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200
    assert (
        res.headers["access-control-allow-origin"]
        == "https://realtor.shergillvps.com"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_cors.py -v`
Expected: FAIL — preflight returns 400 (origin not allowed), or the header assertion fails

- [ ] **Step 3: Add the origin**

In `backend/main.py`, edit the `allow_origins` list:

```python
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative frontend port
        "https://*.vercel.app",   # Vercel deployments
        "https://realtor.shergillvps.com",  # VPS production
    ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_cors.py -v`
Expected: 1 test PASS

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_cors.py
git commit -m "feat(backend): allow production origin in CORS"
```

### Task 3: Build context hygiene + frontend image

**Files:**
- Create: `.dockerignore` (repo root)
- Create: `frontend/nginx.conf`
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Create `.dockerignore`**

Both images build with the **repo root as context** (npm workspaces need the root lockfile; the backend needs the `backend.` package layout). Keep secrets and junk out:

```
.git
node_modules
**/node_modules
**/.venv
**/__pycache__
**/.pytest_cache
**/dist
**/.env
**/.env.*
.env
docs
supabase
.claude
.superpowers
.agents
.vscode
PROGRESS.md
```

- [ ] **Step 2: Create `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;

    # Hashed build assets are immutable
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }

    # SPA fallback
    location / {
        try_files $uri /index.html;
    }
}
```

(No `/api` block here — NPM routes `/api` straight to the backend container; this nginx never sees those requests.)

- [ ] **Step 3: Create `frontend/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1
# Build context must be the REPO ROOT (npm workspaces / root lockfile):
#   docker build -f frontend/Dockerfile .

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/
RUN npm ci --workspace frontend
COPY frontend/ frontend/

# Vite reads VITE_* from the process environment at build time
# (these take precedence over any .env file).
ARG VITE_API_URL=""
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_MAPBOX_TOKEN
ENV VITE_API_URL=$VITE_API_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_MAPBOX_TOKEN=$VITE_MAPBOX_TOKEN
RUN npm run build --workspace frontend

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
```

- [ ] **Step 4: Verify the same-origin build locally (no Docker needed)**

Run:

```bash
VITE_API_URL="" npm run build -w frontend
grep -o 'VITE_API_URL:[^,}]*' frontend/dist/assets/index-*.js
```

Expected: build succeeds; grep shows `VITE_API_URL:""` (or backtick-quoted empty string) — the empty value is baked into the bundle, proving the process-env override beats `frontend/.env.local`. Note: a naive grep for `localhost:8000` is NOT a valid check — that literal legitimately survives minification as the dead fallback branch inside `resolveApiBase`; what matters is the env value Vite statically replaced.

- [ ] **Step 5: Commit**

```bash
git add .dockerignore frontend/nginx.conf frontend/Dockerfile
git commit -m "feat(deploy): frontend Docker image (workspace build -> nginx static)"
```

### Task 4: Backend image

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Create `backend/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1
# Build context must be the REPO ROOT so the image keeps the repo-root package
# layout: /app/backend/... — that way `uvicorn backend.main:app` and
# `python -m backend.ingestion.cli` both work exactly as they do in dev.
#   docker build -f backend/Dockerfile .

FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Sanity-check the module path assumption**

Run: `grep -n "backend.main\|sys.path" backend/main.py`
Expected: `main.py` inserts both repo root and backend dir into `sys.path`, and imports use `backend.api.*` — confirming `/app` workdir + `/app/backend` layout resolves.

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat(deploy): backend Docker image (uvicorn, non-root, healthcheck)"
```

### Task 5: Compose stack + root env example

**Files:**
- Create: `docker-compose.yml` (repo root)
- Create: `.env.example` (repo root)

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
# Realtor Agent Platform — production stack for the Hostinger VPS.
# Joins Nginx Proxy Manager's existing docker network (external); no host
# ports are published — NPM is the only ingress.
#
# Requires a root .env (see .env.example) for build args + network name,
# and backend/.env for runtime secrets.

services:
  frontend:
    container_name: realtor-frontend
    build:
      context: .
      dockerfile: frontend/Dockerfile
      args:
        VITE_API_URL: ${VITE_API_URL:-}
        VITE_SUPABASE_URL: ${VITE_SUPABASE_URL}
        VITE_SUPABASE_ANON_KEY: ${VITE_SUPABASE_ANON_KEY}
        VITE_MAPBOX_TOKEN: ${VITE_MAPBOX_TOKEN}
    restart: unless-stopped
    depends_on:
      - backend
    networks:
      - npm
    logging: &logging
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  backend:
    container_name: realtor-backend
    build:
      context: .
      dockerfile: backend/Dockerfile
    env_file: backend/.env
    environment:
      ENVIRONMENT: production
    restart: unless-stopped
    networks:
      - npm
    logging: *logging

networks:
  npm:
    name: ${NPM_NETWORK}
    external: true
```

- [ ] **Step 2: Create root `.env.example`**

```bash
# Root .env — compose interpolation. Copy to .env on the VPS and fill in.
# (Runtime backend secrets live in backend/.env, not here.)

# Name of the docker network Nginx Proxy Manager is attached to
# (find it: docker inspect <npm-container> --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}')
NPM_NETWORK=replace-with-npm-network-name

# Frontend build args. Empty VITE_API_URL = same-origin (production default).
VITE_API_URL=
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_MAPBOX_TOKEN=pk.your-mapbox-token
```

- [ ] **Step 3: Validate compose syntax (skip if local Docker isn't running)**

Run:

```bash
NPM_NETWORK=dummy VITE_SUPABASE_URL=x VITE_SUPABASE_ANON_KEY=x VITE_MAPBOX_TOKEN=x \
  docker compose config --quiet && echo "COMPOSE OK"
```

Expected: `COMPOSE OK`. If Docker isn't installed locally, note it and rely on the VPS-side validation in Task 9.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat(deploy): compose stack on NPM external network"
```

### Task 6: Deploy helper script

**Files:**
- Create: `deploy/deploy-realtor.sh`

- [ ] **Step 1: Create `deploy/deploy-realtor.sh`**

```bash
#!/usr/bin/env bash
# Redeploy the realtor stack: pull latest, rebuild, restart, prune old images.
# Convention: this script is copied to ~/deploy-realtor.sh on the VPS.
set -euo pipefail

cd /opt/RealtorAgentPlatform
git pull --ff-only
docker compose up -d --build
docker image prune -f
docker compose ps
```

- [ ] **Step 2: Make it executable and commit**

```bash
chmod +x deploy/deploy-realtor.sh
git add deploy/deploy-realtor.sh
git commit -m "feat(deploy): VPS redeploy helper script"
git push origin HEAD
```

(Push is required here — the VPS clones from GitHub in Task 8.)

---

## VPS-side execution (Tasks 7–12, over SSH)

> **Gate:** needs the SSH access + NPM admin creds + basic-auth choice from Prerequisites. `<SSH>` below means `ssh root@187.77.205.64` (adjust user if different).

### Task 7: Pre-flight — Docker + NPM network discovery

- [ ] **Step 1: Verify Docker and compose**

Run: `<SSH> 'docker --version && docker compose version'`
Expected: Docker 24+ and Compose v2 (the VPS uses Hostinger's "Ubuntu 24.04 with Docker" template).

- [ ] **Step 2: Find the NPM container and its network**

Run:

```bash
<SSH> 'docker ps --format "{{.Names}}  {{.Image}}  {{.Ports}}"'
```

Expected: a container using an image like `jc21/nginx-proxy-manager` with ports 80/443/81. Then:

```bash
<SSH> 'docker inspect <npm-container-name> --format "{{range \$k, \$v := .NetworkSettings.Networks}}{{\$k}} {{end}}"'
```

Expected: prints the network name (often `<dir>_default`). **Record it — it becomes `NPM_NETWORK` in Task 8.**

- [ ] **Step 3: Check disk headroom**

Run: `<SSH> 'df -h / && free -h'`
Expected: several GB free on / (100 GB disk) and ~8 GB RAM. If disk is tight, run `docker system prune -f` first.

### Task 8: Clone at /opt + env files

- [ ] **Step 1: Clone the repo (public, HTTPS)**

Run: `<SSH> 'git clone https://github.com/abhisheksharma1042/RealtorAgentPlatform.git /opt/RealtorAgentPlatform'`
Expected: clone completes. If a deployment branch is in use rather than main, check it out: `git -C /opt/RealtorAgentPlatform checkout <branch>`.

- [ ] **Step 2: Copy backend secrets**

From the local machine (never through git):

```bash
scp backend/.env root@187.77.205.64:/opt/RealtorAgentPlatform/backend/.env
<SSH> 'sed -i "s/^ENVIRONMENT=.*/ENVIRONMENT=production/" /opt/RealtorAgentPlatform/backend/.env'
<SSH> 'chmod 600 /opt/RealtorAgentPlatform/backend/.env'
```

Expected: file present with `ENVIRONMENT=production`.

- [ ] **Step 3: Create the root `.env`**

On the VPS, create `/opt/RealtorAgentPlatform/.env` with the **real values** (Supabase URL + anon key and Mapbox token copied from local `frontend/.env.local`; network name from Task 7):

```bash
NPM_NETWORK=<network-from-task-7>
VITE_API_URL=
VITE_SUPABASE_URL=<real value>
VITE_SUPABASE_ANON_KEY=<real value>
VITE_MAPBOX_TOKEN=<real value>
```

Then: `<SSH> 'chmod 600 /opt/RealtorAgentPlatform/.env'`

### Task 9: Build, start, verify inside the network

- [ ] **Step 1: Build and start**

Run: `<SSH> 'cd /opt/RealtorAgentPlatform && docker compose up -d --build'`
Expected: both images build (frontend ~2–4 min for npm ci + vite; backend ~1–2 min), containers start.

- [ ] **Step 2: Container health**

Run: `<SSH> 'cd /opt/RealtorAgentPlatform && docker compose ps'`
Expected: `realtor-frontend` Up; `realtor-backend` Up **(healthy)** after ~30 s.

- [ ] **Step 3: Backend health from inside the NPM network**

Run:

```bash
<SSH> 'docker run --rm --network <network-from-task-7> curlimages/curl -s http://realtor-backend:8000/health'
```

Expected: `{"status":"healthy","anthropic_key_set":true,"supabase_url_set":true}` — both flags **must** be true.

- [ ] **Step 4: Frontend serves from inside the network**

Run:

```bash
<SSH> 'docker run --rm --network <network-from-task-7> curlimages/curl -s -o /dev/null -w "%{http_code}\n" http://realtor-frontend:80/'
```

Expected: `200`

- [ ] **Step 5: Install the helper script at ~ (per server convention)**

Run: `<SSH> 'cp /opt/RealtorAgentPlatform/deploy/deploy-realtor.sh ~/deploy-realtor.sh && chmod +x ~/deploy-realtor.sh'`
Expected: `~/deploy-realtor.sh` exists alongside the other project's scripts.

### Task 10: DNS A record

- [ ] **Step 1: Add `realtor.shergillvps.com` → 187.77.205.64**

Use the Hostinger DNS MCP tool (`DNS_updateDNSRecordsV1`, zone `shergillvps.com`): upsert record `name: "realtor"`, `type: A`, `ttl: 300`, content `187.77.205.64`. (Fallback: hPanel → Domains → shergillvps.com → DNS.)

- [ ] **Step 2: Verify propagation**

Run: `dig +short realtor.shergillvps.com @1.1.1.1`
Expected: `187.77.205.64` (retry for a few minutes if empty — must resolve before the Let's Encrypt step).

### Task 11: NPM proxy host, SSL, basic auth

Via the NPM admin API from the VPS (`http://localhost:81`), or the UI with the same values.

- [ ] **Step 1: Get an API token**

```bash
<SSH> 'curl -s -X POST http://localhost:81/api/tokens -H "Content-Type: application/json" \
  -d "{\"identity\":\"<npm-admin-email>\",\"secret\":\"<npm-admin-password>\"}"'
```

Expected: JSON containing `"token": "..."` — export as `$TOKEN` for the next calls. (If the API misbehaves, do Steps 2–4 in the UI at `http://187.77.205.64:81` with the same field values.)

- [ ] **Step 2: Create the Access List (basic auth)**

```bash
<SSH> 'curl -s -X POST http://localhost:81/api/nginx/access-lists \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\":\"realtor-basic-auth\",\"satisfy_any\":true,\"pass_auth\":false,
       \"items\":[{\"username\":\"<chosen-user>\",\"password\":\"<chosen-pass>\"}],\"clients\":[]}"'
```

Expected: JSON with the new access list `id` — record it.
*(UI: Access Lists → Add — name `realtor-basic-auth`, Authorization tab: add the username/password.)*

- [ ] **Step 3: Request the Let's Encrypt certificate**

```bash
<SSH> 'curl -s -X POST http://localhost:81/api/nginx/certificates \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"provider\":\"letsencrypt\",\"domain_names\":[\"realtor.shergillvps.com\"],
       \"meta\":{\"letsencrypt_email\":\"abhishek.sharma1042@gmail.com\",\"letsencrypt_agree\":true}}"'
```

Expected: certificate JSON with an `id` (takes ~15–30 s; DNS from Task 10 must be live). Record the `id`.
*(UI: SSL Certificates → Add — Let's Encrypt, the domain, agree to ToS.)*

- [ ] **Step 4: Create the proxy host with the `/api` custom location**

```bash
<SSH> 'curl -s -X POST http://localhost:81/api/nginx/proxy-hosts \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d @-' <<'JSON'
{
  "domain_names": ["realtor.shergillvps.com"],
  "forward_scheme": "http",
  "forward_host": "realtor-frontend",
  "forward_port": 80,
  "certificate_id": <cert-id>,
  "ssl_forced": true,
  "http2_support": true,
  "hsts_enabled": false,
  "hsts_subdomains": false,
  "block_exploits": true,
  "caching_enabled": false,
  "allow_websocket_upgrade": true,
  "access_list_id": <access-list-id>,
  "advanced_config": "",
  "locations": [
    {
      "path": "/api",
      "forward_scheme": "http",
      "forward_host": "realtor-backend",
      "forward_port": 8000,
      "advanced_config": "proxy_buffering off;\nproxy_cache off;\nproxy_read_timeout 3600s;\nproxy_http_version 1.1;\nproxy_set_header Connection \"\";"
    }
  ],
  "meta": { "letsencrypt_agree": false, "dns_challenge": false }
}
JSON
```

Expected: proxy-host JSON with `"enabled": 1`. The location block's advanced config is **what keeps SSE streaming** — buffering/cache off, hour-long read timeout, HTTP/1.1 with cleared `Connection` header.
*(UI: Hosts → Proxy Hosts → Add — Details: domain `realtor.shergillvps.com` → `http` / `realtor-frontend` / `80`, Block Common Exploits ON, Websockets Support ON; Custom Locations: `/api` → `http` / `realtor-backend` / `8000`, gear icon → paste the five directives above; SSL tab: select the cert, Force SSL, HTTP/2; Access tab: `realtor-basic-auth`.)*

### Task 12: End-to-end verification

- [ ] **Step 1: Auth gate + SSL**

Run: `curl -s -o /dev/null -w "%{http_code}\n" https://realtor.shergillvps.com`
Expected: `401` (basic auth demanded, valid cert — no `-k` needed)

- [ ] **Step 2: App loads with credentials**

Run: `curl -s -u <user>:<pass> https://realtor.shergillvps.com | head -5`
Expected: the Vite `index.html` (contains `<div id="root">`)

- [ ] **Step 3: SSE streams incrementally through both proxies**

Run:

```bash
curl -N -s -u <user>:<pass> -X POST https://realtor.shergillvps.com/api/chat/stream \
  -H "Content-Type: application/json" -d '{"message":"What data coverage do you have?"}'
```

Expected: `data: {...}` events **appear progressively** (agent_message deltas, tool_call, tool_result, then complete) — not one blob after a long pause. A single buffered dump means the Task 11 location directives didn't apply.

- [ ] **Step 4: Browser walkthrough**

At `https://realtor.shergillvps.com` (after basic auth): send a chat message → text streams token-by-token; ask for comps in 75205 → map + table widgets render (Mapbox token valid); pin a property from the table → card widget appears; open Plutus Knows → pins/searches/skills load; Coverage button → coverage map with ZCTA polygons.

- [ ] **Step 5: Restart resilience**

Run: `<SSH> 'cd /opt/RealtorAgentPlatform && docker compose restart && sleep 20 && docker compose ps'`
Expected: both containers back Up/healthy; the site responds again. (Chat history resets — accepted POC behavior; pins/searches/skills persist in Supabase.)
