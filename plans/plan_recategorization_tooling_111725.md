# plan_recategorization_tooling_111725

## Context
- Agent struggled to recategorize many transactions for a merchant because saved queries omit IDs and `fin-edit set-category` only targets a single row.
- We need to expose transaction IDs in `merchant_search`, add a `--where` targeting mode to `fin-edit set-category`, update prompts/docs, and make the transaction-categorizer skill clearly handle merchant recategorization requests.

## Phase 1 — Query output & CLI capabilities
- [x] Update `fin-query` `merchant_search` query + docs/tests so it returns `transactions.id` (and keep backwards-compatible column order notes). *(README + ledger docs mention first column is `id`; tests updated to assert column list.)*
- [x] Extend `fin-edit set-category` to accept a `--where` clause, ensuring exclusivity with existing target flags, preview logging, and safe execution. *(New option previews matching rows, blocks semicolons, and supports dry-run + apply for batch updates.)*
- [x] Document the new `--where` workflow in README / CLI help (examples for bulk merchant recategorization). *(README CLI reference now shows the flag + merchant flow.)*

## Phase 2 — Prompt & skill guidance
- [x] Update `FIN_AGENT_PROMPT` to explicitly instruct agents to use `merchant_search` (with IDs) + `fin-edit set-category --where` before resorting to raw SQL. *(Added “Categorization Best Practices” section with the exact workflow.)*
- [x] Refresh `.claude/skills/transaction-categorizer/SKILL.md` frontmatter description to mention recategorizing existing merchant patterns, and add a scenario section spelling out the exact steps using the new CLI flow. *(New scenario block covers inspect → set-category --where → add pattern.)*

## Notes
- Ensure tests in `tests/fin_query/test_executor.py` cover the new ID column.
- Consider highlighting that `--where` forbids semicolons/unsafe input to limit SQL injection.
- Reminder: update any references to the old column order (e.g., ledger-query docs) so agents know where to find IDs.
