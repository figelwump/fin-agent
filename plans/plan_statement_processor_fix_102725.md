# plan_statement_processor_fix_102725

## Phase 1 – Investigate & Reproduce
- [ ] Confirm the failing `postprocess.py` execution using the reported `SESSION_SLUG` workspace to capture current error output.
- [ ] Inspect the raw LLM CSVs under `llm/` to document their headers and any schema mismatches (e.g., missing `last_4_digits`).
- [ ] Record how `_repair_csv_formatting` responds to the problematic file (field counts, warnings).

## Phase 2 – Implement Robust CSV Handling
- [ ] Update the post-processing pipeline to tolerate legacy CSVs without `last_4_digits`, deriving or defaulting the value and falling back to v1 account keys when necessary.
- [ ] Ensure the updater maintains strict validation for genuinely malformed rows while avoiding false positives on header-only CSVs.
- [ ] Document the chosen fallback logic inline for future agents.

## Phase 3 – Tests & Verification
- [ ] Extend `tests/statement_processor/test_postprocess.py` (or add new coverage) to validate the new fallback behaviour.
- [ ] Rerun the failing `postprocess.py` command to verify the fix end-to-end.
- [ ] Execute targeted `pytest` scope for statement-processor utilities to confirm the suite stays green.

## Notes
- Workspace: `/Users/vishal/.finagent/skills/statement-processor/mercury-2550-20251027`
- Key script: `.claude/skills/statement-processor/scripts/postprocess.py`
- Ensure virtualenv is activated (`source .venv/bin/activate`) before running Python or pytest commands.
