# LLM Extraction Walkthrough

This example demonstrates the end-to-end LLM pipeline for a single statement. All artifacts are staged under `~/.finagent/skills/statement-processor/<timestamp>/` so the working directory stays uncluttered.

## 1. Set Up Workspace

```bash
WORKDIR="$HOME/.finagent/skills/statement-processor/2025-09-15"
SCRUBBED_DIR="$WORKDIR/scrubbed"
PROMPTS_DIR="$WORKDIR/prompts"
LLM_DIR="$WORKDIR/llm"
ENRICHED_DIR="$WORKDIR/enriched"

mkdir -p "$SCRUBBED_DIR" "$PROMPTS_DIR" "$LLM_DIR" "$ENRICHED_DIR"
```

## 2. Scrub the Statement

```bash
PDF_PATH="$HOME/statements/chase-september.pdf"  # Replace with the user's actual statement PDF
fin-scrub "$PDF_PATH" \
  --output-dir "$WORKDIR"
```

`$SCRUBBED_DIR/chase-september-scrubbed.txt` contains the redacted statement text that the LLM will see.

## 3. Build the Prompt

```bash
python ~/GiantThings/repos/fin-agent/skills/statement-processor/preprocess.py \
  --input "$SCRUBBED_DIR/chase-september-scrubbed.txt" \
  --output-dir "$WORKDIR" \
  --max-merchants 150
```

This pulls existing merchant/category taxonomies from SQLite and renders an extraction prompt into `$PROMPTS_DIR/chase-september-prompt.txt`.

## 4. Run the LLM

Send the prompt to your LLM of choice (Claude in this example) and save the CSV reply as `$LLM_DIR/chase-september-llm.csv`. Ensure the LLM output has the header `date,merchant,amount,original_description,account_name,institution,account_type,category,subcategory,confidence`.

## 5. Post-Process the CSV

```bash
python ~/GiantThings/repos/fin-agent/skills/statement-processor/postprocess.py \
  --input "$LLM_DIR/chase-september-llm.csv" \
  --output-dir "$WORKDIR"
```

This adds `account_key` and `fingerprint` columns while normalising merchants and confidence values.

## 6. Review Low-Confidence Rows

Inspect `$ENRICHED_DIR/chase-september-enriched.csv` for any `confidence < 0.7`. Adjust merchants/categories directly in the CSV or plan to edit them after import via `fin-edit`.

## 7. Import into SQLite

```bash
fin-edit import-transactions "$ENRICHED_DIR/chase-september-enriched.csv"
```

The tool automatically de-duplicates using fingerprints. Use `fin-query saved recent_transactions --limit 10` to validate new records.
