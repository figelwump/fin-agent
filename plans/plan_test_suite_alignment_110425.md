# plan_test_suite_alignment_110425

## Phase 1 – Legacy CLI teardown
- [x] Delete deprecated CLI suites (`tests/fin_extract`, `tests/fin_enhance`, `tests/fin_export`) and associated fixtures to reduce surface area.
- [x] Remove legacy command references from pytest discovery (e.g. prune imports, conftest helpers, tox/nox targets) so runs stay green after deletions.
- [ ] Update docs (README, CONTRIBUTING/testing sections) to note the removal and point to archival history if needed.

## Phase 2 – Active CLI coverage upgrades
- [x] `fin-scrub`: added synthetic fixture (`tests/fixtures/scrubbed/sample_raw_statement.txt`) and regression tests (`tests/fin_scrub/test_scrub.py`) covering detector redactions, CLI output/report handling, custom config overrides, and missing-input failure behaviour (scrubadub mocked to avoid textblob dependency).
- [x] `fin-query`: expanded CLI coverage (`tests/fin_query/test_cli.py`) for `sql` TSV output + limit warnings, empty/malformed params, `list` catalog output, and `schema --db` overrides with JSON parsing.
- [ ] `fin-analyze`: add tests for `--help-list`, analyzer-specific `--help`, CSV rendering with wide tables, and failure propagation when an analyzer raises `AnalysisConfigurationError`.
- [ ] `fin-edit`: cover `--create-if-missing` success path, invalid metadata JSON handling, precedence when both `--apply` and `--dry-run` are passed, and basic validation of mutually exclusive transaction selectors.

## Phase 3 – Shared library regression tests
- [ ] Add tests for `fin_cli.shared.cli` (`common_cli_options`, `handle_cli_errors`) ensuring dry-run defaults, verbosity toggles, and error wrapping remain intact.
- [ ] Backfill `fin_cli.shared.importers` unit tests for CSV/enriched loaders (including BOM handling, missing columns, bad JSON blobs) without going through CLI layers.

## Phase 4 – Skill workflow smoke tests
- [ ] Build an integration smoke test that fabricates a scrubbed text transcript (based on `.claude/skills/statement-processor` prompt expectations) and runs preprocess → postprocess → categorize scripts end-to-end, confirming assumptions about scrub output remain valid.

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
