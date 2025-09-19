# Implementation Plan — Financial CLI Tools Suite v0.1

## Architecture Notes & Decisions
- Target Python 3.11+ with a single distributable package `fin_cli` providing entrypoints `fin-extract`, `fin-enhance`, `fin-query`, `fin-analyze`, and `fin-export`.
- Follow the directory layout from the implementation spec (`fin-extract/`, `fin-enhance/`, etc.) with a shared package containing config, database, models, and utilities.
- Persist data in `~/.findata/transactions.db`; manage connections via a shared database module that also drives simple versioned migrations stored in `shared/migrations/`.
- Place global configuration at `~/.finconfig/config.yaml` with environment variable overrides, and expose helper functions for resolving paths and defaults.
- Enforce privacy guarantees: `fin-extract` performs purely local PDF parsing, while `fin-enhance` is the only tool allowed to invoke LLM APIs (with opt-out and caching).
- Reuse common CLI patterns (Click + Rich) across tools; centralize styling, logging, and error handling helpers in `shared/cli.py`.
- Cache LLM categorizations and learned merchant rules in SQLite tables (`merchant_patterns`, `categories`) to reduce repeated API calls.

## Phase 0 — Repository & Tooling Setup
**Notes:** Establish baseline project scaffolding and automation so later phases can focus on features.
- [x] Create `pyproject.toml` with project metadata, shared dependency groups (core vs optional extras like `pdfplumber`, `camelot-py`, `rich`).
- [x] Add `fin_cli/__init__.py` and package scaffolding aligned with the specified directory structure.
- [x] Configure formatting/linting tools (e.g., `ruff`, `black`, `mypy`) and pre-commit hook placeholders to keep code quality consistent.
- [x] Stub CLI entrypoints via `console_scripts` in `pyproject.toml` for each tool to enable immediate invocation during development.
- [x] Document local setup steps in `README.md` (virtualenv usage, installing extras for PDF parsing, environment variables for LLM keys).
  - Notes: 2025-09-19 — `pyproject.toml`, stub CLI modules, `.pre-commit-config.yaml`, `.gitignore`, and README scaffolding created; editable install verified via local venv.

## Phase 1 — Shared Foundation Modules
**Notes:** Build reusable utilities that every CLI depends on before implementing tool-specific logic.
- [ ] Implement `shared/config.py` to load and merge config from default values, YAML file, and environment variables.
- [ ] Implement `shared/logging.py` (or integrate into `shared/utils.py`) for consistent Rich console logging and verbose output toggles.
- [ ] Implement `shared/paths.py` helpers for resolving `~/.findata` and `~/.finconfig` directories, ensuring they are created lazily.
- [ ] Implement `shared/exceptions.py` defining custom exception classes (e.g., `ExtractionError`, `CategorizationError`, `DatabaseError`) used across CLIs.
- [ ] Implement `shared/cli.py` with Click parameter factories, shared options (`--db`, `--config`, `--verbose`, `--dry-run`), and global error handlers.

## Phase 2 — Database Schema & Migration Engine
**Notes:** Create the persistent model layer and utilities for interacting with SQLite.
- [ ] Implement `shared/database.py` providing connection management, context managers, and `run_migrations()` on startup.
- [ ] Scaffold migration files in `shared/migrations/` (e.g., `001_initial.sql`) mirroring the schema from the implementation spec.
- [ ] Implement `shared/models.py` or query helpers for CRUD operations on accounts, categories, transactions, merchant patterns, and schema versions.
- [ ] Add transaction deduplication strategy (hash of `date+amount+merchant+account_id`) to prevent re-importing duplicates.
- [ ] Write initial unit tests covering migration application and model helpers using an in-memory SQLite database.

## Phase 3 — `fin-extract` MVP (Chase Support)
**Notes:** Deliver the first CLI capable of parsing Chase PDFs into CSV and the database pipeline.
- [ ] Implement PDF loader abstraction using `pdfplumber`, including page iteration and table extraction helpers in `fin-extract/parsers/`.
- [ ] Create Chase-specific extractor in `fin-extract/extractors/chase.py` handling table normalization, multi-page joins, and account metadata detection.
- [ ] Implement bank auto-detection heuristics in `fin-extract/extractors/__init__.py` (search for keywords, header patterns).
- [ ] Implement CLI command in `fin-extract/main.py` supporting options from the product spec (output path, account override, no-db, verbose, dry-run).
- [ ] Wire extracted transactions through CSV writer and optional database account upsert when `--no-db` is absent.
- [ ] Add smoke tests using synthetic Chase PDFs (fixtures) to validate extraction results and CLI output formatting.

## Phase 4 — `fin-enhance` Rules-Only Import Baseline
**Notes:** Build CSV ingestion, deduplication, rule-based categorization, and review workflows without LLM integration yet.
- [ ] Implement CSV reader pipeline converting rows into `Transaction` objects, performing validation and normalization (dates, amounts, merchant names).
- [ ] Implement rule-based categorizer leveraging `merchant_patterns` table before introducing LLM usage.
- [ ] Implement transaction deduplication logic with configurable override via `--force` flag.
- [ ] Implement review queue builder identifying transactions lacking confident categorization.
- [ ] Implement interactive review mode (terminal prompts) and JSON export/import flow (`--review-mode json`, `--review-output`, `--apply-review`).
- [ ] Persist categorization decisions, updating `categories`, `merchant_patterns`, and transaction records with method + confidence metadata.
- [ ] Add CLI dry-run path that surfaces planned inserts/updates without committing.

## Phase 5 — LLM-Powered Dynamic Categorization
**Notes:** Introduce GPT-4o-mini integration, batching, caching, and dynamic category creation thresholds.
- [ ] Implement `fin-enhance/categorizers/llm_client.py` handling prompt construction, API calls, retries, and response validation against safety checks.
- [ ] Add caching layer (SQLite table or local JSON) keyed by normalized merchant descriptors to avoid repeat requests.
- [ ] Implement batching logic to group similar uncategorized transactions per API call, respecting token limits and cost considerations.
- [ ] Implement dynamic category suggestion tracker enforcing `min_transactions_for_new` and `auto_approve_confidence` thresholds from config.
- [ ] Enhance review modes to surface LLM-generated suggestions with confidence scores and example transactions.
- [ ] Implement fallback path to resume rules-only mode when LLM is disabled or API errors occur (configurable via `--skip-llm`).
- [ ] Add unit tests with mocked OpenAI responses covering auto-approve, needs-review, and fallback scenarios.

## Phase 6 — Additional PDF Extractors & Robustness
**Notes:** Expand bank coverage and introduce Camelot fallback for complex tables.
- [ ] Implement Bank of America extractor with support for both checking and credit layouts, including header parsing for date ranges.
- [ ] Implement Mercury business checking extractor handling two-line transaction entries if present.
- [ ] Integrate Camelot fallback for PDFs where `pdfplumber` fails, with configuration toggle and documented performance caveats.
- [ ] Extend auto-detection heuristics to differentiate supported banks reliably and emit `UnsupportedFormatError` for unknown inputs.
- [ ] Add regression tests using synthetic BofA and Mercury PDFs to validate multi-page table stitching and currency parsing.

## Phase 7 — `fin-query` CLI & Saved Queries
**Notes:** Deliver database exploration capabilities for both ad-hoc SQL and curated queries.
- [ ] Implement CLI command with mutual exclusive options (`sql`, `--saved`, `--list`, `--schema`) using Click groups.
- [ ] Create `fin-query/queries/` directory populated with SQL templates referenced by saved query names (e.g., `recent.sql`, `summary.sql`).
- [ ] Implement renderer that outputs Rich tables by default with optional TSV/CSV/JSON serialization.
- [ ] Implement schema introspection command that prints table definitions and indexes from SQLite pragma data.
- [ ] Add tests ensuring saved queries accept parameters (`--month`, `--limit`) and produce expected output shapes.

## Phase 8 — `fin-analyze` Analysis Modules
**Notes:** Provide analytical computations leveraging pandas and reusable query helpers.
- [ ] Implement dispatcher in `fin-analyze/main.py` mapping analysis types to analyzer modules.
- [ ] Build analyzers for spending trends, category breakdown, subscription detection, anomaly detection, merchant frequency, spending patterns, category evolution, and category suggestions as described in the product spec.
- [ ] Share data access utilities (e.g., `shared/dataframe.py`) to pull transactions into pandas DataFrames efficiently.
- [ ] Implement comparison logic for `--compare` option, including period-over-period calculations and significance thresholds.
- [ ] Provide both text (Rich tables + summaries) and JSON outputs, ensuring JSON schema is AI-friendly and documented.
- [ ] Add targeted unit/integration tests per analyzer using fixture datasets to verify calculations and edge cases (insufficient data, zero transactions).

## Phase 9 — `fin-export` Markdown Reporting
**Notes:** Transform analytical outputs into human-readable Markdown with templating support.
- [ ] Implement CLI command orchestrating underlying analyses to gather data for requested sections.
- [ ] Create default Markdown templates in `fin-export/templates/` with Jinja2 or lightweight string formatting for summary, categories, subscriptions, patterns, unusual, merchants, trends, evolution sections.
- [ ] Implement section registry allowing selective export via `--sections` and multi-month context via `--period`.
- [ ] Support `--output` to write files and default to stdout, ensuring directories are created as needed.
- [ ] Encode alert indicators (e.g., ⚠️, ✅, ❌) and ensure ASCII fallbacks for environments without emoji support.
- [ ] Add tests rendering sample reports to verify section inclusion/exclusion and placeholder replacement.

## Phase 10 — Testing, Tooling, and Distribution
**Notes:** Final hardening before release and agent integration.
- [ ] Build synthetic PDF and CSV fixtures in `tests/fixtures/` representing all supported banks and edge cases.
- [ ] Implement CLI integration tests using `pytest` to invoke entrypoints via `CliRunner` (Click) and validate exit codes + key outputs.
- [ ] Add load/cost tests for the LLM categorizer using mocked responses to ensure batching logic stays within rate limits.
- [ ] Document testing instructions and how to run targeted suites (unit vs integration vs LLM-mocked) in README or CONTRIBUTING.
- [ ] Configure packaging (versioning, optional extras) and publish instructions (`pip install -e .`, PyPI workflow outline).
- [ ] Provide Claude Code orchestration examples in docs, including sample scripts leveraging JSON review flows.

## Supporting Workstreams
- [ ] Create developer-focused documentation in `docs/` detailing architecture, configuration schema, and extension points (adding new banks, new analyzers).
- [ ] Establish telemetry-free logging defaults and add verbose tracing hooks primarily for debugging.
- [ ] Define security review checklist (ensure API keys not logged, confirm local-only processing for PDFs).
- [ ] Prepare guardrails for future expansion (e.g., placeholder for local LLM provider integration, OCR roadmap notes).

## Open Questions & Follow-Ups
- [ ] Prioritize bank support order beyond Chase: confirm if BofA + Mercury are required before initial release or can slip.
- [ ] Clarify whether multiple LLM providers must be abstracted immediately or if OpenAI-only is acceptable for v0.1.
- [ ] Decide on seeding baseline categories vs starting empty to shorten first-run review time.
- [ ] Confirm JSON review contract requirements for Claude Code (schema stability, versioning strategy).
- [ ] Determine whether additional export formats (PDF/HTML) should be scheduled post-v0.1 or scoped into current export tool.
