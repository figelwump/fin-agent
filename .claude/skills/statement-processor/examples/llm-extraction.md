# LLM Extraction Walkthrough

This example demonstrates the end-to-end LLM pipeline for a single statement. All artifacts are staged under `~/.finagent/skills/statement-processor/<timestamp>/` so the working directory stays uncluttered.

## 1. Set Up Workspace

```bash
# Run from the repository root so relative paths resolve.
eval "$(scripts/bootstrap.sh chase-2025-09)"
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
python scripts/preprocess.py \
  --workdir "$FIN_STATEMENT_WORKDIR" \
  --max-merchants 150
```

This pulls existing merchant/category taxonomies from SQLite and renders an extraction prompt into `$FIN_STATEMENT_PROMPTS_DIR/chase-september-prompt.txt`.

## 4. Run the LLM

Send the prompt to your LLM of choice and save the CSV reply as `$FIN_STATEMENT_LLM_DIR/chase-september-llm.csv`. Ensure the LLM output has the header `date,merchant,amount,original_description,account_name,institution,account_type,category,subcategory,confidence`.

## 5. Post-Process the CSV

```bash
python scripts/postprocess.py \
  --workdir "$FIN_STATEMENT_WORKDIR" \
  --apply-patterns \
  --verbose
```

This processes every CSV under `$FIN_STATEMENT_LLM_DIR`, adds `account_key`, `fingerprint`, and `source` columns while normalising merchants and confidence values, applies known merchant patterns, and writes enriched files to `$FIN_STATEMENT_ENRICHED_DIR`. The `--verbose` flag shows which patterns matched and which transactions remain uncategorized.

## 6. Review the Enriched CSV

- Inspect `$FIN_STATEMENT_ENRICHED_DIR/chase-september-enriched.csv` to understand categorization results:
  - Check the `source` column: `llm_extraction` (from initial LLM), `pattern_match` (from merchant patterns DB), or empty (uncategorized)
  - Review transactions with `confidence < 0.7` or empty category/subcategory
- The `--verbose` output from step 5 shows which patterns matched and which merchants have no patterns yet
- Uncategorized transactions (empty category/subcategory) will be imported successfully in the next step

## 7. Import into SQLite

```bash
# Preview (dry-run)
fin-edit import-transactions "$FIN_STATEMENT_ENRICHED_DIR/chase-september-enriched.csv"

# Apply after confirming the preview output (auto-learn merchants ≥0.9)
fin-edit --apply import-transactions "$FIN_STATEMENT_ENRICHED_DIR/chase-september-enriched.csv" \
  --learn-patterns --learn-threshold 0.9
```

Add `--default-confidence 0.9` if you want to fill empty confidence cells, or `--no-create-categories` to abort when a category is missing. The tool automatically de-duplicates using fingerprints and will import uncategorized transactions successfully. Use `fin-query saved recent_transactions --limit 10` to validate new records.

## 8. Categorize Remaining Transactions

For any uncategorized or low-confidence transactions, use the `transaction-categorizer` skill:

```bash
# Check for uncategorized transactions
fin-query saved uncategorized --limit 20

# Switch to transaction-categorizer skill
# The skill always tries an automated LLM pass first for ALL uncategorized transactions
# Only if leftovers remain, it will use interactive manual review
# Merchant patterns are learned automatically for future auto-categorization
```

The categorizer uses an LLM-first approach for cost efficiency: it attempts bulk categorization for all uncategorized transactions, then falls back to interactive review only for leftovers. Patterns are learned automatically to improve future imports.

## 9. Archive Artifacts

Keep the scrubbed source text, prompts, LLM CSV, and enriched CSV inside the run directory for auditing. Clean them up once reconciled with the user.
