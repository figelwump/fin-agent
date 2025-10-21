Branch: main
Plan: plans/plan_llm_statement_processor_102025.md
Last Updated: 2025-10-21

## Status
- Phase 1 (merchants saved query) ✅
- Phase 2 (preprocess/postprocess helpers + templates) ✅
- Phase 3 in progress (skill docs/examples refreshed; awaiting integration work)

## Statement Imports (LLM Pipeline)
- Use the `statement-processor` skill for all PDF-to-CSV imports.
- Recommended workspace: `~/.finagent/skills/statement-processor/<timestamp>/` with subfolders created automatically by the CLI (`scrubbed/`, `prompts/`, `llm/`, `enriched/`).
- Key commands:
  - `fin-scrub <pdf> --output-dir $WORKDIR`
  - `python skills/statement-processor/preprocess.py --input $WORKDIR/scrubbed/* --output-dir $WORKDIR [--batch ...]`
  - Call the LLM manually, save CSV responses in `$WORKDIR/llm/`.
  - `python skills/statement-processor/postprocess.py --input $WORKDIR/llm/*.csv --output-dir $WORKDIR`
  - `fin-edit import-transactions $WORKDIR/enriched/*.csv`
- Low-confidence (`confidence < 0.7`) rows must be reviewed with the user before import.

## Next Steps
- Implement interactive wiring inside the statement-processor skill (Phase 3 tasks in the plan).
- Update or retire remaining legacy docs after postprocess integration lands.
