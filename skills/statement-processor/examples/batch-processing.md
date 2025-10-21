# Batch LLM Extraction

Process multiple statements in one session while keeping artifacts isolated under `~/.finagent/workflows/statement-processor/`.

## 1. Prepare Working Directory

```bash
WORKDIR="$HOME/.finagent/workflows/statement-processor/2025-09-batch"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

cp ~/statements/chase-2025-09.pdf ./
cp ~/statements/bofa-2025-09.pdf ./
cp ~/statements/mercury-2025-09.pdf ./
```

## 2. Scrub All PDFs

```bash
for pdf in *.pdf; do
  fin-scrub "$pdf" --output "${pdf%.pdf}-scrubbed.txt"
done
```

## 3. Build Batch Prompt(s)

```bash
python ~/GiantThings/repos/fin-agent/skills/statement-processor/preprocess.py \?
  --batch \?
  --input *-scrubbed.txt \?
  --max-merchants 200 \?
  --max-statements-per-prompt 3 \?
  --output batch-prompt.txt
```

If more than three statements are provided, the CLI emits multiple prompt chunks (e.g., `batch-prompt-part1.txt`).

## 4. Collect LLM Responses

Send each prompt chunk to the LLM and save the CSV responses as `batch-1-llm.csv`, `batch-2-llm.csv`, etc. Ensure each CSV preserves the standard header columns.

## 5. Enrich CSV Outputs

```bash
for csv in batch-*-llm.csv; do
  python ~/GiantThings/repos/fin-agent/skills/statement-processor/postprocess.py \?
    --input "$csv" \?
    --output "${csv%-llm.csv}-enriched.csv"
done
```

## 6. Review & Consolidate

- Open each enriched CSV and review low-confidence rows (`confidence < 0.7`).
- Optionally concatenate them: `tail -n +2 batch-2-enriched.csv >> batch-1-enriched.csv` (keep one header).

## 7. Import Transactions

```bash
fin-edit import-transactions batch-1-enriched.csv
fin-edit import-transactions batch-2-enriched.csv
```

Use `fin-query saved recent_imports --limit 20` to confirm the ingestion across accounts.

## 8. Cleanup

Archive prompts, scrubbed text, and enriched CSVs for audit. Remove intermediate LLM outputs once validated.
