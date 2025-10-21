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
PDF_GLOB=~/statements/2025-09/*.pdf  # Replace with the user's actual statement locations
for pdf in $PDF_GLOB; do
  fin-scrub "$pdf" --output-dir "$WORKDIR"
done
```

## 3. Build Batch Prompt(s)

```bash
python ~/GiantThings/repos/fin-agent/.claude/skills/statement-processor/preprocess.py \
  --batch \
  --input "$SCRUBBED_DIR"/*-scrubbed.txt \
  --max-merchants 200 \
  --max-statements-per-prompt 3 \
  --output-dir "$WORKDIR"
```

If more than three statements are provided, the CLI emits multiple prompt chunks (e.g., `$PROMPTS_DIR/batch-prompt-part1.txt`).

## 4. Collect LLM Responses

Send each prompt chunk to the LLM and save the CSV responses as `$LLM_DIR/batch-1-llm.csv`, `$LLM_DIR/batch-2-llm.csv`, etc. Ensure each CSV preserves the standard header columns.

> Note: stick to the documented preprocess → LLM → postprocess flow. Avoid generating ad-hoc scripts to extract transactions directly from prompt text; the LLM review step is required to produce the CSV outputs that `postprocess.py` expects.

## 5. Enrich CSV Outputs

```bash
for csv in "$LLM_DIR"/batch-*-llm.csv; do
  base=$(basename "$csv" -llm.csv)
  python ~/GiantThings/repos/fin-agent/.claude/skills/statement-processor/postprocess.py \
    --input "$csv" \
    --output-dir "$WORKDIR"
done
```

## 6. Review, Correct, and Capture Patterns

- Open each enriched CSV in `$ENRICHED_DIR` and review low-confidence rows (`confidence < 0.7`).
- For confirmed fixes, update the CSV now or stage CLI corrections:
  ```bash
  fin-edit set-category --fingerprint <fingerprint> \
    --category "Auto & Transport" --subcategory "Parking"
  ```
- When the user asks to remember a merchant/category pairing, run `fin-edit add-merchant-pattern` (dry-run first) with the normalized pattern key (see below) so future statements skip the LLM.
- Optionally concatenate enriched CSVs after review: `tail -n +2 "$ENRICHED_DIR/batch-2-enriched.csv" >> "$ENRICHED_DIR/batch-1-enriched.csv"` (keep one header).

Tip: derive the normalized key before calling `add-merchant-pattern`:
```bash
python -c "from fin_cli.shared.merchants import merchant_pattern_key; print(merchant_pattern_key('STARBUCKS #1234'))"
```

## 7. Import Transactions

```bash
for enriched in "$ENRICHED_DIR"/batch-*-enriched.csv; do
  fin-edit import-transactions "$enriched"           # preview
  fin-edit --apply import-transactions "$enriched"  # write once approved
done
```

Use `fin-query saved recent_imports --limit 20` to confirm the ingestion across accounts.

## 8. Preserve Artifacts

Retain scrubbed text, prompts, LLM outputs, and enriched CSVs for audit and debugging.
