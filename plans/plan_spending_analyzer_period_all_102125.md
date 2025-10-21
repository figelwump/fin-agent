# plan_spending_analyzer_period_all_102125

## Architecture Notes
- `fin_cli/fin_analyze/temporal.py` resolves window flags; extend it so `"all"` spans the dataset by querying SQLite via `AppConfig` when available, falling back gracefully if no transactions exist.
- Update shared analyzer error messaging in `fin_cli/fin_analyze/analyzers/` to mention the new longer-period suggestions to keep agent guidance consistent.
- Expand CLI tests in `tests/fin_analyze/test_cli.py` (and related fixtures if needed) to cover the new `"all"` period while keeping existing behaviours intact.

## Phase 1 — Window Resolution Updates
- [x] Audit usages of `temporal.resolve_windows` (CLI + exporter) to confirm they can supply configuration for DB-bound period resolution.
  - Notes: 2025-10-21 — Updated CLI and exporter call sites to pass `cli_ctx.config`, keeping other invocation signatures unchanged.
- [x] Extend `_from_period` to accept `"all"` by computing dataset bounds from SQLite (min/max transaction date) and produce a descriptive window label.
  - Notes: 2025-10-21 — `_from_period` now recognises `"all"` and uses a new helper hitting SQLite for MIN/MAX dates, falling back to a labelled empty window when no transactions exist.
- [x] Validate comparison window behaviour for `"all"` (either support or guard) to avoid pathological spans.
  - Notes: 2025-10-21 — Guarded `--compare` with `"all"` by raising `AnalysisConfigurationError` to avoid undefined preceding windows.

## Phase 2 — User Messaging Polish
- [x] Update analyzer error messages referencing longer periods so they read `6m, 12m, 24m, 36m, or all`.
  - Notes: 2025-10-21 — Normalised guidance across spending/category analyzers to include 24m/36m alongside `all`.
- [x] Check ancillary docs or prompts for the old guidance and refresh as needed.
  - Notes: 2025-10-21 — Searched repo for the old phrase; no doc updates required.

## Phase 3 — Tests & Validation
- [x] Add CLI coverage for `fin-analyze category-breakdown --period all --format json` ensuring the payload delivers the expected window label/data.
  - Notes: 2025-10-21 — Added CLI regression test validating window label + JSON payload.
- [x] Consider fixture tweaks or targeted unit coverage for empty-dataset handling with `"all"` to guarantee graceful errors.
  - Notes: 2025-10-21 — Added `empty` fixture and test asserting the new messaging surfaces 24m guidance.
- [x] Run `pytest` (with `.venv` activated) to confirm the suite stays green.
  - Notes: 2025-10-21 — `pytest tests/fin_analyze/test_cli.py` passes via activated virtualenv.

## Notes & Open Questions
- When the database has zero transactions, `"all"` should produce an empty window result (0 transactions) without falling back to another period.
- Decide whether `"all"` should allow `--compare`; if supported, ensure resulting time windows remain within valid date bounds.
