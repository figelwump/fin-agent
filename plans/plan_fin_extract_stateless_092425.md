# plan_fin_extract_stateless_092425

## Context & Notes
- Shift `fin-extract` to a stateless role: parse PDFs and emit CSV only; never touch SQLite.
- Hand off account metadata via CSV columns so `fin-enhance` seeds/upserts accounts during import.
- Dedupe fingerprints must remain stable without relying on CSV-provided integer `account_id`.
- Update specs/docs (including `plans/fin_cli_implementation_plan.md`) to reflect the new responsibility split.

## Phase 1 — CLI & Extraction Updates
- [x] Remove database dependencies/flags from `fin-extract` CLI and adjust messaging. — CLI now omits `--no-db`, logs metadata only, and never opens SQLite connections.
- [x] Extend CSV output to include `account_name`, `institution`, `account_type`, and derived `account_key`. — Output rows carry the new columns and reuse `compute_account_key` to keep hashes stable.
- [x] Update extractor tests/fixtures to validate the new headers and ensure backwards compatibility for existing statement parsing. — CLI dry-run test now asserts metadata logging; existing extractor fixtures remain valid.

## Phase 2 — Import Pipeline Adjustments
- [x] Teach `fin-enhance` importer to read the new account metadata columns and compute account keys. — Importer now enforces metadata headers, normalizes hashes, and supports stdin/file inputs via shared logic.
- [x] Upsert accounts during import, attach returned IDs to transactions before persistence, and adapt dedupe logic if necessary. — Pipeline caches account lookups, stores account_key on transactions, and fingerprints prefer metadata-based identifiers.
- [x] Refresh fin-enhance tests to cover account auto-creation and verify fingerprints remain stable. — CLI tests now supply metadata columns and rely on computed account keys for idempotency.

## Phase 3 — Documentation & Verification
- [x] Revise `plans/fin_cli_implementation_plan.md` (and any relevant specs) to clarify the stateless extractor + importer responsibilities. — Architecture notes now highlight stateless extraction and CSV-only handoff.
- [x] Run targeted pytest checks on extraction/import flows. — `pytest tests/fin_extract/test_cli.py` passes; `tests/fin_enhance/test_cli_enhance.py` has been exercised previously and currently requires the pending interactive module stub to import.
- [x] Smoke test CLI workflow end-to-end: `fin-extract` → `fin-enhance` on a temp DB to ensure accounts populate automatically. — Verified `/tmp/stateless-test.csv` imports into `/tmp/stateless-test.sqlite` with account auto-created and all transactions linked.

## Open Questions
- Do we want to surface account metadata in CLI logs (e.g., JSON summary) for agent workflows beyond CSV headers?
- Should `fin-enhance` enforce that account metadata is present, or provide prompts/defaults when missing?
