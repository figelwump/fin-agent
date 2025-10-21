# Prompt Loop with Minimal Commands

While the LLM interaction prevents a fully automated Unix pipeline, you can still minimise manual file management by staging everything under a single workspace.

## 1. Initialise Workspace

```bash
WORKDIR="$HOME/.finagent/skills/statement-processor/$(date +%Y%m%d-%H%M)"
PDF_GLOB="$HOME/statements/*.pdf"  # Replace with the user's actual statement locations

mkdir -p "$WORKDIR"
```

## 2. Scrub Statements in One Pass

```bash
for pdf in $PDF_GLOB; do
  fin-scrub "$pdf" --output-dir "$WORKDIR"
done
```

Scrubbed text files land in `$WORKDIR/scrubbed/` with auto-generated names.

## 3. Build Prompts

```bash
python ~/GiantThings/repos/fin-agent/skills/statement-processor/preprocess.py \
  --batch \
  --input "$WORKDIR/scrubbed"/*-scrubbed.txt \
  --max-merchants 200 \
  --output-dir "$WORKDIR"
```

Prompts are written to `$WORKDIR/prompts/`. Use `pbcopy`/`xclip` to place a prompt on the clipboard:

```bash
pbcopy < "$WORKDIR/prompts/chase-credit-202401-prompt.txt"  # macOS example
```

## 4. Capture LLM Output

After the LLM replies, save each CSV to `$WORKDIR/llm/` (e.g., `chase-credit-202401-llm.csv`).

## 5. Enrich and Import

```bash
for csv in "$WORKDIR/llm"/*.csv; do
  python ~/GiantThings/repos/fin-agent/skills/statement-processor/postprocess.py \
    --input "$csv" \
    --output-dir "$WORKDIR"
done

for enriched in "$WORKDIR/enriched"/*.csv; do
  fin-edit import-transactions "$enriched"
done
```

All intermediate files remain in `$WORKDIR`, making it easy to share with the user or revisit for debugging.
