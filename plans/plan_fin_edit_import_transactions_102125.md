# fin-edit Import Transactions Plan

## Objective
Implement the `fin-edit import-transactions` subcommand to safely persist enriched CSV transactions (with account metadata, category choices, and precomputed fingerprints) into the SQLite ledger, honoring dry-run versus apply semantics and providing clear logging/statistics.

## Phase 1 – Requirements & Design
- [x] Confirm expected CSV schema (columns, types) and dry-run behaviour by reviewing `.claude/skills/statement-processor` post-processing output and currently shared utilities only. *(Columns: date, merchant, amount, original_description, account_name, institution, account_type, category, subcategory, confidence, account_key, fingerprint; treat confidence default 1.0, ensure dry-run performs validation without writes.)*
- [x] Identify reusable helpers in shared modules (move any needed logic out of CLI-specific code such as `fin_cli.fin_enhance.importer` into a shared helper) and decide on dedupe/category handling strategy. *(Introduce new shared parser for enriched CSV rows; reuse `fin_cli.shared.models` for account/category handling with fingerprints + `insert_transaction` dedupe).*
- [x] Document command interface (options, arguments, logging expectations) aligning with existing CLI conventions. *(Command: `fin-edit import-transactions [OPTIONS] <csv_path>` where `<csv_path>` may be `-` for stdin; options: `--method TEXT` default `manual:fin-edit`, `--default-confidence FLOAT` to override blank values (default 1.0), future-proof for verbose logging; summarise totals and category creations with `[dry-run]` prefix when previewing.)*

## Phase 2 – Implementation
- [x] Add `import-transactions` Click command to `fin_cli/fin_edit/main.py`, reusing CSV parsing helpers and wiring into database models. *(See `fin_cli/fin_edit/main.py:353` for the new command, helper dataclass, and wiring to shared loader.)*
- [x] Implement dry-run preview that reports would-be inserts without mutating the database. *(Preview path uses read-only connection, counts duplicates/inserts, and logs would-be category/account creations.)*
- [x] Implement apply path that upserts accounts, inserts transactions, updates category usage counts, and skips duplicates using fingerprints. *(Uses shared loader + `models.get_or_create_category`, `models.upsert_account`, and `models.insert_transaction` with `allow_update=True`.)*
- [x] Ensure command emits summarized stats (inserted, duplicates, skipped) consistent with other tooling. *(See `_log_import_summary` in `fin_cli/fin_edit/main.py:396`.)*

## Phase 3 – Testing & Validation
- [x] Extend `tests/fin_edit/test_fin_edit.py` with coverage for dry-run/apply flows, duplicate handling, and category creation behaviour. *(Added CSV helpers + three import tests covering preview, apply, duplicates, and no-create scenario.)*
- [x] Run `pytest tests/fin_edit/test_fin_edit.py` (after activating `.venv`) and ensure suite passes. *(Executed `source .venv/bin/activate && pytest tests/fin_edit/test_fin_edit.py` — all 5 tests pass.)*
- [ ] Manual CLI sanity check (optional) to verify logging output shape.

## Phase 4 – Documentation & Cleanup
- [x] Update relevant docs/help text if needed (e.g., README snippets or skill instructions) to reflect final CLI syntax. *(README fin-edit section, statement processor skill + examples + reference now cover preview/apply flow and new paths.)*
- [x] Review `git status` for unintended changes and provide summary/next steps. *(Working tree clean aside from staged rename to `.claude/skills/…` replacing legacy `skills/…`; summary prepared for final handoff.)*

## Notes / Decisions
- Expect enriched CSV rows to include `account_key` and `fingerprint`; plan to validate presence and compute if missing for robustness.
- If functionality from `fin_cli.fin_enhance.importer` is required, extract it into a new shared helper module rather than depending on CLI-specific code that may be deprecated later.
- Ensure category ids are resolved/created based on provided category/subcategory, respecting dry-run semantics.

### Interfaces & Logging
- CLI shape: `fin-edit import-transactions [OPTIONS] PATH|-` (PATH required; `-` reads stdin).
- Options: `--method` (default `manual:fin-edit`), `--default-confidence` (fill empty confidence cells), `--no-create-categories` to skip auto-creation and error instead.
- Logging: show totals (`rows`, `inserted`, `duplicates`, `categories_created`, `categories_missing`) with dry-run prefix; per-row debug for verbose mode only.
