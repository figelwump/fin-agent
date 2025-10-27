# plan_transaction_categorizer_workspace_fix_102725

## Phase 1 – Reproduce & Map Current Workflow
- [x] Reproduce the reported `fin-query` redirection failure when `FIN_CATEGORIZER_QUERIES_DIR` is unset.
- [x] Inspect `.claude/skills/transaction-categorizer/scripts/bootstrap.sh` outputs and the workspace directories it creates.
- [x] Note how existing scripts (e.g., `build_prompt.py`) expect workspace paths or environment variables.

## Phase 2 – Simplify Categorizer Workspace Usage
- [x] Remove workspace persistence/helper artifacts introduced during initial fix attempt.
- [x] Update guidance to clarify transaction-categorizer bootstraps its own session slug (no dependency on statement-processor exports).
- [x] Document the recommended command pattern (e.g., chaining `eval "$()` bootstrap `"` with the immediate CLI) so env vars are in scope when needed.

## Phase 3 – Verification
- [ ] Rerun the problematic categorizer command using the simplified workflow to confirm output lands in the expected workspace.
- [ ] Run `pytest` (targeted scope is fine) to ensure no regressions.
- [ ] Record verification details and any follow-up notes in this plan file.

## Notes
- Workspace root: `~/.finagent/skills/transaction-categorizer`
- Virtualenv activation required for CLI interactions: `source .venv/bin/activate`
- Related scripts live under `.claude/skills/transaction-categorizer/scripts/`
- Reproduction: `fin-query saved uncategorized --format json > "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized.json"` emitted `read-only file system: /uncategorized.json` because `$FIN_CATEGORIZER_QUERIES_DIR` expanded to empty.
- Bootstrap snapshot: `mercury-2550-20251027-20251027-144655/{queries,prompts,llm}` created under the root; instructions in `SKILL.md` rely on those env vars being present across commands.
- Decision: drop cross-skill slug reuse; transaction-categorizer always bootstraps its own workspace per run using `--session`.
- Recommendation: chain `eval "$(.claude/skills/transaction-categorizer/scripts/bootstrap.sh --session '<slug>')"` with the next command in this harness so exports exist for that invocation.
