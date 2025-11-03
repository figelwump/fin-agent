---
name: statement-processor
description: Process, extract, and import bank/credit card statements from PDF files into the local SQLite database. Use when asked to import statements, process PDFs, or extract transactions from statement files.
allowed-tools: Bash, Read, Grep, Glob
---

# Statement Processor Skill

Teach the agent how to extract and import bank statements end-to-end.

## Configuration

**Resource root (do not `cd` here):** `$SKILL_ROOT` = `.claude/skills/statement-processor`

**Workspace root:** `~/.finagent/skills/statement-processor`

**Choose a session slug once at the start** (e.g., `chase-6033-20251027`) and remember it throughout the workflow.

Throughout this workflow, **`$WORKDIR`** refers to: `~/.finagent/skills/statement-processor/<slug>`

When executing commands, replace `$WORKDIR` with the full path using your chosen slug. Use `$SKILL_ROOT` only when you need an absolute path to a helper script or reference file and keep the shell working directory at the repository root.

Prerequisites: install the `fin-cli` package (e.g., `pip install -e .` or `pipx install fin-cli`) so the `fin-*` commands are on your `PATH`. Python helper scripts run with your default interpreter; no virtualenv activation is required inside the skill.

## Workflow (Sequential Loop)

Process statements one at a time. For each PDF, run the full loop before touching the next file.

**Before starting, create the workspace directory once:**
```bash
mkdir -p $WORKDIR
```

### Steps

1. **Scrub sensitive data into the workspace:**
```bash
fin-scrub statement.pdf --output-dir $WORKDIR
```

   > **Escalation:** If `fin-scrub` errors, returns an empty/garbled file, or you notice PII surviving in the scrubbed text, switch to the [fin-scrub configuration workflow](reference/fin-scrub-config-workflow.md). Catastrophic failures should trigger that workflow automatically; otherwise pause, alert the user, and wait for approval before promoting any config changes beyond the workspace override.

2. **Build the prompt** (single statement per invocation):
```bash
python $SKILL_ROOT/scripts/preprocess.py \
--workdir $WORKDIR \
--input $WORKDIR/<file>-scrubbed.txt
```

3. **Send the prompt to your LLM** (Claude, etc.) and save the CSV response to `$WORKDIR/<filename>.csv`.

4. **Enrich and apply known patterns:**
```bash
python $SKILL_ROOT/scripts/postprocess.py \
--workdir $WORKDIR \
--apply-patterns --verbose
```

5. **Import validated rows** (preview first, then apply with pattern learning):
```bash
# Preview
fin-edit import-transactions $WORKDIR/<file>-enriched.csv

# Apply
fin-edit --apply import-transactions $WORKDIR/<file>-enriched.csv \
--learn-patterns --learn-threshold 0.75
```

6. **Hand off to transaction-categorizer skill** to handle remaining uncategorized transactions. Verify success with:
```bash
fin-query saved uncategorized --limit 5 --format csv  # Should shrink

fin-query saved merchant_patterns --limit 5 --format csv  # Should reflect new patterns
```

7. **If any command fails** or the sanity checks above are unexpected, stop the loop and resolve the issue before moving to the next statement.

---

**Note:** The prompt builder focuses purely on extraction guidance. Category taxonomy and merchant hints are fetched later by the transaction-categorizer skill. If you need to inspect taxonomy data separately for debugging, run `python $SKILL_ROOT/scripts/preprocess.py --input scrubbed.txt --emit-json` or query the catalog directly with `fin-query` (e.g., `fin-query saved categories --limit 200 --format csv`).

## CSV Requirements (LLM Output)
- Required header (order fixed):
  `date,merchant,amount,original_description,account_name,institution,account_type,last_4_digits,category,subcategory,confidence`
- `last_4_digits` is REQUIRED and must be exactly 4 digits (e.g., `6033`). Do not include these digits in `account_name`.
- Postprocess writes `account_key`, `fingerprint`, `pattern_key`, `pattern_display`, `merchant_metadata`, and `source` columns and preserves `last_4_digits`.

## Working Directory
- The workspace directory is created once at the start (e.g., `~/.finagent/skills/statement-processor/chase-6033-20251023`).
- All helper CLIs accept `--workdir` to locate files within the workspace.
- All files (scrubbed statements, prompts, raw LLM CSVs, enriched CSVs) are stored flat in the workspace directory.
- Clean up the workspace once the import is committed to the database.

## Handling Low Confidence and Uncategorized Transactions
- The prompt instructs the LLM to lower `confidence` (<0.7) whenever unsure.
- Post-processing with `--apply-patterns` will apply known merchant patterns. Use `--verbose` to see which patterns matched and which transactions remain uncategorized.
- Import transactions with `fin-edit import-transactions` - uncategorized transactions (empty category/subcategory) will be imported successfully.
- After import, use the `transaction-categorizer` skill to handle remaining uncategorized or low-confidence transactions:
  - The categorizer will ALWAYS attempt LLM categorization first for ALL uncategorized transactions
  - Only if leftovers remain after LLM categorization, the categorizer will offer interactive manual review
  - Merchant patterns are learned automatically to improve future auto-categorization
- If account metadata is unclear, pause and ask the user which account the statement belongs to; rerun post-processing once metadata is confirmed.
- For bulk high-confidence learning during import, use `fin-edit --apply import-transactions … --learn-patterns --learn-threshold 0.75`; this will automatically create patterns for high-confidence transactions.
- For manual pattern creation, use `fin-edit add-merchant-pattern` (preview, then `--apply`) with the deterministic pattern key (use `python -c "from fin_cli.shared.merchants import merchant_pattern_key; print(merchant_pattern_key('MERCHANT RAW'))"` if needed).

## Database Writes
- Always preview imports: `fin-edit import-transactions enriched.csv`
- Apply when satisfied: `fin-edit --apply import-transactions enriched.csv --learn-patterns --learn-threshold 0.75`
- Use `--default-confidence` to backfill blanks and `--no-create-categories` to enforce pre-created taxonomy entries.
- Validate inserts with `fin-query saved recent_imports --limit 10 --format csv` or `fin-query saved transactions_month --param month=YYYY-MM --limit 200 --format csv`.

## Cleanup & Database Safety
- The SQLite schema is normalized: `transactions` only stores foreign keys (`category_id`, `account_id`). There is **no** `category`, `subcategory`, `account_name`, or `account_key` column in the table. Join to `categories` / `accounts` or use saved queries when you need human-readable fields.
- Need a refresher? Run `fin-query schema --table transactions --format table` (or `--all`) before composing ad-hoc SQL.
- To remove bad rows after an import, run a dry-run preview and confirm the IDs with the user. Example:
  ```bash
fin-edit delete-transactions --id 338 --id 340 --id 342
  ```
  This prints every targeted row and exits without writing. Only rerun with `--apply` **after** the user approves the list:
  ```bash
fin-edit --apply delete-transactions --id 338 --id 340 --id 342
  ```
- Avoid raw `sqlite3` deletes unless a fin-cli command cannot perform the operation.

## Available Commands
- `fin-scrub`: sanitize PDFs to redact PII.
- `python $SKILL_ROOT/scripts/preprocess.py`: build per-statement prompts with existing taxonomies; rejects multi-input usage.
- `python $SKILL_ROOT/scripts/postprocess.py`: append `account_key`/`fingerprint`/`source` to LLM CSV output and, with `--apply-patterns`, pull categories/confidence from existing merchant patterns. Use `--verbose` to see pattern matching details.
- `fin-edit import-transactions`: persist enriched CSV rows into SQLite (preview by default; add `--apply` to write, `--default-confidence` to fill gaps, `--no-create-categories` to force manual taxonomy prep). Uncategorized transactions will be imported successfully.
- `fin-edit set-category`: correct individual transactions after import (dry-run before `--apply`).
- `fin-edit add-merchant-pattern`: remember high-confidence merchant/category mappings for future runs.
- `fin-query saved merchants --min-count N --limit 200 --format csv`: retrieve merchant taxonomy for debugging.

## Common Errors
- **Missing CSV columns**: Verify LLM output has all required fields: `date,merchant,amount,original_description,account_name,institution,account_type,last_4_digits,category,subcategory,confidence`. Run postprocess.py to add `account_key`, `fingerprint`, and related columns.
- **Fingerprint collision on import**: Transaction already exists in database. This is expected behavior - duplicates are automatically skipped.
- **Invalid confidence value**: Ensure confidence is between 0 and 1. Use `--default-confidence 0.9` to fill empty cells during import.
- **Unknown category on import**: Either edit the CSV to use existing categories (check with `fin-query saved categories --limit 200 --format csv`) or allow creation by omitting `--no-create-categories` flag.
- **Account identification unclear**: If the LLM cannot determine which account a statement belongs to, pause and ask the user before importing. Rerun `$SKILL_ROOT/scripts/postprocess.py` after updating account metadata in the CSV.
- **Low-confidence rows (<0.7)**: Review and correct in the enriched CSV before import, or use `fin-edit set-category` after import to fix individual transactions.
- **Malformed amount**: Ensure amounts are positive decimals with two decimal places. Credits/refunds should be excluded upstream.

## Reference Material
- `$SKILL_ROOT/reference/csv-format.md` – canonical schema for enriched CSVs.

## Validation After Import
After successfully importing transactions, verify the results:
```bash
# Check recent imports
fin-query saved recent_imports --limit 5 --format csv

# Verify transaction count for the month
fin-query saved transactions_month --param month=YYYY-MM --limit 200 --format csv

# Check for uncategorized transactions (should be minimal if import went well)
fin-query saved uncategorized --limit 10 --format csv
```

## Cross-Skill Transitions
- **After import**: Use the `transaction-categorizer` skill to handle uncategorized transactions (empty category/subcategory) or low-confidence categorizations (confidence < 0.7). The categorizer always tries an automated LLM pass for ALL uncategorized transactions, then falls back to interactive manual review only for leftovers. Patterns are learned automatically for future auto-categorization.
- **To analyze imported data**: Use `spending-analyzer` skill to run reports on the newly imported transactions
- **To query specific merchants or categories**: Use `ledger-query` skill for targeted lookups

## Next Steps for Agents
- Ensure enriched CSVs include `account_key`, `fingerprint`, and `source` columns before import.
- Use `--verbose` flag with `$SKILL_ROOT/scripts/postprocess.py` to see pattern matching details and identify uncategorized transactions.
- Review the `source` column in enriched CSVs to understand categorization provenance: `llm_extraction`, `pattern_match`, or empty (uncategorized).
