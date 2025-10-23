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
5. Enrich CSV and apply known rules: `python .claude/skills/statement-processor/scripts/postprocess.py --workdir "$FIN_STATEMENT_WORKDIR" --apply-patterns`.
6. Build a prompt for any uncategorized rows (optional): `python .claude/skills/statement-processor/scripts/categorize_leftovers.py --workdir "$FIN_STATEMENT_WORKDIR" --output "$FIN_STATEMENT_WORKDIR/prompt-leftovers.txt"`. If the tool reports “No uncategorized transactions found” you can skip this step; otherwise send the prompt to **Claude Haiku 4.5** and apply the returned CSV before import.
7. Import validated rows: `fin-edit import-transactions "$FIN_STATEMENT_ENRICHED_DIR"/file.csv` (preview) then `fin-edit --apply import-transactions "$FIN_STATEMENT_ENRICHED_DIR"/file.csv --learn-patterns --learn-threshold 0.9` once the review passes. Add `--no-create-categories` if you want to fail instead of auto-creating new categories.

The prompt builder loads the live taxonomy from SQLite automatically. For debugging you can inspect the payload by running `python .claude/skills/statement-processor/scripts/preprocess.py --input scrubbed.txt --emit-json`, or export the same data manually with:
- Categories: `fin-query saved categories --format json > categories.json`
- Merchants: `fin-query saved merchants --min-count 2 --format json > merchants.json` (adjust `--min-count`/`--limit` as needed).

Batch Workflow
1. Automate scrubbing + prompt prep with the helper script:
   - `.claude/skills/statement-processor/scripts/run_batch.sh --workdir "$FIN_STATEMENT_WORKDIR" --max-merchants 150 --max-statements-per-prompt 3 statements/*.pdf`
   - The script cleans stale `*-scrubbed.txt` files in the workspace, runs `fin-scrub` for each PDF, and invokes `preprocess.py --batch` so prompts land in `$FIN_STATEMENT_PROMPTS_DIR` using the default naming scheme.
2. Run the LLM once per emitted prompt chunk and save each CSV response (e.g., `chunk-1.csv`).
3. Post-process every CSV: `python .claude/skills/statement-processor/scripts/postprocess.py --input chunk-1.csv --output chunk-1-enriched.csv --apply-patterns`
4. Generate a single prompt for any remaining uncategorized rows: `python .claude/skills/statement-processor/scripts/categorize_leftovers.py --workdir "$FIN_STATEMENT_WORKDIR" --output "$FIN_STATEMENT_WORKDIR/prompt-leftovers.txt"`.
5. Concatenate or import each enriched CSV via `fin-edit import-transactions` (preview) and rerun with `--apply` when ready. Use `--default-confidence` to fill empty confidence cells when needed.

Working Directory
- Use `bootstrap.sh` to create a deterministic run directory (e.g., `eval "$(.claude/skills/statement-processor/scripts/bootstrap.sh chase-2025-09)"`). The script works for both single and batch workflows.
- All helper CLIs accept `--workdir` so they can auto-discover `scrubbed/`, `prompts/`, `llm/`, and `enriched/` subdirectories.
- The harness resets the shell’s CWD between commands; rely on the exported environment variables or absolute paths instead of `cd`.
- Store scrubbed statements, prompts, raw LLM CSVs, and enriched CSVs inside the workspace and clean up once the import is committed to the database.

Handling Low Confidence
- The prompt instructs the LLM to lower `confidence` (<0.7) whenever unsure.
- Review low-confidence rows first; edit merchants/categories before import or after import using `fin-edit`.
- If account metadata is unclear, pause and ask the user which account the statement belongs to; rerun post-processing once metadata is confirmed.
- After the user approves a correction, update the record via `fin-edit set-category` (dry-run first) and bump confidence to 1.0 when rerunning `import-transactions`.
- When a user wants future transactions auto-categorised, run `fin-edit add-merchant-pattern` (preview, then `--apply`) with the deterministic pattern key (use `python -c "from fin_cli.shared.merchants import merchant_pattern_key; print(merchant_pattern_key('MERCHANT RAW'))"` if needed).
- For bulk high-confidence learning, prefer `fin-edit --apply import-transactions … --learn-patterns --learn-threshold 0.9`; keep manual `add-merchant-pattern` for edge cases or low-confidence merchants.
- When you do need an LLM to categorise a handful of leftover merchants, prefer a lightweight model (Claude Haiku 4.5) for the categorisation micro-prompt to keep latency and cost down; reserve Sonnet 4.5 for the main extraction step.

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
- `python .claude/skills/statement-processor/scripts/postprocess.py`: append `account_key`/`fingerprint` to LLM CSV output and, with `--apply-patterns`, pull categories/confidence from existing merchant patterns.
- `python .claude/skills/statement-processor/scripts/categorize_leftovers.py`: assemble a prompt for uncategorized merchants after rules have been applied.
- `fin-edit import-transactions`: persist enriched CSV rows into SQLite (preview by default; add `--apply` to write, `--default-confidence` to fill gaps, `--no-create-categories` to force manual taxonomy prep).
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
- **After import with low-confidence transactions**: Switch to `transaction-categorizer` skill to interactively review and correct low-confidence categorizations (confidence < 0.7)
- **To analyze imported data**: Use `spending-analyzer` skill to run reports on the newly imported transactions
- **To query specific merchants or categories**: Use `ledger-query` skill for targeted lookups

Next Steps for Agents
- Ensure enriched CSVs include `account_key` and `fingerprint` before import.
- Capture review notes for low-confidence rows; feed corrections back into prompt parameters when retrying.
- Report recurring merchant/category gaps so the taxonomy can be extended via rules or prompt tweaks.
