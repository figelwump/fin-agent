## plan_statement_processor_scrub_config_102825

- [x] Phase 1 – Confirm existing guidance
  - [x] Review `.claude/skills/statement-processor/SKILL.md` sections around fin-scrub usage and failure guidance *(2025-10-28 – noted Step 1 scrub loop, no config escalation guidance yet.)*
  - [x] Inspect `fin_cli/fin_scrub/main.py` for config loading behaviour to document accurately *(2025-10-28 – confirmed layered merge: package defaults → `~/.finagent/fin-scrub.yaml` → `--config` overrides.)*
- [x] Phase 2 – Draft reference documentation
  - [x] Create `.claude/skills/statement-processor/reference/fin-scrub-config-workflow.md` describing
    - [x] Workspace override flow (copy default -> edit -> run with `--config`)
    - [x] Commenting expectations for new rules
    - [x] Failure detection cues (subtle vs catastrophic) and when to escalate
    - [x] Promotion process for global config changes (surface diff for user approval)
- [x] Phase 3 – Update primary skill doc
  - [x] Insert succinct pointer in `SKILL.md` after fin-scrub step linking to the new reference doc
  - [x] Mention automatic escalation for catastrophic scrubbing errors and manual review for subtle mismatches
  - [x] Ensure new guidance aligns with existing skill workflow tone/style *(2025-10-28 – added blockquote guidance mirroring existing formatting.)*
- [x] Phase 4 – Validation & handoff
  - [x] Proofread both documents for clarity and consistency *(2025-10-28 – verified reference doc and SKILL excerpt read cleanly.)*
  - [x] Summarize updates for the user and highlight any follow-up actions *(2025-10-28 – communicated in handoff message.)*

### Notes
- No code changes anticipated; documentation only.
- Reference doc should be actionable for agents, including concrete shell snippets and rationale for staging edits.
