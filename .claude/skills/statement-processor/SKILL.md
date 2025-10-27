---
name: statement-processor
description: Process, extract, and import bank/credit card statements from PDF files into the local SQLite database. Use when asked to import statements, process PDFs, or extract transactions from statement files.
allowed-tools: Bash, Read, Grep, Glob
---

# Statement Processor Skill

Teach the agent how to extract and import bank statements end-to-end.

## Environment
1. Activate the venv before running any python script:
   ```bash
   source .venv/bin/activate
   ```

## Setup (Run Once Per Session)
**IMPORTANT: Run bootstrap ONCE at the start. It prints export lines; `eval` applies them so the variables persist for the rest of the session.**
1. Initialise the statement workspace and let bootstrap set environment variables (no need to export manually):
   ```bash
   eval "$(.claude/skills/statement-processor/scripts/bootstrap.sh --session 'your-session-slug')"
   ```
   - This exports `SESSION_SLUG`, `FIN_STATEMENT_WORKDIR`, `FIN_STATEMENT_SCRUBBED_DIR`, `FIN_STATEMENT_PROMPTS_DIR`, `FIN_STATEMENT_LLM_DIR`, and `FIN_STATEMENT_ENRICHED_DIR`.
   - Alternative (timestamped workspace): `eval "$(.claude/skills/statement-processor/scripts/bootstrap.sh your-label)"`.
   - Companion skills (like `transaction-categorizer`) can reuse the same `SESSION_SLUG` automatically.

## Workflow (Sequential Loop)

Process statements one at a time. For each PDF, run the full loop before touching the next file.

**IMPORTANT:** Prepend `source .venv/bin/activate &&` before running any python script.

### Steps

1. **Scrub sensitive data into the workspace:**
   ```bash
   fin-scrub statement.pdf --output-dir "$FIN_STATEMENT_WORKDIR"
   ```

2. **Build the prompt** (single statement per invocation):
   ```bash
   python .claude/skills/statement-processor/scripts/preprocess.py \
     --workdir "$FIN_STATEMENT_WORKDIR" \
     --input "$FIN_STATEMENT_SCRUBBED_DIR/<file>-scrubbed.txt"
   ```

3. **Send the prompt to your LLM** (Claude, etc.) and save the CSV response into `$FIN_STATEMENT_LLM_DIR`.

4. **Enrich and apply known patterns:**
   ```bash
   python .claude/skills/statement-processor/scripts/postprocess.py \
     --workdir "$FIN_STATEMENT_WORKDIR" \
     --apply-patterns --verbose
   ```

5. **Import validated rows** (preview first, then apply with pattern learning):
   ```bash
   # Preview
   fin-edit import-transactions "$FIN_STATEMENT_ENRICHED_DIR"/file.csv

   # Apply
   fin-edit --apply import-transactions "$FIN_STATEMENT_ENRICHED_DIR"/file.csv \
     --learn-patterns --learn-threshold 0.75
   ```

6. **Hand off to transaction-categorizer skill** to handle remaining uncategorized transactions. The categorizer's bootstrap reuses `SESSION_SLUG`. Verify success with:
   ```bash
   fin-query saved uncategorized --limit 5  # Should shrink
   fin-query saved merchant_patterns --limit 5 --format table  # Should reflect new patterns
   ```

7. **If any command fails** or the sanity checks above are unexpected, stop the loop and resolve the issue before moving to the next statement.

---

**Note:** The prompt builder focuses purely on extraction guidance. Category taxonomy and merchant hints are fetched later by the transaction-categorizer skill. If you need to inspect taxonomy data separately for debugging, run `python .claude/skills/statement-processor/scripts/preprocess.py --input scrubbed.txt --emit-json` or query the catalog directly with `fin-query` (e.g., `fin-query saved categories --format json`).

## CSV Requirements (LLM Output)
- Required header (order fixed):
  `date,merchant,amount,original_description,account_name,institution,account_type,last_4_digits,category,subcategory,confidence`
- `last_4_digits` is REQUIRED and must be exactly 4 digits (e.g., `6033`). Do not include these digits in `account_name`.
- Postprocess writes `account_key`, `fingerprint`, `pattern_key`, `pattern_display`, `merchant_metadata`, and `source` columns and preserves `last_4_digits`.

## Working Directory
- Bootstrap creates a deterministic run directory (e.g., `~/.finagent/skills/statement-processor/chase-6033-20251023`) that matches the categorizer workspace.
- All helper CLIs accept `--workdir` so they can auto-discover `scrubbed/`, `prompts/`, `llm/`, and `enriched/` subdirectories.
- The bash session persists between commands, so exported environment variables (like `$FIN_STATEMENT_WORKDIR`) remain available without re-running bootstrap.
- Store scrubbed statements, prompts, raw LLM CSVs, and enriched CSVs inside the workspace and clean up once the import is committed to the database.

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
- Validate inserts with `fin-query saved recent_imports --limit 10` or `fin-query saved transactions_month --param month=YYYY-MM`.

## Available Commands
- `.claude/skills/statement-processor/scripts/bootstrap.sh`: initialise a run workspace ONCE per session (supports `--session` for shared slugs) and export helper environment variables (use via `eval "$(...)"`). Run this during Environment Setup only.
- `fin-scrub`: sanitize PDFs to redact PII.
- `python .claude/skills/statement-processor/scripts/preprocess.py`: build per-statement prompts with existing taxonomies; rejects multi-input usage.
- `python .claude/skills/statement-processor/scripts/postprocess.py`: append `account_key`/`fingerprint`/`source` to LLM CSV output and, with `--apply-patterns`, pull categories/confidence from existing merchant patterns. Use `--verbose` to see pattern matching details.
- `fin-edit import-transactions`: persist enriched CSV rows into SQLite (preview by default; add `--apply` to write, `--default-confidence` to fill gaps, `--no-create-categories` to force manual taxonomy prep). Uncategorized transactions will be imported successfully.
- `fin-edit set-category`: correct individual transactions after import (dry-run before `--apply`).
- `fin-edit add-merchant-pattern`: remember high-confidence merchant/category mappings for future runs.
- `fin-query saved merchants --format json --min-count N`: retrieve merchant taxonomy for debugging.

## Common Errors
- **Missing CSV columns**: Verify LLM output has all required fields: `date,merchant,amount,original_description,account_name,institution,account_type,last_4_digits,category,subcategory,confidence`. Run postprocess.py to add `account_key`, `fingerprint`, and related columns.
- **Fingerprint collision on import**: Transaction already exists in database. This is expected behavior - duplicates are automatically skipped.
- **Invalid confidence value**: Ensure confidence is between 0 and 1. Use `--default-confidence 0.9` to fill empty cells during import.
- **Unknown category on import**: Either edit the CSV to use existing categories (check with `fin-query saved categories`) or allow creation by omitting `--no-create-categories` flag.
- **Account identification unclear**: If the LLM cannot determine which account a statement belongs to, pause and ask the user before importing. Rerun `.claude/skills/statement-processor/scripts/postprocess.py` after updating account metadata in the CSV.
- **Low-confidence rows (<0.7)**: Review and correct in the enriched CSV before import, or use `fin-edit set-category` after import to fix individual transactions.
- **Malformed amount**: Ensure amounts are positive decimals with two decimal places. Credits/refunds should be excluded upstream.

## Reference Material
- `.claude/skills/statement-processor/reference/csv-format.md` – canonical schema for enriched CSVs.

## Validation After Import
After successfully importing transactions, verify the results:
```bash
# Check recent imports
fin-query saved recent_imports --limit 5

# Verify transaction count for the month
fin-query saved transactions_month --param month=YYYY-MM --format table

# Check for uncategorized transactions (should be minimal if import went well)
fin-query saved uncategorized --limit 10
```

## Cross-Skill Transitions
- **After import**: Use the `transaction-categorizer` skill to handle uncategorized transactions (empty category/subcategory) or low-confidence categorizations (confidence < 0.7). The categorizer always tries an automated LLM pass for ALL uncategorized transactions, then falls back to interactive manual review only for leftovers. Patterns are learned automatically for future auto-categorization.
- **To analyze imported data**: Use `spending-analyzer` skill to run reports on the newly imported transactions
- **To query specific merchants or categories**: Use `ledger-query` skill for targeted lookups

## Next Steps for Agents
- Ensure enriched CSVs include `account_key`, `fingerprint`, and `source` columns before import.
- Use `--verbose` flag with `.claude/skills/statement-processor/scripts/postprocess.py` to see pattern matching details and identify uncategorized transactions.
- After import, transition to `transaction-categorizer` skill to handle uncategorized or low-confidence transactions:
  - The categorizer will ALWAYS attempt LLM categorization (Haiku) first for ALL uncategorized transactions
  - Only if leftovers remain after LLM categorization, the categorizer will use interactive manual review
  - Merchant patterns are learned automatically to improve future imports
- Review the `source` column in enriched CSVs to understand categorization provenance: `llm_extraction`, `pattern_match`, or empty (uncategorized).
