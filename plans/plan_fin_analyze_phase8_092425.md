# plan_fin_analyze_phase8_092425

## Architecture Notes
- Promote a reusable analyzer interface (`AnalysisRequest` → `AnalysisResult`) so each module only focuses on its domain logic while the CLI handles option parsing and output negotiation.
- Use a registry (`fin_cli/fin_analyze/registry.py`) mapping analysis slugs to metadata (label, summary, accepted options) and callable factories; this lets `main.py` stay declarative and keeps help/listing in sync with the spec.
- Load transaction data through pandas using a shared utility (`fin_cli/shared/dataframe.py`) that leverages the existing SQLite connection helpers, applies date filters, and returns denormalized frames with category/account context.
- Treat period math centrally (`fin_cli/fin_analyze/temporal.py`) to convert `--month`, `--period`, `--year`, and rolling aliases into explicit `[start, end)` ranges and the prior comparison window when `--compare` is requested.
- Support calendar year rollups (e.g., `--year 2024`) and rolling 12-month windows so analyzers can emit both "last 12 months" and named-year summaries without duplicated logic.
- Express analyzer outputs as dataclasses that can render to Rich tables + narrative text or to deterministic JSON payloads (documented schema, snake_case keys, typed numbers for AI-friendliness).
- Provide guardrails for insufficient data: analyzers should surface `AnalysisError` with exit code `2` when a window has fewer than the minimum observations rather than emitting misleading numbers.
- Reuse shared logging to emit debug traces (e.g., window boundaries, row counts) when `--verbose` is set, aiding future troubleshooting by LLM agents.

## Phase 8A — CLI Dispatcher & Interfaces
- [x] Replace the stub in `fin_cli/fin_analyze/main.py` with a Click command that validates `analysis_type`, resolves it via the registry, parses `--month`, `--period`, `--year`, `--compare`, `--threshold`, and forwards remaining analyzer-specific options.
- [x] Introduce `fin_cli/fin_analyze/types.py` defining `AnalysisRequest`, `AnalysisContext`, `AnalysisResult`, `SeriesPayload`, and custom exceptions for uniform handling.
- [x] Add `fin_cli/fin_analyze/registry.py` enumerating analysis descriptors (slug, title, help text, option set) and exposing helpers for `--help-list` / future docs generation.
- [x] Implement a parser in `fin_cli/fin_analyze/temporal.py` that supports `YYYY-MM`, `Nd`, `Nw`, `Nm`, `--year YYYY`, and a `--last-12-months` alias (mapping to 12 months back from the latest full month), defaulting to the current month when nothing is provided, and deriving prior periods for comparisons.
- [x] Ensure CLI errors out with descriptive messages when both `--month` and `--period` conflict, when `--year` is combined with other windows, or when analyzer-specific flags are misapplied; include Rich-styled `--help` examples pulled from the registry metadata.
  - Notes: 2025-09-25 — Added analyzer registry + option parser, temporal window resolver (month/period/year/12mo) with comparison handling, new types module, and rewired CLI dispatcher with `--help-list` + analyzer-specific help support.

## Phase 8B — Data Access Utilities
- [x] Implement `fin_cli/shared/dataframe.py` with helpers: `load_transactions_frame`, `load_category_totals`, `load_recurring_candidates`, each accepting an `AnalysisContext` and returning pandas DataFrames.
- [x] Ensure loaders join `transactions`, `categories`, and `accounts`, normalize amounts (positive spend, negative income), coerce dates, and attach metadata columns (e.g., `month`, `weekday`, `is_credit` flags).
- [x] Add window helpers returning current and comparison frames, handling sparse datasets (e.g., return empty DataFrame with schema, set a flag for analyzers to short-circuit) while labelling frames with window descriptors like `"last_12_months"` or `"calendar_year_2024"` for downstream reporting.
- [x] Cache schema introspection (column dtypes) to avoid repeated PRAGMA queries, and document any pandas dtype coercions so downstream analyzers stay consistent.
  - Notes: 2025-09-25 — Added pandas-backed data loaders with fixed column order (avoids repeated PRAGMA), derived temporal/amount helpers (`month`, `weekday`, `spend_amount`, etc.), JSON metadata parsing, and a `build_window_frames` helper that includes comparison windows & labels for later analyzers.

## Phase 8C — Trend & Breakdown Analyzers
- [x] Build `fin_cli/fin_analyze/analyzers/spending_trends.py` to compute monthly totals, rolling deltas, trendlines (simple linear regression via numpy), and optional per-category breakdown when `--show-categories` is enabled; include support for rolling 12-month summaries and explicit year rollups in output payloads.
- [x] Implement `fin_cli/fin_analyze/analyzers/category_breakdown.py` calculating category/subcategory totals, percentages of spend, change vs prior period (`--compare`), and honouring `--min-amount` thresholds; ensure outputs capture both monthly and yearly aggregates when the window spans 12+ months.
- [x] Create `fin_cli/fin_analyze/analyzers/category_evolution.py` summarizing new categories, dormant categories, resurging categories, and transaction count changes over the requested period, including specific handling for calendar-year storytelling.
- [x] Each analyzer should emit: (a) structured JSON payload with totals/deltas, (b) Rich table/narrative text highlighting key movements, (c) significance tagging when change exceeds configurable thresholds (default 10%).
  - Notes: 2025-09-25 — Added spending trend/category/evolution analyzers backed by pandas frames, producing JSON + TableSeries + summary lines with threshold-aware significance tagging; registry now dispatches real implementations and CLI captures results for later rendering.

## Phase 8D — Subscription & Anomaly Detection
- [x] Implement `fin_cli/fin_analyze/analyzers/subscription_detect.py` that identifies recurring merchants by cadence (25–35 day gaps), amount stability, and recent activity, marking status (`active`, `inactive`, `price_increase`) and confidence.
- [x] Add detection of new vs cancelled subscriptions, average cycle spend, and flag price increases beyond a configurable delta (default 5%); include annualized spend summaries when the window covers a full year.
- [x] Implement `fin_cli/fin_analyze/analyzers/unusual_spending.py` using median absolute deviation (MAD) or z-score analysis against trailing periods to highlight anomalies by merchant/category; respect `--sensitivity` (1–5) to adjust the threshold multiplier.
- [x] Surface summary narratives (e.g., “Dining up 45% vs baseline”) and include list of new merchants observed within the analysis window.
  - Notes: 2025-09-25 — Added cadence-based subscription heuristics (active/inactive/new, price increase alerts, confidence scoring) plus sensitive anomaly detection with configurable thresholds; spend metrics now treat debits as positive values for trend math.

## Phase 8E — Patterns, Merchant Frequency, Suggestions
- [x] Implement `fin_cli/fin_analyze/analyzers/merchant_frequency.py` producing top merchants by visit count/amount, supporting `--min-visits` and comparison deltas if previous window exists; provide annual visit/amount totals when using year-long windows.
- [x] Implement `fin_cli/fin_analyze/analyzers/spending_patterns.py` aggregating by day-of-week, week-of-month, or exact date (per `--by`) and identifying peak/off-peak periods; ensure reporting gracefully scales when the window spans an entire calendar year.
- [x] Implement `fin_cli/fin_analyze/analyzers/category_suggestions.py` evaluating category overlap (shared merchants, spend volume) to propose merges/splits with overlap percentages and rationale pulled from historical data.
- [x] Share reusable scoring utilities (e.g., Jaccard overlap) under `fin_cli/fin_analyze/metrics.py` to keep heuristics consistent across analyzers.
  - Notes: 2025-09-25 — Added merchant frequency ranking with comparison deltas, day/week/date pattern summaries, overlap-based category suggestions (Jaccard scoring), and regression tests covering the new analyzers.

## Phase 8F — Rendering & Output Contracts
- [x] Create `fin_cli/fin_analyze/render.py` to translate `AnalysisResult` objects into Rich tables (when available) with fallback plain text, and to JSON via `dataclasses.asdict`, ensuring floats are rounded to two decimals for currency fields.
- [x] Extend CLI to respect `--format json` by dumping canonical JSON (sorted keys, explicit metadata section describing parameters used, including window labels like `"period": "last_12_months"` or `"year": 2024`) and append newline for piping.
- [x] Document the JSON schema for each analyzer in `docs/json/fin_analyze.md`, including sample payloads mirrored in tests/fixtures and demonstrating yearly vs rolling outputs.
- [x] Update README/spec snippets to reference new CLI usage patterns, available analysis modules, and examples for yearly rollups.
  - Notes: 2025-09-25 — Added renderer module with Rich/JSON output, CLI now streams results directly, docs include JSON schema reference, and README shows live usage examples.

## Phase 8G — Testing & Fixtures
- [x] Prepare synthetic datasets under `tests/fixtures/analyze/` covering recurring subscriptions, seasonal trends, anomalies, and sparse data edge cases, including fixtures that span multiple years to validate yearly rollups.
- [x] Add unit tests per analyzer module verifying numeric outputs, flagging behaviour in low-data scenarios, and comparison-mode fallbacks when prior data is absent.
- [x] Add CLI integration tests (`tests/fin_analyze/test_cli.py`) using `CliRunner` to exercise dispatch, invalid analyzer names, option parsing, text vs JSON rendering, and exit codes; include cases for `--year 2024` and `--last-12-months`.
- [x] Include regression tests ensuring JSON payload keys remain stable (snapshot or schema comparison) to protect Claude Code integrations.
- [x] Update `pytest` fixtures to seed SQLite databases with shared migrations and fixture data for reproducible analytics runs.
  - Notes: 2025-09-25 — Added fixture loader + dataset suite (`tests/fixtures/analyze/*.json`, `tests/fin_analyze/conftest.py`), expanded analyzer tests (trend/breakdown/evolution, sparse handling, payload contracts), new CLI coverage for yearly & rolling windows, and corrected category totals query to treat debits as spend so tests reflect real analytics behaviour.

## Risks & Dependencies
- Accurate comparison periods depend on consistent timezone-free date handling; mismatches could skew deltas if transactions cross period boundaries.
- Subscription detection heuristics rely on pandas + numpy optional extras—ensure these dependencies are documented and optionally gated behind the `analysis` extra.
- Large datasets may stress in-memory DataFrames; consider chunking or SQL aggregation fallbacks if profiling reveals performance issues.
- Downstream Phase 9 (`fin-export`) assumes analyzers provide stable JSON; any schema drift must be coordinated before release.

## Open Questions
- Should analyzers persist derived metrics (e.g., recurring subscription metadata) for reuse, or remain stateless per execution?
- Do we need localization (currency symbol/locale formatting) beyond USD defaults in text output?
- What minimum sample size should trigger “insufficient data” for anomaly detection—configurable or hard-coded?
