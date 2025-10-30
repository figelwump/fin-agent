## plan_transaction_cleanup_workflow_103025

- [x] Phase 1 – Problem Assessment
  - [x] Review transcript highlighting schema lookup confusion and unsafe deletion workflow.
  - [x] Identify documentation gaps leading to reliance on legacy `account_key` column references.

- [x] Phase 2 – Documentation Fixes
  - [x] Update relevant skill docs to reflect current schema (no `account_key` column) and encourage `fin-query schema` usage.
  - [x] Add guidance to confirm deletion targets with the user before applying changes.

- [x] Phase 3 – CLI Enhancements
  - [x] Implement `fin-edit delete-transactions` subcommand with preview + confirmation flow.
  - [x] Ensure command logs transaction details prior to deletion and respects dry-run.
  - [x] Add unit coverage for the new command.

- [x] Phase 4 – Verification & Wrap-up
  - [x] Run targeted tests (`pytest tests/fin_edit`) and lint if applicable.
  - [x] Document verification steps and residual risks in the plan notes.

**Notes**
- Schema fields: use `transactions.account_id` joined to `accounts.name`/`accounts.institution`; categories via `category_id` join. Reinforce through docs.
- Confirm downstream skills (statement-processor, ledger-query) reference the updated instructions.
- Tests: `source .venv/bin/activate && pytest tests/fin_edit/test_fin_edit.py` (covers new delete flow, preview/apply behavior, and missing-id guard).
