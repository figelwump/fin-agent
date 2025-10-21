# LLM Extraction Walkthrough

This example demonstrates the end-to-end LLM pipeline for a single statement. All artifacts are staged under `~/.finagent/skills/statement-processor/<timestamp>/` so the working directory stays uncluttered.

## 1. Set Up Workspace

```bash
WORKDIR="$HOME/.finagent/skills/statement-processor/2025-09-15"
mkdir -p "$WORKDIR"
cd "$WORKDIR"
```

Copy the redacted PDF (or place it in this directory) as `chase-september.pdf`.

## 2. Scrub the Statement

```bash
fin-scrub chase-september.pdf --output chase-september-scrubbed.txt
```

`chase-september-scrubbed.txt` contains the redacted statement text that the LLM will see.

## 3. Build the Prompt

```bash
python ~/GiantThings/repos/fin-agent/skills/statement-processor/preprocess.py \?
  --input chase-september-scrubbed.txt \?
  --output chase-september-prompt.txt \?
  --max-merchants 150
```

This pulls existing merchant/category taxonomies from SQLite and renders an extraction prompt into `chase-september-prompt.txt`.

## 4. Run the LLM

Send the prompt to your LLM of choice (Claude in this example) and save the CSV reply as `chase-september-llm.csv`. Ensure the LLM output has the header `date,merchant,amount,original_description,account_name,institution,account_type,category,subcategory,confidence`.

## 5. Post-Process the CSV

```bash
python ~/GiantThings/repos/fin-agent/skills/statement-processor/postprocess.py \?
  --input chase-september-llm.csv \?
  --output chase-september-enriched.csv
```

This adds `account_key` and `fingerprint` columns while normalising merchants and confidence values.

## 6. Review Low-Confidence Rows

Inspect `chase-september-enriched.csv` for any `confidence < 0.7`. Adjust merchants/categories directly in the CSV or plan to edit them after import via `fin-edit`.

## 7. Import into SQLite

```bash
fin-edit import-transactions chase-september-enriched.csv
```

The tool automatically de-duplicates using fingerprints. Use `fin-query saved recent_transactions --limit 10` to validate new records.

## 8. Clean Up

Archive or delete the intermediate files as needed. Retain `chase-september-enriched.csv` if further review is expected.
