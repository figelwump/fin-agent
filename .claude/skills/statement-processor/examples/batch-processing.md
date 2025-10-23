# Batch LLM Extraction

Process multiple statements in one session while keeping artifacts isolated under `~/.finagent/skills/statement-processor/`.

## 1. Prepare Working Directory

```bash
# Run from the repository root so relative paths resolve.
eval "$(.claude/skills/statement-processor/scripts/bootstrap.sh chase-2025-09-batch)"
```

The script exports:

```
FIN_STATEMENT_WORKDIR
FIN_STATEMENT_SCRUBBED_DIR
FIN_STATEMENT_PROMPTS_DIR
FIN_STATEMENT_LLM_DIR
FIN_STATEMENT_ENRICHED_DIR
```

## 2. Automate Scrubbing + Prompt Prep

Use the helper to run workflow steps 1–2 in one go:

```bash
.claude/skills/statement-processor/scripts/run_batch.sh \
  --workdir "$FIN_STATEMENT_WORKDIR" \
  --max-merchants 200 \
  --max-statements-per-prompt 3 \
  ~/statements/2025-09/*.pdf
```

Example output (truncated):

```
No --workdir provided. Using /Users/alex/.finagent/skills/statement-processor/20251022-181530
Scrubbing PDF statements...
  [1/3] fin-scrub /Users/alex/statements/2025-09/Chase.pdf -> .../scrubbed/Chase-scrubbed.txt
  [2/3] fin-scrub /Users/alex/statements/2025-09/BofA.pdf -> .../scrubbed/BofA-scrubbed.txt
  [3/3] fin-scrub /Users/alex/statements/2025-09/Mercury.pdf -> .../scrubbed/Mercury-scrubbed.txt
Generating prompts via preprocess.py...
Wrote prompt to .../prompts/chase-batch-prompt.txt

Batch preparation complete.
Workspace: /Users/alex/.finagent/skills/statement-processor/20251022-181530
Scrubbed statements:
  - .../scrubbed/Chase-scrubbed.txt
  - .../scrubbed/BofA-scrubbed.txt
  - .../scrubbed/Mercury-scrubbed.txt
Prompt chunks:
  - .../prompts/chase-batch-prompt.txt

Next steps:
  1. Run the LLM over each prompt in the order emitted above and save the CSV responses.
  2. Post-process each CSV with postprocess.py.
  3. Review/import transactions via fin-edit.
```

The script deletes stale `*-scrubbed.txt` files (unless `--no-clean` is used), reruns `fin-scrub` for each PDF, and invokes `preprocess.py --batch` so chunk files land in `$FIN_STATEMENT_PROMPTS_DIR` (`$FIN_STATEMENT_WORKDIR/prompts`).

## 4. Collect LLM Responses

Send each prompt chunk to the LLM and save the CSV responses as `$FIN_STATEMENT_LLM_DIR/batch-1-llm.csv`, `$FIN_STATEMENT_LLM_DIR/batch-2-llm.csv`, etc. Ensure each CSV preserves the standard header columns.

> Note: stick to the documented preprocess → LLM → postprocess flow. Avoid generating ad-hoc scripts to extract transactions directly from prompt text; the LLM review step is required to produce the CSV outputs that `postprocess.py` expects.

## 5. Enrich CSV Outputs

```bash
python .claude/skills/statement-processor/scripts/postprocess.py \
  --workdir "$FIN_STATEMENT_WORKDIR" \
  --apply-patterns
```

This processes all CSV files in `$FIN_STATEMENT_LLM_DIR`, adds `account_key` and `fingerprint` columns, normalizes merchants and confidence values, and writes enriched files to `$FIN_STATEMENT_ENRICHED_DIR`.

## 6. Review, Correct, and Capture Patterns

- Open each enriched CSV in `$FIN_STATEMENT_ENRICHED_DIR` and review low-confidence rows (`confidence < 0.7`).
- For confirmed fixes, update the CSV now or stage CLI corrections:
  ```bash
  fin-edit set-category --fingerprint <fingerprint> \
    --category "Auto & Transport" --subcategory "Parking"
  ```
- When the user asks to remember a merchant/category pairing, run `fin-edit add-merchant-pattern` (dry-run first) with the normalized pattern key (see below) so future statements skip the LLM.
- Optionally concatenate enriched CSVs after review: `tail -n +2 "$FIN_STATEMENT_ENRICHED_DIR/batch-2-enriched.csv" >> "$FIN_STATEMENT_ENRICHED_DIR/batch-1-enriched.csv"` (keep one header).
- Build a prompt for the remaining blanks (if any):
  ```bash
  python .claude/skills/statement-processor/scripts/categorize_leftovers.py \
    --workdir "$FIN_STATEMENT_WORKDIR" \
    --output "$FIN_STATEMENT_WORKDIR/prompt-leftovers.txt"
  ```
  If the script reports leftovers, send the prompt to **Claude Haiku 4.5** and merge the resulting CSV before import.

Tip: derive the normalized key before calling `add-merchant-pattern`:
```bash
python -c "from fin_cli.shared.merchants import merchant_pattern_key; print(merchant_pattern_key('STARBUCKS #1234'))"
```

## 7. Import Transactions

```bash
for enriched in "$FIN_STATEMENT_ENRICHED_DIR"/batch-*-enriched.csv; do
  fin-edit import-transactions "$enriched"           # preview
  fin-edit --apply import-transactions "$enriched" \
    --learn-patterns --learn-threshold 0.9          # write once approved & learn
done
```

## 8. Validate Imports

After importing all batches, verify the results:
```bash
# Check recent imports across all batches
fin-query saved recent_imports --limit 20

# Verify transaction count for the month
fin-query saved transactions_month --param month=YYYY-MM --format table

# Check for uncategorized transactions
fin-query saved uncategorized --limit 10

# Verify total count matches expectations
fin-query sql "SELECT COUNT(*) as total FROM transactions WHERE date >= 'YYYY-MM-01' AND date < 'YYYY-MM+1-01'"
```

## 9. Preserve Artifacts

Retain scrubbed text, prompts, LLM outputs, and enriched CSVs for audit and debugging.
The CLI harness resets CWD between commands, so rely on the exported variables instead of `cd`.
