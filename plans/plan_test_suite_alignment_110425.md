# plan_test_suite_alignment_110425

## Phase 1 – Legacy CLI teardown
- [x] Delete deprecated CLI suites (`tests/fin_extract`, `tests/fin_enhance`, `tests/fin_export`) and associated fixtures to reduce surface area.
- [x] Remove legacy command references from pytest discovery (e.g. prune imports, conftest helpers, tox/nox targets) so runs stay green after deletions.
- [ ] Update docs (README, CONTRIBUTING/testing sections) to note the removal and point to archival history if needed.

## Phase 2 – Active CLI coverage upgrades
- [x] `fin-scrub`: added synthetic fixture (`tests/fixtures/scrubbed/sample_raw_statement.txt`) and regression tests (`tests/fin_scrub/test_scrub.py`) covering detector redactions, CLI output/report handling, custom config overrides, and missing-input failure behaviour (scrubadub mocked to avoid textblob dependency).
- [x] `fin-query`: expanded CLI coverage (`tests/fin_query/test_cli.py`) for `sql` TSV output + limit warnings, empty/malformed params, `list` catalog output, and `schema --db` overrides with JSON parsing.
- [x] `fin-analyze`: extended CLI coverage (`tests/fin_analyze/test_cli.py`) for `--help-list`, analyzer-specific help passthrough, and invalid period error handling to surface `AnalysisConfigurationError` messages.
- [x] `fin-edit`: added CLI tests (`tests/fin_edit/test_fin_edit.py`) for `--create-if-missing`, invalid metadata errors, `--apply` + `--dry-run` precedence, and selector validation.

## Phase 3 – Shared library regression tests
- [x] Added tests for `fin_cli.shared.cli` (`common_cli_options`, `handle_cli_errors`) ensuring dry-run defaults, verbosity toggles, and error wrapping remain intact.
- [x] Backfilled `fin_cli.shared.importers` unit tests for CSV/enriched loaders (BOM handling, missing columns, invalid metadata) without going through CLI layers.

## Phase 4 – Skill workflow smoke tests
- [x] Added an integration smoke test (`tests/statement_processor/test_pipeline_smoke.py`) that runs preprocess → postprocess → categorize with synthetic scrubbed input and ensures prompts/enriched outputs are generated.

## Phase 5 – Validation & tooling
- [ ] Run `pytest` (full suite + targeted markers) after removals/additions and capture runtime deltas for historical notes.
- [ ] Update documentation (README/testing guidelines) with new fixtures, commands, and how to run skill smoke + CLI suites.

## Notes & Open Questions
- Synthetic scrubbed text should be generated from deterministic sample data (e.g. seeded transactions) and checked into `tests/fixtures`, never sourced from personal ledgers or `~/.finagent` real runs.
- All new tests must rely on temp directories and in-memory SQLite to avoid touching user data paths.
- Validate that no CI or tooling scripts still reference the removed legacy suites before committing the teardown.
- 2025-11-04: Removed `tests/fin_extract`, `tests/fin_enhance`, and `tests/fin_export`; no remaining pytest plugins or imports reference these modules.
- 2025-11-04: `tests/fin_scrub/test_scrub.py` exercises detector coverage, CLI error paths, and config overrides using a synthetic fixture while patching `_apply_scrubadub` to avoid textblob dependency.
- 2025-11-04: Added `fin-query` CLI assertions for `sql` TSV output, empty/malformed params, saved query catalog, and `schema` JSON output under DB overrides.
- 2025-11-04: Added fin-analyze CLI coverage for help flows and period validation errors.
- 2025-11-04: Added fin-edit CLI coverage for create-if-missing, metadata validation, dry-run precedence, and selector errors.
- 2025-11-04: Added shared CLI/importer regression tests to guard decorators and CSV parsing helpers.
- 2025-11-04: Added statement-processor pipeline smoke test covering preprocess → postprocess → categorize.
