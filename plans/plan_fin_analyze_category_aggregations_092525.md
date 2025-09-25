# plan_fin_analyze_category_aggregations_092525

## Architecture Notes
- Reuse the existing pandas loader stack (`fin_cli/shared/dataframe.py`) but add helpers that can aggregate transactions by arbitrary grain (`month`, `quarter`, `year`) and filter on category/subcategory prior to aggregation to avoid post-hoc slicing in analyzers.
- Extend analyzer registry with a new descriptor (likely `category-timeline`) that accepts flags such as `--category`, `--subcategory`, `--interval`, and `--include-merchants` to toggle merchant-level drilldowns.
- Introduce shared formatting utilities so both timeline and merchant-frequency analyzers can inherit consistent currency rounding, percent calculations, and label generation for time buckets.
- Consider caching commonly requested aggregations inside the analysis context (window frame metadata) to avoid recomputing monthly groupings when both timeline and merchant analyzers request the same data.
- Ensure JSON schemas remain backward compatible; add explicit versioning in payload metadata when introducing new keys or nested structures.
- Respect the CLI's existing `--period` flag so users can request rolling windows without specifying discrete months/years.

## Phase 1 — Data Access Enhancements
- [x] Audit `build_window_frames` / `load_transactions_frame` to confirm they expose sufficient columns for grouping by interval and category filters.
- [x] Implement utility (e.g., `prepare_grouped_spend(frame, interval)`) that returns grouped DataFrames with spend, income, net totals, and transaction counts.
- [x] Add helper for filtering frames by category & subcategory (case-insensitive) and expose merchant lists scoped to that filter for downstream analyzers.
- [x] Document new helpers in docstrings so future analyzers can reuse them without re-deriving pandas operations.
  - Notes: 2025-09-25 — Added `filter_frame_by_category`, `summarize_merchants`, and `prepare_grouped_spend` in `fin_cli/shared/dataframe.py` with docstrings plus interval-aware aggregation logic (month/quarter/year). Existing dataframe loader already carried required columns; verified via targeted analyzer test.

## Phase 2 — Category Timeline Analyzer
- [x] Create `fin_cli/fin_analyze/analyzers/category_timeline.py` calculating spend per interval with optional compare window and cumulative totals.
- [x] Support CLI flags `--interval` (`month`, `quarter`, `year`), `--category`, `--subcategory`, and `--top-n` (limit output rows).
- [x] Provide Rich table + JSON payload, including both aggregated metrics and a metadata block describing the applied filters and interval boundaries.
- [x] Emit warnings or short-circuit when the requested category/subcategory has insufficient data (< configurable threshold).
  - Notes: 2025-09-25 — Added Category Timeline analyzer using new dataframe helpers; exposes interval/category filters, top-N limiting (latest intervals), optional merchant listings, comparison deltas, cumulative spend, and raises AnalysisError when filters yield zero rows. Tests cover month/quarter usage, merchant output, and JSON schema expectations.

## Phase 3 — Category-Scoped Merchant Frequency
- [x] Update `merchant_frequency.analyze` (or extract helper) to accept optional category/subcategory filters so it can be reused by the new analyzer.
- [x] Expose a `--category` / `--subcategory` option through the CLI registry, wiring through to the analyzer options parsing.
- [x] Ensure JSON payload reflects the filter context (e.g., include `"filter": {"category": "Food & Dining", "subcategory": "Restaurants"}`) and that comparisons respect filtered datasets.
  - Notes: 2025-09-25 — Merchant frequency analyzer now accepts category/subcategory filters, registry exposes matching CLI flags, JSON payload includes filter metadata, and tests guard filtered behaviour. Comparison windows respect the same filters.

## Phase 4 — Registry, CLI, and Docs
- [x] Register the new analyzer in `fin_cli/fin_analyze/registry.py`, including alias, help text, and option descriptors for `--interval`, `--category`, etc.
- [x] Update CLI help (`--help-list`) and README/docs to showcase sample usage for timeline aggregation and category-filtered merchant frequency.
- [x] Extend `docs/json/fin_analyze.md` with schema for the new payloads and note the additional filter context fields.
  - Notes: 2025-09-25 — Registry now exposes `category-timeline` with interval/category flags plus new `--category/--subcategory` for merchant-frequency; README illustrates usage and docs/json updated with payload schema (including filter metadata and timeline structure).

## Phase 5 — Testing & Fixtures
- [x] Expand fixtures (or add new ones) covering multiple years and diversified categories for validating interval aggregations.
- [x] Add unit tests for the new analyzer verifying month/quarter/year rollups, category filtering, comparison deltas, and insufficient-data behaviour.
- [x] Add tests ensuring merchant frequency respects category filters and preserves prior behaviour when no filter is provided.
- [x] Add CLI integration tests for `category-timeline` with various intervals and for merchant frequency invoked with `--category/--subcategory`.
- [x] Update JSON contract tests to include the new filter metadata and timeline payload structure.
  - Notes: 2025-09-25 — Reused `spending_multi_year` fixture for multi-interval validation, added analyzer + CLI tests (including `--period` coverage) and contract assertions ensuring filter metadata and timeline payload keys are stable.

## Risks & Open Questions
- Determine whether interval calculations should align strictly to calendar boundaries (calendar months/years) or respect custom periods passed via `--period`.
- Decide on performance strategy for large datasets; grouping by interval may require indexes or chunking if frames become large.
- Validate naming collisions between existing analyzer flags and new options (e.g., `--category` already used elsewhere?).
- Confirm desired default interval when none is provided (likely month) and whether cumulative totals should be opt-in.
