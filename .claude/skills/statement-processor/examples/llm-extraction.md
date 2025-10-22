# LLM Extraction Walkthrough

This example demonstrates the end-to-end LLM pipeline for a single statement. All artifacts are staged under `~/.finagent/skills/statement-processor/<timestamp>/` so the working directory stays uncluttered.

## 1. Set Up Workspace

```bash
# Run from the repository root so relative paths resolve.
eval "$(.claude/skills/statement-processor/bootstrap.sh chase-2025-09)"
```

This exports helper environment variables:

```
FIN_STATEMENT_WORKDIR
FIN_STATEMENT_SCRUBBED_DIR
FIN_STATEMENT_PROMPTS_DIR
FIN_STATEMENT_LLM_DIR
FIN_STATEMENT_ENRICHED_DIR
```

The CLI harness resets CWD between commands, so rely on these exported paths instead of `cd`.

## 2. Scrub the Statement

```bash
PDF_PATH="$HOME/statements/chase-september.pdf"  # Replace with the user's actual statement PDF
fin-scrub "$PDF_PATH" \
  --output-dir "$FIN_STATEMENT_WORKDIR"
```

`$FIN_STATEMENT_SCRUBBED_DIR/chase-september-scrubbed.txt` contains the redacted statement text that the LLM will see.

## 3. Build the Prompt

```bash
python .claude/skills/statement-processor/preprocess.py \
  --workdir "$FIN_STATEMENT_WORKDIR" \
  --max-merchants 150
```

This pulls existing merchant/category taxonomies from SQLite and renders an extraction prompt into `$FIN_STATEMENT_PROMPTS_DIR/chase-september-prompt.txt`.

## 4. Run the LLM

Send the prompt to your LLM of choice (Claude in this example) and save the CSV reply as `$FIN_STATEMENT_LLM_DIR/chase-september-llm.csv`. Ensure the LLM output has the header `date,merchant,amount,original_description,account_name,institution,account_type,category,subcategory,confidence`.

## 5. Post-Process the CSV

```bash
python .claude/skills/statement-processor/postprocess.py \
  --workdir "$FIN_STATEMENT_WORKDIR"
```

This processes every CSV under `$FIN_STATEMENT_LLM_DIR`, adds `account_key` and `fingerprint` columns while normalising merchants and confidence values, and writes enriched files to `$FIN_STATEMENT_ENRICHED_DIR`.

## 6. Review & Correct Low-Confidence Rows

- Inspect `$FIN_STATEMENT_ENRICHED_DIR/chase-september-enriched.csv` for any `confidence < 0.7`.
- If a category needs to change now, edit the CSV and rerun post-processing (to regenerate fingerprints) or plan to run:
  ```bash
  fin-edit set-category --fingerprint <fingerprint> \
    --category "Food & Dining" --subcategory "Coffee" \
    --confidence 1.0 --method claude:interactive
  fin-edit --apply set-category …
  ```
- Note merchants that should be remembered; after confirming the mapping with the user, capture it via:
  ```bash
  fin-edit add-merchant-pattern --pattern 'STARBUCKS%' \
    --category "Food & Dining" --subcategory "Coffee" \
    --confidence 0.95
  fin-edit --apply add-merchant-pattern …
  ```

## 7. Import into SQLite

```bash
# Preview (dry-run)
fin-edit import-transactions "$FIN_STATEMENT_ENRICHED_DIR/chase-september-enriched.csv"

# Apply after confirming the preview output (auto-learn merchants ≥0.9)
fin-edit --apply import-transactions "$FIN_STATEMENT_ENRICHED_DIR/chase-september-enriched.csv" \
  --learn-patterns --learn-threshold 0.9
```

Add `--default-confidence 0.9` if you want to fill empty confidence cells, or `--no-create-categories` to abort when a category is missing. The tool automatically de-duplicates using fingerprints. Use `fin-query saved recent_transactions --limit 10` to validate new records.

## 8. Archive Artifacts

Keep the scrubbed source text, prompts, LLM CSV, and enriched CSV inside the run directory for auditing. Clean them up once reconciled with the user.
