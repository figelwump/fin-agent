## plan_skill_limit_update_103025

- [x] Phase 1 – Inventory current CLI usage guidance
  - [ ] Audit all skill documentation (`.claude/skills/**/SKILL.md`) for `fin-query` examples
  - [ ] Note commands lacking explicit `--limit` guidance and CSV usage for large outputs
  - [ ] Review `fin-analyze` usage for consistent CSV output guidance
  - [ ] Identify flows (e.g., subscription detection, unusual spend) that assume time ranges
- [x] Phase 2 – Update skill docs and workflows
  - [x] Revise every `fin-query` invocation to include `--limit N` and `--format csv`
  - [x] Update `fin-analyze` invocations to include `--format csv`
  - [x] Adjust sample commands to demonstrate the new flag usage
  - [x] Insert guidance to request explicit timeframes when users omit them for temporal analyses
  - [x] Add brief rationale comments if helpful for future agents
- [x] Phase 3 – Sanity check
  - [x] Re-read updated files for consistency and typos
  - [x] Summarize changes and open questions for the user

**Notes**
- Ensure guidance does not break scenarios where smaller interactive tables remain desirable; clarify when to keep defaults vs. when to opt into CSV.
- Keep tone aligned with existing skill documentation style; avoid altering unrelated instructions.
- Identified update targets (Phase 1): `.claude/skills/README.md`, `spending-analyzer/SKILL.md`, spending-analyzer workflows & examples, `ledger-query/SKILL.md` (+examples/reference), `statement-processor/SKILL.md`, `transaction-categorizer/SKILL.md` (+reference + scripts), and shared references mentioning `--format json`.
- `transaction-categorizer` prompt builder previously required JSON; extended it to auto-detect CSV/JSON so the workflow stays compatible with the new guidance.
