# plan_plaid_web_link_101525

Implement Plaid Link inside the fin agent web app and run imports server‑side. This replaces the need for a dedicated `fin-fetch` CLI for the initial Plaid integration (CLI can be revisited later for headless/CI use).

Status: in progress — Phase 1 complete (2025-10-15).

## Goals

- Web UX: “Connect Bank Account” button launches Plaid Link in the browser.
- After the user completes Link, the server exchanges `public_token` → `access_token` and stores it locally (file‑scoped, mode 600).
- The server fetches transactions for a chosen date range, writes a temp CSV with our canonical columns, runs `fin-enhance` to import/categorize, and returns a summary to the UI.
- Users can connect multiple accounts; the UI shows connected institutions/accounts and exposes a “Refresh Data” action per account.
- Default spend sign remains positive (outflows > 0) to match PDFs and existing analyzers.

## Non‑Goals (v1)

- Incremental cursors (`transactions/sync`). We will refetch for the requested window on demand.
- Persisting access tokens in SQLite. Use a local config file under `~/.finagent/plaid/tokens.json` with strict permissions instead.
- Multi‑tenant server. This is a local, single‑user app.

## High‑Level Flow

1. Client requests `POST /api/plaid/link-token` → server calls Plaid `link/token/create` using `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV` → returns `link_token`.
2. Client initializes Plaid Link with `link_token`; user completes OAuth/consent.
3. Client receives `public_token` → `POST /api/plaid/exchange` → server exchanges via `item/public_token/exchange` → stores `{ item_id, access_token, institution_id }` locally.
4. Client triggers `POST /api/plaid/fetch` with `{ item_id, start, end, accountIds?, autoApprove? }`.
5. Server fetches accounts + `transactions/get` (with paging), normalizes to our CSV columns, writes a temp CSV, runs `fin-enhance` (via child process with project venv), and returns summary + preview.
6. UI updates: show connected institutions/accounts and last sync time; provide “Refresh” per account.

## Server Endpoints (Bun/TypeScript)

- `POST /api/plaid/link-token` → `{ link_token }`
- `POST /api/plaid/exchange` → body: `{ public_token }` → `{ item_id, institution_id, accounts }`
- `GET /api/plaid/items` → list of connected items with institution names
- `GET /api/plaid/accounts?item_id=...` → accounts for an item
- `POST /api/plaid/fetch` → body: `{ item_id, start, end, accountIds?: string[], autoApprove?: boolean }` → returns `{ summary, transactionsPreview, reviewItems }` (same shape as bulk import response)

Implementation notes:
- Use Plaid Node SDK (`plaid` npm package) from the Bun server.
- Store secrets under `~/.finagent/plaid/tokens.json` (mode 600). One file with an array of items: `{ item_id, access_token, institution_id, accounts: [...] }`.
- Reuse `ccsdk/bulk-import.ts` utilities where possible (e.g., CSV parsing of enhanced output). Add a new helper to write a temp CSV and run `fin-enhance`.

## Frontend (React) Changes

- Add a small PlaidLink component that:
  - `POST /api/plaid/link-token` → gets `link_token`.
  - Opens Plaid Link (browser script) and, on success, posts `public_token` to `/api/plaid/exchange`.
  - On completion, refreshes a “Connected Accounts” panel via `/api/plaid/items`.
- Add a “Refresh Data” action that calls `/api/plaid/fetch` with a date range.
- Add minimal UI feedback (spinner, success/error toasts) and show last refreshed time.

## CSV Mapping (Plaid → Our CSV)

Required columns: `date,merchant,amount,original_description,account_name,institution,account_type,account_key`

- `date` ← `transaction.date`
- `merchant` ← `transaction.merchant_name` or fallback `transaction.name`
- `amount` ← positive for outflow if `--sign positive` (default); we’ll convert per Plaid’s `amount` sign if needed
- `original_description` ← `transaction.name`
- `account_name` ← `account.official_name` or `account.name` + `••••{mask}`
- `institution` ← resolve from `item.institution_id` via institutions API; fallback to the ID
- `account_type` ← prefer Plaid `account.subtype`; fallback map from `account.type`
- `account_key` ← `compute_account_key(account_name, institution, account_type)`

## Security

- Keep `PLAID_CLIENT_ID`/`PLAID_SECRET` in `.env` (not in the client). Access tokens stored locally with fs mode 600.
- Never log tokens. Scrub sensitive fields in server logs.
- For OAuth institutions, configure redirect URI if/when needed; initial local testing can use standard non‑OAuth flows.

## Phases & Todos

### Phase 1 — Server plumbing
- [x] Add `plaid` npm dependency and minimal client factory (env‑driven).
- [x] Implement `/api/plaid/link-token` and `/api/plaid/exchange`.
- [x] Add token storage helpers under `~/.finagent/plaid/` with mode 600.
  - Notes: Added `server/plaid/client.ts` singleton; `server/plaid/token-store.ts` writes `tokens.json` with chmod 600; new endpoints live in `server/server.ts` returning JSON with consistent headers.

### Phase 2 — Fetch & CSV
- [x] Implement `/api/plaid/fetch` (transactions paging + accounts/institution lookups).
- [x] Write temp CSV with canonical columns; run `fin-enhance` via child process (stdin or file path).
- [x] Return summary/preview compatible with bulk import UI components.
  - Notes: Added `server/plaid/fetch.ts` to fetch/paginate transactions, derive CSV rows, and reuse `bulkImportStatements`; response mirrors bulk-import `summary` shape with preview/review arrays. Temp CSV written under system tmp dir then removed.
  - Testing: 2025-10-16 sandbox run of `/api/plaid/link-token`, `/api/plaid/exchange`, `/api/plaid/fetch` (autoApprove=true) verified import pipeline and preview output.

### Phase 3 — UI
- [ ] Add PlaidLink component and “Connected Accounts” panel.
- [ ] Add “Refresh Data” action per item/account.
- [ ] Minimal UX polish (loading states, errors, last updated timestamps).

### Phase 4 — Docs & Tests
- [ ] README section: Plaid setup (Sandbox first), required env vars, and UX walkthrough.
- [ ] Unit tests for server helpers (token store, CSV mapping) with JSON fixtures.
- [ ] Manual E2E: connect Sandbox item, fetch a small range, confirm DB rows and UI preview.

## Notes for Future LLMs

- Keep imports stateless from the server’s perspective; SQLite writes remain the job of `fin-enhance`.
- If you later add `transactions/sync`, persist cursors in the same token store file keyed by `item_id`.
- Consider adding an optional metadata column to CSV (e.g., `plaid_transaction_id`) once `fin-enhance` supports storing it to aid dedupe.

---

## Appendix A — Metadata Column for Dedupe (Plaid)

Problem the column solves
- Re‑fetching the same date window from Plaid should not create duplicates. Merchant strings can vary between providers/sources, so fingerprinting by date|amount|merchant|account may not always hold.

Proposal
- Add an optional `metadata` column to the CSV (JSON per row) containing Plaid identifiers:
  - `{"source":"plaid","plaid_transaction_id":"...","plaid_account_id":"...","iso_currency_code":"USD"}`
- fin-enhance parses this JSON and stores it in `transactions.metadata` (already present in schema via migration 004).
- During insert, if `metadata.plaid_transaction_id` matches an existing row, treat as duplicate and update category fields as needed (no new row).

What it does not solve yet
- Cross‑source duplicates (PDF vs Plaid) for the same account and overlapping dates. PDF rows do not have `plaid_transaction_id`. We can address this later with reconciliation heuristics or a “Prefer Plaid for this account” migration.

Implementation notes (small, contained)
- importer: accept optional `metadata` header; parse JSON into `ImportedTransaction`.
- pipeline: merge Plaid metadata with existing LLM metadata before insert.
- models.insert_transaction: before fingerprint dedupe, first probe by `json_extract(metadata, '$.plaid_transaction_id')` when present.
- web server (Plaid fetch): include the JSON `metadata` in generated CSV rows.

Decision
- [ ] Add metadata column now (recommended for reliable re‑fetch dedupe)
- [ ] Defer; rely on current fingerprinting until reconciliation work lands

## Appendix B — Token Storage: File vs SQLite

Default (this plan)
- Store tokens in a local file `~/.finagent/plaid/tokens.json` with fs mode `600`. Keep tokens out of SQLite by default.

Why not SQLite by default?
- Separation of concerns: the DB is the user’s financial ledger and is broadly queryable (`fin-query`, MCP tools). Keeping secrets out reduces accidental exposure (queries, CSV exports, dumps).
- Simpler least‑privilege: the Bun server can manage tokens without granting every DB consumer access to them.
- Operational simplicity: no DB migrations or secret‑column crypto in v1. A file with strict perms is easy to lock down and rotate.
- Backups/portability: users often copy/inspect the DB; leaving tokens out avoids exporting secrets with analytics data.

When SQLite could be preferable
- You want a single store with relational joins (e.g., items ↔ accounts ↔ transactions) and audit trails.
- Multi‑user or remote deployment where central role‑based access control is required.

If we switch to SQLite later
- Add tables like `plaid_items(item_id TEXT PRIMARY KEY, access_token TEXT, institution_id TEXT, created_at, updated_at)` and `plaid_accounts(item_id, account_id, ...)`.
- Encrypt `access_token` at rest (e.g., via OS keychain/Keychain + envelope encryption; avoid storing raw secrets).
- Restrict access: never expose these tables to `fin-query`/MCP tools.

Decision
- [x] Keep file‑based tokens for v1 (local‑first, single‑user)
- [ ] Revisit SQLite storage with encryption for future multi‑user/hosted scenarios
