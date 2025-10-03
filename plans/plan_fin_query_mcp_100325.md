# plan_fin_query_mcp_100325

A plan to expose `fin-query` via the existing Node MCP server in `ccsdk/custom-tools.ts` with safe, structured access for LLM agents, while retaining a strictly‑guarded direct SQL escape hatch.

## Scope

- Provide an MCP server that wraps `fin-query` capabilities: saved queries, ad‑hoc read‑only SQL, schema exploration, and sampling.
- Enforce strong guardrails on ad‑hoc SQL. Keep saved queries as the primary path.
- Ship docs, examples, and tests so agents can reliably chain results.

## Goals

- Stable, typed JSON interfaces over the local SQLite ledger.
- Safe default behavior (read‑only, bounded, single‑statement SELECT only).
- Backwards‑compatible with existing `fin-query` internals (reuse executor, types).

## Non‑Goals

- No write APIs (imports/categorization remain outside MCP).
- No remote DB support in this phase (SQLite only).
- No full SQL IDE features (linting/formatting) beyond minimal validation.

## Deliverables

- Extend `ccsdk/custom-tools.ts` (finance MCP) with new tools (below).
- Guardrailed SQL validator/limiter utility in TypeScript.
- Update `ccsdk/cc-client.ts` allowedTools to include new tools.
- Docs: README section + AGENTS.md notes; example tool calls.
- Optional: `.mcp.json` update only if external clients need discovery (current CCClient wires server programmatically).

## API (MCP Methods in `finance` server)

- `fin_query.list_saved()`
  - Input: none
  - Output: `{ queries: [{ name, description, parameters, path }] }`
- `fin_query.saved(name, params, limit?)`
  - Output: `QueryResult` JSON `{ columns: [str], rows: [[...]], truncated: bool, description?: str, limit_applied: bool, limit_value?: int }`
- `fin_query.schema(table?: str)`
  - Output: `{ database_path, tables: [{ name, columns: [[name, type, required]], indexes: [str], foreign_keys: [[from, table, to]], estimated_row_count: int }] }`
- `fin_query.sample(table, limit=20)`
  - Output: `QueryResult` for `SELECT * FROM table LIMIT {limit}` (safe, quoted, allowlisted table).
- `fin_query.sql(query, params?, limit?)` (escape hatch)
  - Input: SQL string + named params
  - Output: `QueryResult`
  - Guardrails: SELECT/CTE only, single statement, implicit LIMIT, timeout + truncation, read‑only connection.
- Optional (stretch): `fin_query.explain(query, params?)` → `EXPLAIN QUERY PLAN …` when validation passes.

## Guardrails (sql endpoint)

- Read‑only connection via existing `connect(..., read_only=True, apply_migrations=False)` and `PRAGMA query_only=ON`.
- Single statement enforcement; reject batches/semicolons beyond trailing whitespace.
- Allowlist statement kind: `SELECT` or `WITH` (CTE). Reject everything else (PRAGMA, ATTACH, CREATE, INSERT/UPDATE/DELETE, DROP, ALTER, VACUUM, ANALYZE, LOAD_EXTENSION, etc.).
- LIMIT injection: if absent, apply default `LIMIT 200`; cap to max `1000`. Return `truncated=true` when rows exceed limit.
- Progress/timeout: use `sqlite3.Connection.set_progress_handler` to abort long queries (e.g., ~2s wall/step budget); return a structured timeout error.
- Param binding only (no string interpolation). Reject positional `?` if not bound.
- Basic denylist scan for risky tokens inside comments (e.g., `--`, `/* */` with forbidden keywords).
- Result size cap (bytes/rows) to keep MCP payloads small; include `limit_applied` and `limit_value` flags.
- Structured errors surfaced to the LLM for self‑correction.

## Architecture Notes

- Keep the current MCP server in `ccsdk/custom-tools.ts`; add new `tool(...)` handlers under the same `finance` server.
- Shell out to existing CLI:
  - `fin-query saved NAME -p KEY=VALUE --format json`
  - `fin-query schema --format json [--table T]`
  - For `list_saved`, parse `fin_cli/fin_query/queries/index.yaml` directly in Node (YAML → JSON) for richer metadata.
- Add TypeScript helper `validateAndLimitSql(sql: string, defaultLimit=200, hardCap=1000)` to enforce guardrails before calling `fin-query sql`.
- Keep venv activation (`source .venv/bin/activate`) and environment propagation as in existing tools.

## File Map (planned)

- `ccsdk/custom-tools.ts` (update: add new MCP tools + SQL guardrails util)
- `ccsdk/cc-client.ts` (update: allowedTools list)
- `README.md` (update)
- `AGENTS.md` (update)

## Phases & Tasks

### Phase 0 – Finalize spec (this doc)
- [x] Draft plan and API surface
- [ ] Confirm SDK package names and minimum versions
- [ ] Confirm transport (stdio vs websockets) for your agent tooling

### Phase 1 – Server extensions
- [x] Add `fin_query_list_saved` tool (reads YAML manifest)
- [x] Add `fin_query_saved` tool (shells to `fin-query saved ... --format json`)
- [x] Add `fin_query_schema` tool (shells to `fin-query schema --format json`)
- [x] Add `fin_query_sample` tool (allowlisted table name → `fin-query sql ...`)
  - Notes: Implemented in `ccsdk/custom-tools.ts` with ORDER BY per table to show recent rows:
    - transactions: `ORDER BY date DESC, id DESC`
    - accounts: `ORDER BY COALESCE(last_import, created_date) DESC, id DESC`
    - categories: `ORDER BY COALESCE(last_used, created_date) DESC, id DESC`
    - merchant_patterns: `ORDER BY COALESCE(learned_date, usage_count) DESC`
    - category_suggestions: `ORDER BY COALESCE(last_seen, created_at) DESC, id DESC`
    - llm_cache: `ORDER BY COALESCE(updated_at, created_at) DESC`
  - Limit defaults to 20; hard cap 100. Results saved to `~/.finagent/logs/sample-<table>-<ts>.json`.

### Phase 2 – Saved queries and schema
- [ ] Implement `list_saved` via `executor.list_saved_queries`
- [ ] Implement `saved(name, params, limit)` via `executor.run_saved_query`
- [ ] Implement `schema(table?)` via `executor.describe_schema`
- [ ] Implement `sample(table, limit)` with allowlisted identifier quoting

### Phase 3 – SQL escape hatch (guarded)
- [x] Implement `validateAndLimitSql` in TS with:
  - single‑statement check (reject multiple semicolons),
  - allowlist (`SELECT`/`WITH`), denylist (DDL/DML/PRAGMA/ATTACH/etc.),
  - LIMIT injection (default 200, cap 1000),
  - basic comment stripping before checks.
- [x] Add `fin_query_sql` tool using the validator and `-p KEY=VALUE` bindings.
- [x] Remove `search_transactions` MCP tool (redundant with `fin_query_saved`/`fin_query_sql`).

### Phase 4 – Wiring and docs
- [x] Update `ccsdk/cc-client.ts` allowedTools with new finance MCP tools
- [ ] Document environment vars, venv activation, and DB override support

### Phase 5 – Tests
- [x] Unit: validator rejects DDL/PRAGMA/multi‑stmt (ccsdk/__tests__/sql-guard.test.ts)
- [x] Unit: limit injection + max cap behavior (ccsdk/__tests__/sql-guard.test.ts)
- [ ] Unit: timeout via progress handler (skipped for Node wrapper; CLI-level guard not exposed here)
- [ ] Integration: saved query happy paths; schema and sample

### Phase 6 – Docs & examples
- [ ] README: MCP usage, example tool calls
- [ ] AGENTS.md: guidance to prefer `saved` over `sql`, when to use the escape hatch
- [ ] Examples: end‑to‑end JSON payloads for each method

### Phase 7 – Stretch (optional)
- [ ] `explain(query)` endpoint guarded like `sql`
- [ ] Window helpers: `period/month/year` parameter normalization for saved queries
- [ ] Pagination support (`next_page_token` with offset/limit)

## Acceptance Criteria

- Saved queries, schema, and sample work via MCP with deterministic JSON.
- `sql` endpoint rejects non‑SELECT, multi‑statement, and dangerous tokens.
- LIMIT is always applied (default 200, configurable, hard‑cap 1000).
- Long‑running queries are aborted with a clear error.
- Tests cover the guardrails; CI passes.
- Docs describe how/when to use each method and the safety tradeoffs.

## Rollout

- Ship behind `pip install .[mcp]` extra.
- Add `.mcp.json` entry; verify with your LLM client that methods appear and function.
- Keep `fin-query` CLI available for humans and scripts.

## Open Questions

- Which MCP Python SDK package to standardize on for this repo? (Name/version)
- Preferred default LIMIT (200 vs 100)?
- Should `sql` support CTEs that contain multiple SELECTs but still form a single statement? (Proposed: yes.)
- Any tables/columns to hide from schema/sample for privacy?

---

Please review and confirm or adjust:
- Method set and JSON shapes
- Guardrail defaults (LIMITs, timeout, allowlist)
- SDK/transport assumptions
- Stretch items you want prioritized
