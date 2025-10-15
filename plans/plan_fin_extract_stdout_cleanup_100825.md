# plan_fin_extract_stdout_cleanup_100825

## Phase 1 – Reproduce & Scope
- [x] Run `fin-extract` with `--stdout` to capture the mixed CSV/log output and quantify the duplicate records being emitted into the stream.
- [x] Inspect the captured output to isolate which lines are duplicated and determine whether they originate from transaction rendering or from the shared logger.

## Phase 2 – Implement Logging Fix
- [x] Review `fin_cli/shared/logging.py` and the `Logger` facade to understand how Rich consoles are configured for info/success output.
- [x] Adjust the logger so informational messages route to stderr (or are suppressed) when commands emit structured stdout payloads, ensuring `fin-extract --stdout` produces pure CSV.
- [x] Verify other CLI commands continue to display human-readable logs without corrupting stdout streams.

## Phase 3 – Verification
- [x] Re-run the original `fin-extract` command and confirm the stdout stream now contains only a single CSV header plus transaction rows (no duplicate/log lines).
- [x] Update or add automated coverage (unit or CLI-level) if practical to guard against regressions in stdout purity.
- [x] Document the change rationale in the plan notes for future agents.

### Notes
- Root cause likely lives in the shared Rich-based logger (`fin_cli/shared/logging.py`), which currently prints to stdout, contaminating CSV streams.
- Key files: `fin_cli/fin_extract/main.py`, `fin_cli/shared/logging.py`, and any tests under `tests/` covering CLI logging.
- Ensure virtualenv activation (`source .venv/bin/activate`) before executing project CLIs during verification.
- 2025-10-09: `fin-extract statements/bofa/eStmt_2025-08-22.pdf --stdout` emits Rich info lines (`Using PDF engine`, `Detected format`, account summary) before the CSV header and prints `Extraction complete...` after the rows, confirming stdout contamination originates from the shared logger rather than duplicate transaction rendering.
- 2025-10-09: Updated `fin_cli/shared/logging.py` to direct info/success/warning/error output to Rich's stderr console while keeping a stdout console available for structured printing. Verified `fin-extract --stdout` now produces pure CSV (captured via shell redirection) and `fin-extract | fin-enhance --stdin --stdout` still writes clean CSV streams while logs remain visible in the terminal.
- 2025-10-09: Added regression test `tests/shared/test_logging.py::test_logger_info_routes_to_stderr` asserting that informational logging no longer touches stdout. Captured `fin-extract statements/bofa/eStmt_2025-08-22.pdf --stdout` output post-fix and confirmed absence of log chatter in the CSV.
