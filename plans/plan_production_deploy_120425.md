# Plan: Deploy fin-agent to Production (Render.com)

Deploy fin-agent to Render.com for shared use, following claudeboxes patterns.

**Reference repository**: `../claudeboxes` (sibling directory to fin-agent)
- Key files to reference:
  - `claudeboxes/server/server.ts` - auth helpers, security headers, CORS
  - `claudeboxes/agentsdk/websocket-handler.ts` - message-based WebSocket auth
  - `claudeboxes/web/App.tsx` - login screen, localStorage auth persistence
  - `claudeboxes/Dockerfile` - container setup
  - `claudeboxes/docker/entrypoint.sh` - persistent data initialization
  - `claudeboxes/render.yaml` - Render deployment config

## Architecture Overview

```
Render.com Service
├── Docker Container
│   ├── Python 3.11 + fin-cli (all deps)
│   ├── Bun runtime for web server
│   └── Claude Agent SDK
├── Persistent Disk (/var/data)
│   ├── data.db (SQLite - shared)
│   └── imports/ (staging)
└── Environment Variables
    ├── AUTH_PASSWORD
    ├── ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
    └── FINAGENT_DATABASE_PATH=/var/data/data.db
```

---

## Phase 1: Dockerfile

Create multi-stage Dockerfile with both Python and Bun runtimes.

- [x] Create `Dockerfile`
  - Base: `oven/bun:1-debian` (native Bun + Debian for Python)
  - Install Python 3.11, ghostscript, poppler (PDF deps)
  - Install fin-cli with `[all]` optional deps
  - Copy Bun deps and application source
  - Expose port 3000, healthcheck on `/`

**File**: `Dockerfile` (new)

---

## Phase 2: Entrypoint Script

Smart initialization for persistent data handling.

- [x] Create `docker/entrypoint.sh`
  - Create `/var/data/imports` directory
  - Set `FINAGENT_DATABASE_PATH` env var
  - Symlink `~/.finagent/data.db` to persistent disk for CLI compatibility
  - Initialize database if missing
  - Exec main Bun server command

**File**: `docker/entrypoint.sh` (new)

---

## Phase 3: Authentication Layer (claudeboxes approach)

Copy the exact authentication pattern from claudeboxes.

### Server-side (`server/server.ts`)

- [x] Add auth environment variables:
  ```typescript
  const AUTH_PASSWORD = process.env.AUTH_PASSWORD || process.env.BASIC_AUTH_PASSWORD;
  ```

- [x] Add auth helper functions (copy from claudeboxes):
  - `getPasswordFromRequest(req, url)` - checks `?token=` query param and `Authorization: Basic` header
  - `isAuthorized(password)` - validates against `AUTH_PASSWORD`
  - `unauthorizedResponse(origin)` - returns 401 with `WWW-Authenticate` header

- [x] Protect `/api/*` endpoints with auth check (after CORS preflight, before route handling)

- [x] Add security headers object (from claudeboxes):
  ```typescript
  const securityHeaders = {
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "...",
  };
  ```

- [x] Add CORS configuration with `ALLOWED_ORIGINS` env var

- [x] Update `createHeaders()` to include security headers on all responses

### WebSocket Handler (`ccsdk/websocket-handler.ts`)

- [x] Add auth state to WebSocket data: `ws.data.authenticated`

- [x] On connection open:
  - If no `AUTH_PASSWORD` set → reject with `auth_failed`
  - Otherwise → send `auth_required` message

- [x] Handle `auth` message type:
  - Validate `message.password === AUTH_PASSWORD`
  - If valid → set `ws.data.authenticated = true`, send `connected`
  - If invalid → send `auth_failed`, close connection

- [x] Reject all non-auth messages if `!ws.data.authenticated`

### Frontend (`web_client/`)

- [x] Add credentials state and localStorage persistence to `App.tsx`:
  - Store key: `finagent:auth`
  - Load saved password on mount
  - Save password after successful auth
  - Clear on `auth_failed`

- [x] Show login screen when no credentials (password input form)

- [x] In WebSocket `onMessage` handler:
  - On `auth_required` → send `{ type: 'auth', password }`
  - On `connected` → clear error, proceed to chat
  - On `auth_failed` → clear localStorage, show login

- [x] Only enable WebSocket when credentials are set: `enabled: Boolean(credentials)`

**Files**:
- `server/server.ts` (modify)
- `ccsdk/websocket-handler.ts` (modify)
- `ccsdk/types.ts` (modify - add `authenticated` to WSData)
- `web_client/App.tsx` (modify)

---

## Phase 4: render.yaml

Infrastructure-as-code for Render deployment.

- [x] Create `render.yaml`:
  ```yaml
  services:
    - type: web
      name: fin-agent
      runtime: docker
      plan: starter  # $7/mo, 512MB RAM
      disk:
        name: fin-data
        mountPath: /var/data
        sizeGB: 1
      healthCheckPath: /
      envVars:
        - key: AUTH_PASSWORD
          sync: false  # prompt on deploy
        - key: ANTHROPIC_API_KEY
          sync: false
        - key: CLAUDE_CODE_OAUTH_TOKEN
          sync: false
        - key: FINAGENT_DATABASE_PATH
          value: /var/data/data.db
        - key: ALLOWED_ORIGINS
          value: "*"
        - key: NODE_ENV
          value: production
  ```

**File**: `render.yaml` (new)

---

## Phase 5: Configuration Files

- [x] Update `.env.example`:
  ```bash
  # Authentication (required for production)
  AUTH_PASSWORD=

  # Anthropic API (one required)
  ANTHROPIC_API_KEY=
  # CLAUDE_CODE_OAUTH_TOKEN=

  # Database
  FINAGENT_DATABASE_PATH=~/.finagent/data.db

  # CORS (comma-separated origins, or * for all)
  ALLOWED_ORIGINS=*
  ```

- [x] Create `.dockerignore`:
  ```
  .git/
  node_modules/
  .venv/
  .venv-py312/
  statements/
  tests/
  __pycache__/
  .pytest_cache/
  .ruff_cache/
  plans/
  *.md
  !README.md
  .env
  .playwright-mcp/
  ```

**Files**:
- `.env.example` (modify)
- `.dockerignore` (new)

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `Dockerfile` | Create | Multi-stage Python+Bun container |
| `docker/entrypoint.sh` | Create | Persistent data initialization |
| `render.yaml` | Create | Render.com deployment config |
| `.dockerignore` | Create | Exclude dev files from build |
| `server/server.ts` | Modify | Add auth, security headers, CORS |
| `ccsdk/websocket-handler.ts` | Modify | Add WebSocket message-based auth |
| `ccsdk/types.ts` | Modify | Add `authenticated` to WSData type |
| `web_client/App.tsx` | Modify | Add login screen, localStorage auth |
| `.env.example` | Modify | Document new env vars |

---

## Environment Variables (Production)

| Variable | Required | Description |
|----------|----------|-------------|
| `AUTH_PASSWORD` | Yes | Shared password for access |
| `ANTHROPIC_API_KEY` | One of | API key (pay per token) |
| `CLAUDE_CODE_OAUTH_TOKEN` | One of | Claude Max/Pro token |
| `FINAGENT_DATABASE_PATH` | Auto | Set to `/var/data/data.db` |
| `ALLOWED_ORIGINS` | No | CORS whitelist (default: `*`) |

---

## Deployment Steps (after implementation)

1. Push code with new files to GitHub
2. Create Render account, connect repository
3. Create new Web Service → select Docker
4. Set `AUTH_PASSWORD` and `ANTHROPIC_API_KEY` in Render dashboard
5. Deploy and verify at `https://your-app.onrender.com`

---

## Testing Checkpoints

- [x] `docker build -t fin-agent .` succeeds
- [x] `docker run -p 3000:3000 -e AUTH_PASSWORD=test fin-agent` serves UI
- [x] Login screen appears, password required
- [x] Auth persists in localStorage after login
- [x] Chat workflow works after authentication
- [x] API endpoints reject requests without auth
- [x] Security headers present in all responses
- [x] Render deploy succeeds
- [x] End-to-end works in production
