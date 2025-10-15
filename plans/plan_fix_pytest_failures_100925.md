# plan_fix_pytest_failures_100925

## Phase 1 – Analyze Failures
- [x] Re-run targeted pytest modules to capture detailed tracebacks for `fin_extract`, `fin_enhance`, and `fin_export`.
- [x] Summarize root causes (e.g., missing API compatibility layers, fixture expectations) in plan notes.

## Phase 2 – Implement Fixes
- [x] Restore or shim expected interfaces in `fin_cli/fin_extract/main.py` so tests can monkeypatch `load_pdf_document`.
- [x] Update fin-enhance categorizer logic or fixtures to satisfy pattern/LLM fallback expectations without regressions.
- [x] Adjust fin-export CLI defaults/fixtures to avoid ValueErrors during tests (ensure deterministic config).

## Phase 3 – Verification
- [x] Re-run the specific pytest modules fixed above to confirm they pass.
- [x] Execute full `pytest` suite inside the virtualenv and ensure green.
- [x] Document findings and decisions in plan notes for future agents.

### Notes
- Create focused commits per subsystem if changes grow large (extract/enhance/export).
- Keep logging routed to stderr while ensuring stdout-based CLI tests read cleanly.
- fin_extract CLI tests expected legacy `load_pdf_document`; added compatibility wrapper in `fin_cli/fin_extract/main.py` and restored Click decorator after refactor.
- fin_enhance categorizer tests were failing due to diverged merchant-pattern normalization and config schema changes. Updated shared merchant normalization (`fin_cli/shared/merchants.py`) to strip numeric noise while retaining brand tokens, synchronized LLM client helper, adjusted auto-assignment logic in `HybridCategorizer`, and refreshed fixtures/tests.
- fin_export suite re-used analysis fixtures via `pytest_plugins`, causing duplicate plugin registration when running the whole suite. Replaced plugin usage with explicit fixture re-export in `tests/fin_export/conftest.py` to keep pytest happy.
- After fixes, targeted modules and full `pytest` run now pass (90 passed in 2.57s on 2025-10-09).
