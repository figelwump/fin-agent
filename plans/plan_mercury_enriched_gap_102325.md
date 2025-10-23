# Plan: Investigate Mercury 2025-04-05 Enriched Chunk Mismatch (2025-10-23)

## Phase 1 – Reproduce & Quantify
- [x] Activate project virtualenv for CLI access (`source .venv/bin/activate`). *(2025-10-23; required for fin-* CLI usage)*
- [x] Inspect scrubbed source CSVs to confirm expected transaction count. *(Scrubbed Mercury Apr/May statements list 4 + 17 ledger lines respectively)*
- [x] Inspect enriched chunk CSV row count for comparison. *(chunk-1-enriched-test.csv contains header + 1 transaction for 2025-05-30)*

## Phase 2 – Trace Processing Pipeline
- [x] Review statement processor configuration for this import batch. *(No custom config in ~/.finagent/config.yaml; defaults in `postprocess.py` apply auto-approve=0.8 etc.)*
- [x] Inspect intermediate outputs/logs to see where transactions drop. *(LLM chunk (`llm/chunk-1.csv`) retains 5 rows; drop occurs between LLM output and enriched CSV.)*
- [x] Verify enrichment scripts/steps that write `chunk-1-enriched-test.csv`. *(Found indentation bug in `.claude/skills/statement-processor/scripts/postprocess.py` causing only final row to be appended.)*

## Phase 3 – Diagnose & Outline Fix
- [ ] Identify the root cause behind the missing transactions.
- [ ] Document proposed remediation (code change, config, rerun steps).
- [ ] Note any required follow-up actions or tests.

## Notes
- Dataset paths: `~/.finagent/skills/statement-processor/mercury-2025-04-05-20251022-170227/`.
- Core CSVs: `scrubbed/**`, `enriched/chunk-1-enriched-test.csv`.
- Enrichment likely handled by statement processor skill scripts.
