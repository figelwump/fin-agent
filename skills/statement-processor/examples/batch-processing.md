# Batch LLM Extraction

Process multiple statements in one session while keeping artifacts isolated under `~/.finagent/skills/statement-processor/`.

## 1. Prepare Working Directory

```bash
WORKDIR="$HOME/.finagent/skills/statement-processor/2025-09-batch"
SCRUBBED_DIR="$WORKDIR/scrubbed"
PROMPTS_DIR="$WORKDIR/prompts"
LLM_DIR="$WORKDIR/llm"
ENRICHED_DIR="$WORKDIR/enriched"

mkdir -p "$SCRUBBED_DIR" "$PROMPTS_DIR" "$LLM_DIR" "$ENRICHED_DIR"
```

## 2. Scrub All PDFs

```bash
for pdf in ~/statements/2025-09/*.pdf; do
  name=$(basename "${pdf%.pdf}")
  fin-scrub "$pdf" --output "$SCRUBBED_DIR/${name}-scrubbed.txt"
done
```

## 3. Build Batch Prompt(s)

```bash
python ~/GiantThings/repos/fin-agent/skills/statement-processor/preprocess.py \
  --batch \
  --input "$SCRUBBED_DIR"/*-scrubbed.txt \
  --max-merchants 200 \
  --max-statements-per-prompt 3 \
  --output "$PROMPTS_DIR/batch-prompt.txt"
```

If more than three statements are provided, the CLI emits multiple prompt chunks (e.g., `$PROMPTS_DIR/batch-prompt-part1.txt`).

## 4. Collect LLM Responses

Send each prompt chunk to the LLM and save the CSV responses as `$LLM_DIR/batch-1-llm.csv`, `$LLM_DIR/batch-2-llm.csv`, etc. Ensure each CSV preserves the standard header columns.

## 5. Enrich CSV Outputs

```bash
for csv in "$LLM_DIR"/batch-*-llm.csv; do
  base=$(basename "$csv" -llm.csv)
  python ~/GiantThings/repos/fin-agent/skills/statement-processor/postprocess.py \
    --input "$csv" \
    --output "$ENRICHED_DIR/${base}-enriched.csv"
done
```

## 6. Review & Consolidate

- Open each enriched CSV in `$ENRICHED_DIR` and review low-confidence rows (`confidence < 0.7`).
- Optionally concatenate them: `tail -n +2 "$ENRICHED_DIR/batch-2-enriched.csv" >> "$ENRICHED_DIR/batch-1-enriched.csv"` (keep one header).

## 7. Import Transactions

```bash
for enriched in "$ENRICHED_DIR"/batch-*-enriched.csv; do
  fin-edit import-transactions "$enriched"
done
```

Use `fin-query saved recent_imports --limit 20` to confirm the ingestion across accounts.

## 8. Preserve Artifacts

Retain scrubbed text, prompts, LLM outputs, and enriched CSVs for audit and debugging.
