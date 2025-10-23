---
name: statement-processor
description: Extract and import bank statements from PDF files into the local SQLite database.
---

# Statement Processor Skill

Teach the agent how to extract and import bank statements end-to-end.

Environment
- Activate the venv before running commands:
  - `source .venv/bin/activate`

Quick Start (LLM Pipeline)
1. Initialise a workspace (shared by single or batch flows): `eval "$(.claude/skills/statement-processor/scripts/bootstrap.sh chase-2025-09)"`.
   - Exports `FIN_STATEMENT_WORKDIR`, `FIN_STATEMENT_SCRUBBED_DIR`, `FIN_STATEMENT_PROMPTS_DIR`, `FIN_STATEMENT_LLM_DIR`, and `FIN_STATEMENT_ENRICHED_DIR`.
2. Scrub sensitive data: `fin-scrub statement.pdf --output-dir "$FIN_STATEMENT_WORKDIR"`.
3. Build prompt with taxonomies: `python .claude/skills/statement-processor/scripts/preprocess.py --workdir "$FIN_STATEMENT_WORKDIR"`.
4. Send the prompt to your LLM (Claude, etc.) and save the CSV response into `$FIN_STATEMENT_LLM_DIR`.
5. Enrich CSV and apply known rules: `python .claude/skills/statement-processor/scripts/postprocess.py --workdir "$FIN_STATEMENT_WORKDIR" --apply-patterns --verbose`.
6. Import validated rows: `fin-edit import-transactions "$FIN_STATEMENT_ENRICHED_DIR"/file.csv` (preview) then `fin-edit --apply import-transactions "$FIN_STATEMENT_ENRICHED_DIR"/file.csv --learn-patterns --learn-threshold 0.9` once the review passes. Add `--no-create-categories` if you want to fail instead of auto-creating new categories. Uncategorized transactions will be imported successfully.
7. Review uncategorized transactions: Use the `transaction-categorizer` skill to interactively categorize any remaining uncategorized transactions.

The prompt builder loads the live taxonomy from SQLite automatically. For debugging you can inspect the payload by running `python .claude/skills/statement-processor/scripts/preprocess.py --input scrubbed.txt --emit-json`, or export the same data manually with:
- Categories: `fin-query saved categories --format json > categories.json`
- Merchants: `fin-query saved merchants --min-count 2 --format json > merchants.json` (adjust `--min-count`/`--limit` as needed).

Batch Workflow
1. Automate scrubbing + prompt prep with the helper script:
   - `.claude/skills/statement-processor/scripts/run_batch.sh --workdir "$FIN_STATEMENT_WORKDIR" --max-merchants 150 --max-statements-per-prompt 3 statements/*.pdf`
   - The script cleans stale `*-scrubbed.txt` files in the workspace, runs `fin-scrub` for each PDF, and invokes `preprocess.py --batch` so prompts land in `$FIN_STATEMENT_PROMPTS_DIR` using the default naming scheme.
2. Run the LLM once per emitted prompt chunk and save each CSV response (e.g., `chunk-1.csv`).
3. Post-process every CSV: `python .claude/skills/statement-processor/scripts/postprocess.py --input chunk-1.csv --output chunk-1-enriched.csv --apply-patterns --verbose`
4. Concatenate or import each enriched CSV via `fin-edit import-transactions` (preview) and rerun with `--apply` when ready. Use `--default-confidence` to fill empty confidence cells when needed. Uncategorized transactions will be imported successfully.
5. Review uncategorized transactions: Use the `transaction-categorizer` skill to interactively categorize any remaining uncategorized transactions.

Working Directory
- Use `bootstrap.sh` to create a deterministic run directory (e.g., `eval "$(.claude/skills/statement-processor/scripts/bootstrap.sh chase-2025-09)"`). The script works for both single and batch workflows.
- All helper CLIs accept `--workdir` so they can auto-discover `scrubbed/`, `prompts/`, `llm/`, and `enriched/` subdirectories.
- The harness resets the shell’s CWD between commands; rely on the exported environment variables or absolute paths instead of `cd`.
- Store scrubbed statements, prompts, raw LLM CSVs, and enriched CSVs inside the workspace and clean up once the import is committed to the database.

Handling Low Confidence and Uncategorized Transactions
- The prompt instructs the LLM to lower `confidence` (<0.7) whenever unsure.
- Post-processing with `--apply-patterns` will apply known merchant patterns. Use `--verbose` to see which patterns matched and which transactions remain uncategorized.
- Import transactions with `fin-edit import-transactions` - uncategorized transactions (empty category/subcategory) will be imported successfully.
- After import, use the `transaction-categorizer` skill to handle remaining uncategorized or low-confidence transactions:
  - The categorizer will ALWAYS attempt LLM categorization first using Claude Haiku 4.5 (cost-effective) for ALL uncategorized transactions
  - Only if leftovers remain after LLM categorization, the categorizer will offer interactive manual review
  - Merchant patterns are learned automatically to improve future auto-categorization
- If account metadata is unclear, pause and ask the user which account the statement belongs to; rerun post-processing once metadata is confirmed.
- For bulk high-confidence learning during import, use `fin-edit --apply import-transactions … --learn-patterns --learn-threshold 0.9`; this will automatically create patterns for high-confidence transactions.
- For manual pattern creation, use `fin-edit add-merchant-pattern` (preview, then `--apply`) with the deterministic pattern key (use `python -c "from fin_cli.shared.merchants import merchant_pattern_key; print(merchant_pattern_key('MERCHANT RAW'))"` if needed).

Database Writes
- Always preview imports: `fin-edit import-transactions enriched.csv`
- Apply when satisfied: `fin-edit --apply import-transactions enriched.csv --learn-patterns --learn-threshold 0.9`
- Use `--default-confidence` to backfill blanks and `--no-create-categories` to enforce pre-created taxonomy entries.
- Validate inserts with `fin-query saved recent_imports --limit 10` or `fin-query saved transactions_month --param month=YYYY-MM`.

Available Commands
- `.claude/skills/statement-processor/scripts/bootstrap.sh`: initialise a run workspace and export helper environment variables (use via `eval "$(...)"`).
- `.claude/skills/statement-processor/scripts/run_batch.sh`: scrub multiple PDFs and generate batch prompts (steps 1–2 of the batch workflow).
- `fin-scrub`: sanitize PDFs to redact PII.
- `python .claude/skills/statement-processor/scripts/preprocess.py`: build single or batch prompts with existing taxonomies.
- `python .claude/skills/statement-processor/scripts/postprocess.py`: append `account_key`/`fingerprint`/`source` to LLM CSV output and, with `--apply-patterns`, pull categories/confidence from existing merchant patterns. Use `--verbose` to see pattern matching details.
- `fin-edit import-transactions`: persist enriched CSV rows into SQLite (preview by default; add `--apply` to write, `--default-confidence` to fill gaps, `--no-create-categories` to force manual taxonomy prep). Uncategorized transactions will be imported successfully.
- `fin-edit set-category`: correct individual transactions after import (dry-run before `--apply`).
- `fin-edit add-merchant-pattern`: remember high-confidence merchant/category mappings for future runs.
- `fin-query saved merchants --format json --min-count N`: retrieve merchant taxonomy for debugging.

Common Errors
- **Missing CSV columns**: Verify LLM output has all required fields: `date,merchant,amount,original_description,account_name,institution,account_type,category,subcategory,confidence`. Run postprocess.py to add `account_key` and `fingerprint`.
- **Fingerprint collision on import**: Transaction already exists in database. This is expected behavior - duplicates are automatically skipped.
- **Invalid confidence value**: Ensure confidence is between 0 and 1. Use `--default-confidence 0.9` to fill empty cells during import.
- **Unknown category on import**: Either edit the CSV to use existing categories (check with `fin-query saved categories`) or allow creation by omitting `--no-create-categories` flag.
- **Account identification unclear**: If the LLM cannot determine which account a statement belongs to, pause and ask the user before importing. Rerun postprocess.py after updating account metadata in the CSV.
- **Low-confidence rows (<0.7)**: Review and correct in the enriched CSV before import, or use `fin-edit set-category` after import to fix individual transactions.
- **Malformed amount**: Ensure amounts are positive decimals with two decimal places. Credits/refunds should be excluded upstream.

Reference Material (to be refreshed)
- `examples/llm-extraction.md` – end-to-end walkthrough for a single statement.
- `examples/batch-processing.md` – workflow for multi-statement batches.
- `reference/csv-format.md` – canonical schema for enriched CSVs.

Validation After Import
After successfully importing transactions, verify the results:
```bash
# Check recent imports
fin-query saved recent_imports --limit 5

# Verify transaction count for the month
fin-query saved transactions_month --param month=YYYY-MM --format table

# Check for uncategorized transactions (should be minimal if import went well)
fin-query saved uncategorized --limit 10
```

Cross-Skill Transitions
- **After import**: Use the `transaction-categorizer` skill to handle uncategorized transactions (empty category/subcategory) or low-confidence categorizations (confidence < 0.7). The categorizer always tries LLM categorization first with Claude Haiku 4.5 (cost-effective) for ALL uncategorized transactions, then falls back to interactive manual review only for leftovers. Patterns are learned automatically for future auto-categorization.
- **To analyze imported data**: Use `spending-analyzer` skill to run reports on the newly imported transactions
- **To query specific merchants or categories**: Use `ledger-query` skill for targeted lookups

Next Steps for Agents
- Ensure enriched CSVs include `account_key`, `fingerprint`, and `source` columns before import.
- Use `--verbose` flag with postprocess.py to see pattern matching details and identify uncategorized transactions.
- After import, transition to `transaction-categorizer` skill to handle uncategorized or low-confidence transactions:
  - The categorizer will ALWAYS attempt LLM categorization (Haiku) first for ALL uncategorized transactions
  - Only if leftovers remain after LLM categorization, the categorizer will use interactive manual review
  - Merchant patterns are learned automatically to improve future imports
- Review the `source` column in enriched CSVs to understand categorization provenance: `llm_extraction`, `pattern_match`, or empty (uncategorized).
