# Plan: Investigate Mercury 2025-04-05 Enriched Chunk Mismatch (2025-10-23)

## Phase 1 – Reproduce & Quantify
- [x] Activate project virtualenv for CLI access (`source .venv/bin/activate`). *(2025-10-23; required for fin-* CLI usage)*
- [x] Inspect scrubbed source CSVs to confirm expected transaction count. *(Scrubbed Mercury Apr/May statements list 4 + 17 ledger lines respectively)*
- [x] Inspect enriched chunk CSV row count for comparison. *(chunk-1-enriched-test.csv contains header + 1 transaction for 2025-05-30)*

## Phase 2 – Trace Processing Pipeline
- [x] Review statement processor configuration for this import batch. *(No custom config in ~/.finagent/config.yaml; defaults in `postprocess.py` apply auto-approve=0.8 etc.)*
- [x] Inspect intermediate outputs/logs to see where transactions drop. *(LLM chunk (`llm/chunk-1.csv`) retains 5 rows; drop occurs between LLM output and enriched CSV.)*
- [x] Verify enrichment scripts/steps that write `chunk-1-enriched-test.csv`. *(Found indentation bug in `scripts/postprocess.py` causing only final row to be appended.)*

## Phase 3 – Diagnose & Outline Fix
- [ ] Confirm statement-processor postprocess flow keeps all LLM rows (multi-row regression test).
- [ ] Trace how low-confidence rows flow into `categorize_leftovers.py` and why enriched CSV edits are manual-only.
- [ ] Capture remediation options (script changes vs. workflow guidance) plus validation requirements.

## Phase 4 – Automate Leftover Categorization Round-Trip
- [ ] Update `categorize_leftovers.py` prompt + schema to tag each row with the transaction fingerprint (or equivalent stable ID).
- [ ] Add an automation entrypoint (new script or postprocess flag) that merges leftover decisions back into enriched CSVs safely.
- [ ] Cover the new workflow with unit/integration tests (fingerprint propagation + merge happy-path & mismatch handling).
- [ ] Document the updated flow in `SKILL.md` / helper notes so agents stop editing enriched CSVs manually.

## Phase 5 – Validation & Regression Guardrails
- [ ] Re-run the Mercury April 2025 workspace end-to-end (postprocess → leftovers merge → fin-edit preview) to confirm import passes.
- [ ] Add regression tests or fixtures ensuring multi-row enriched outputs and leftover merges remain stable.
- [ ] Summarize follow-up actions (pattern learning tweaks, config changes) if any gaps remain.

## Notes
- Dataset paths: `~/.finagent/skills/statement-processor/mercury-2025-04-05-20251022-170227/`.
- Core CSVs: `scrubbed/**`, `enriched/chunk-1-enriched-test.csv`.
- Enrichment likely handled by statement processor skill scripts.
