# plan_fin_query_092425

## Architecture Notes
- Leverage existing `fin_cli.shared.database` context managers to provide read-only SQLite connections (enforce `immutable=1` pragmas when possible).
- Route all CLI entrypoints through `fin_cli/fin_query/main.py`, exposing subcommands `sql`, `saved`, `list`, and `schema` per Phase 7 scope.
- Store curated SQL templates under `fin_cli/fin_query/queries/` with `.sql` extension and `{name}.sql` convention; ensure parameter substitution uses safe bindings (no string formatting).
- Centralize output rendering via a helper module (e.g., `fin_cli/fin_query/render.py`) capable of Rich tables and serialized formats (TSV/CSV/JSON).
- Keep saved query metadata in a manifest (e.g., `queries/index.yaml`) containing descriptions, default params, and validation hints for CLI usage.
- Respect configuration overrides (`--db`, environment) using `shared.config` resolution, and log executed queries with redaction of bound parameters when verbose.

## Phase 1 — CLI Structure & Context
- [x] Flesh out `fin_cli/fin_query/main.py` to wire Click commands, context objects, and shared options (`--db`, `--config`, `--verbose`).
- [x] Implement argument/option validation (mutually exclusive flags, required params for subcommands) and ensure helpful error messaging.
- [x] Ensure ad-hoc `sql` subcommand wraps execution in try/except to surface database errors with context while preserving tracebacks when `--verbose`.
  - Notes: 2025-09-24 — Click group now runs without migrations, supports per-command DB override, parameter parsing, common error handling, and placeholder render/executor hooks guarded for verbose tracebacks.

## Phase 2 — Query Execution Layer
- [x] Build `fin_cli/fin_query/executor.py` with helpers to obtain read-only SQLite connections and execute parameterized queries.
- [x] Support parameter binding for `--sql` (e.g., `--param key=value`) and saved query defaults, using named placeholders to avoid SQL injection.
- [x] Add pagination/limit enforcement for safety (configurable default limit, override via CLI flag with explicit opt-out).
  - Notes: 2025-09-24 — Added read-only connection helper leveraging shared database module, enforced default fetch limit (200 rows) with truncation detection, surfaced SQLite errors as `QueryError`, and set up saved query scaffolding (manifest loader, parameter coercion) ahead of Phase 3.

## Phase 3 — Saved Query Catalog
- [x] Create `fin_cli/fin_query/queries/index.yaml` describing saved queries (name, file path, description, expected params, default values).
- [x] Implement loader that validates manifest, ensures matching SQL template files, and supports environment variable conditions if needed.
- [x] Build CLI `saved` and `list` subcommands to reference the manifest, render descriptions, and supply defaults.
  - Notes: 2025-09-24 — Added initial manifest + SQL templates (recent_transactions, category_summary, uncategorized). Executor now resolves defaults, coerces types, and surfaces friendly “available queries” hints when names are unknown; CLI reuses existing rendering hooks.

## Phase 4 — Output Rendering Utilities
- [x] Implement `fin_cli/fin_query/render.py` providing Rich table rendering plus TSV/CSV/JSON serializers with consistent column ordering.
- [x] Detect when result sets are large and provide truncation warnings or prompt for `--limit` adjustments.
- [x] Include optional `--raw` flag (or reuse `--format`) to bypass Rich styling for piping into other tools.
  - Notes: 2025-09-24 — Added Rich-based table renderer with CSV/TSV/JSON serializers, integrated truncation warnings when executor caps output, and introduced `--format table|csv|tsv|json` handling that falls back to plain text when Rich unavailable.

## Phase 5 — Schema Introspection & Metadata Commands
- [x] Implement `schema` subcommand using SQLite PRAGMA queries to list tables, columns, indexes, and foreign keys in a readable format.
- [x] Provide optional `--table name` filter to inspect a single table, including additional metadata (row counts via fast estimation).
- [x] Add `--json` output variant for schema details to aid downstream automation.
  - Notes: 2025-09-24 — `fin-query schema` now surfaces table/index/fk info with Rich rendering or JSON payloads; table filters validate existence and row counts are included via COUNT(*); verified CLI runs for default, filtered, and JSON modes.

## Phase 6 — Tests & Documentation
- [x] Add unit tests covering executor parameter binding, saved query loading validation, and renderer output (Rich table snapshot or textual assertions).
- [x] Write CLI integration tests using `CliRunner` with an in-memory SQLite fixture seeded via shared migrations.
- [x] Update `README.md` (or dedicated docs) with usage examples, saved query catalog overview, and best practices for extending queries.
- [x] Document logging/verbose behaviour and safety considerations (read-only connections) in code comments for future LLM maintainers.
  - Notes: 2025-09-24 — Added `tests/fin_query/` suite for executor, render, and CLI coverage (parameter binding, manifest validation, CSV/JSON formatting). README now documents typical `fin-query` commands/formats, and inline comments clarify read-only connection policy plus truncation warnings.

## Notes
- Coordinate with Phase 8 analyzers to ensure saved queries align with analytics expectations.
- Consider stubbing hooks for future permission layers (e.g., restricting certain tables) but defer enforcement unless requirements emerge.
