# plan_fin_enhance_auto_mode_092425

## Phase 1 – Design & CLI Surface
- [x] Document desired `--auto` semantics: bypass review pipeline, auto-assign even low confidence/new categories, and suppress review artifacts.
- [x] Identify touch points (CLI option wiring, hybrid categorizer options, import pipeline, stats) and testing implications.

## Phase 2 – Implementation
- [x] Extend `CategorizationOptions` and hybrid logic to support forced auto assignment (create categories when needed, mark outcomes as finalized, persist metadata).
- [x] Wire `--auto` flag through CLI/pipeline (skip review file handling, adjust stats, ensure dry-run parity).

## Phase 3 – Verification
- [x] Add/extend unit tests covering forced auto assignment, CLI flag behavior, and ensure review queue is empty in auto mode.
- [x] Run full pytest suite to confirm no regressions.

### Notes

- Added `--auto` flag wiring through CLI/pipeline; Hybrid categorizer force branch auto-creates categories and disables review queue; tests updated (47 passing).
- Expect updates in `fin_cli/fin_enhance/{main.py,categorizer/hybrid.py,pipeline.py}`, `fin_cli/shared/models.py` (if needed for stats), and tests under `tests/fin_enhance/`.
- Auto mode should still respect dedupe/LLM skip flags; when LLM disabled we may still get review if no rules match.
