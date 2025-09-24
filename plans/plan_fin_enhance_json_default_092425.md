# plan_fin_enhance_json_default_092425

## Phase 1 — Strategy & Cleanup Targets
- [x] List files touched by interactive-mode work to revert or adjust (main.py, pipeline.py, review plan, tests, interactive module).
  - Notes: 2025-09-24 — Impacted files: fin_cli/fin_enhance/main.py, pipeline.py, interactive.py, tests/fin_enhance/test_cli_enhance.py, plans/plan_fin_enhance_interactive_092425.md, plans/fin_cli_implementation_plan.md, AGENTS.md, CLAUDE.md.
- [x] Confirm database schema elements tied to `needs_review` and plan migration removal.
  - Notes: 2025-09-24 — `needs_review` defined in 001_initial.sql, referenced throughout models, pipeline, hybrid categorizer; plan to drop column via new migration.
- [x] Define revised CLI surface (no `--review-mode`, optional `--confidence`, `--review-output`, `--apply-review`).
  - Notes: 2025-09-24 — CLI flow: default import categorizes with config threshold; `--confidence` overrides threshold; `--review-output <file>` writes unresolved items; `--apply-review <file>` ingests decisions; no other review modes exposed.

## Phase 2 — Revert Interactive Mode Footprint
- [x] Remove `fin_cli/fin_enhance/interactive.py` and associated imports/usages.
  - Notes: 2025-09-24 — Deleted module and will strip related imports while rewriting CLI/pipeline.
- [x] Revert plan/test/docs additions created solely for interactive mode (plan file, plan checkbox, test case).
  - Notes: 2025-09-24 — Removed interactive plan file, excised interactive test case, updating implementation plan to reflect JSON-only strategy.
- [x] Restore CLI help/output messaging to non-interactive phrasing.
  - Notes: 2025-09-24 — Updated CLI help string and log messages to emphasize JSON export path.

## Phase 3 — Simplify Categorization Flow
- [x] Update pipeline/categorizer/models to eliminate `needs_review` flags and rely on `category_id` presence only.
  - Notes: 2025-09-24 — Revised pipeline, hybrid categorizer, and models to remove DB `needs_review` usage while retaining outcome flags for review queues.
- [x] Introduce migration to drop `needs_review` column from `transactions` table while preserving data.
  - Notes: 2025-09-24 — Added migration 003 to rebuild transactions table without `needs_review` and recreate indexes.
- [x] Adjust CLI entry logic to always run hybrid import, emit review JSON when `--review-output` supplied, and remove review mode flag.
  - Notes: 2025-09-24 — Simplified CLI options, removed `--review-mode`, default tip nudges to `--review-output`, and warns when unresolved remain.

## Phase 4 — Tests & Docs
- [x] Update unit/integration tests to reflect new CLI options and review JSON behavior.
  - Notes: 2025-09-24 — Refreshed CLI, categorizer, and importer tests for JSON-first flow and new CSV headers.
- [x] Run relevant pytest suite (fin_enhance) inside `.venv` and ensure green.
  - Notes: 2025-09-24 — `.venv` python -m pytest tests/fin_enhance/test_cli_enhance.py tests/fin_enhance/test_categorizer.py tests/fin_enhance/test_hybrid_categorizer.py`.
- [x] Document new default flow in specs/README if needed and update master plan checkboxes.
  - Notes: 2025-09-24 — Updated product & implementation specs, README tips, agent guidelines, and master plan to reflect JSON-first workflow.

## Notes
- JSON review export becomes default follow-up path; auto classification uses config or `--confidence` override.
- On import, unresolved transactions stay uncategorized; agents fetch them via `--review-output`.
- Migration must be idempotent and safe for existing DBs.
