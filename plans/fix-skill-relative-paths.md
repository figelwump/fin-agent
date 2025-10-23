# Fix Skill Relative Paths

## Problem

Skills documentation currently uses paths relative to the skill directory (e.g., `scripts/bootstrap.sh`), but Claude Code actually executes commands from the repository root. This means:

- Documentation suggests: `scripts/bootstrap.sh` (relative to skill dir)
- Actual working directory: `/Users/vishal/GiantThings/repos/fin-agent` (repo root)
- Required path: `.claude/skills/statement-processor/scripts/bootstrap.sh`

Reference: [Claude Code Skills Documentation](https://docs.claude.com/en/docs/claude-code/skills) suggests skill-relative paths should work, but current implementation doesn't support this.

## Scope

Update all 4 skills in `.claude/skills/`:
1. `statement-processor`
2. `transaction-categorizer`
3. `ledger-query`
4. `spending-analyzer`

## Path Patterns to Update

### Pattern: Script References
- **From**: `scripts/bootstrap.sh`
- **To**: `.claude/skills/<skill-name>/scripts/bootstrap.sh`

### Pattern: Python Scripts
- **From**: `python scripts/preprocess.py`
- **To**: `python .claude/skills/<skill-name>/scripts/preprocess.py`

### Pattern: Documentation References
- **From**: `examples/llm-extraction.md`
- **To**: `.claude/skills/<skill-name>/examples/llm-extraction.md`
- **From**: `reference/saved-queries.md`
- **To**: `.claude/skills/<skill-name>/reference/saved-queries.md`

## Phase 1: statement-processor ✅

**Paths to update:**
- [x] Line 18: `eval "$(scripts/bootstrap.sh --session \\"$SESSION_SLUG\\")"`
  - → `eval "$(.claude/skills/statement-processor/scripts/bootstrap.sh --session \\"$SESSION_SLUG\\")"`
- [x] Line 22: `python scripts/preprocess.py --workdir ...`
  - → `python .claude/skills/statement-processor/scripts/preprocess.py --workdir ...`
- [x] Line 24: `python scripts/postprocess.py --workdir ...`
  - → `python .claude/skills/statement-processor/scripts/postprocess.py --workdir ...`
- [x] Line 33: `python scripts/preprocess.py --input scrubbed.txt --emit-json`
  - → `python .claude/skills/statement-processor/scripts/preprocess.py --input scrubbed.txt --emit-json`
- [x] Line 38: `scripts/bootstrap.sh --session "$SESSION_SLUG"`
  - → `.claude/skills/statement-processor/scripts/bootstrap.sh --session "$SESSION_SLUG"`
- [x] Line 62: `scripts/bootstrap.sh` (in Available Commands)
  - → `.claude/skills/statement-processor/scripts/bootstrap.sh`
- [x] Line 64: `python scripts/preprocess.py` (in Available Commands)
  - → `python .claude/skills/statement-processor/scripts/preprocess.py`
- [x] Line 65: `python scripts/postprocess.py` (in Available Commands)
  - → `python .claude/skills/statement-processor/scripts/postprocess.py`
- [x] Line 76: `postprocess.py` (in Common Errors section)
  - → `.claude/skills/statement-processor/scripts/postprocess.py`
- [x] Line 81: `examples/llm-extraction.md`
  - → `.claude/skills/statement-processor/examples/llm-extraction.md`
- [x] Line 82: `reference/csv-format.md`
  - → `.claude/skills/statement-processor/reference/csv-format.md`
- [x] Line 104: `postprocess.py` (in Next Steps section)
  - → `.claude/skills/statement-processor/scripts/postprocess.py`

## Phase 2: transaction-categorizer ✅

**Paths to update:**
- [x] Line 23: `scripts/bootstrap.sh`
  - → `.claude/skills/transaction-categorizer/scripts/bootstrap.sh`
- [x] Line 46: `eval "$(scripts/bootstrap.sh)"`
  - → `eval "$(.claude/skills/transaction-categorizer/scripts/bootstrap.sh)"`
- [x] Line 63: `python scripts/build_prompt.py`
  - → `python .claude/skills/transaction-categorizer/scripts/build_prompt.py`
- [x] Line 191: `scripts/bootstrap.sh` in Available Commands
  - → `.claude/skills/transaction-categorizer/scripts/bootstrap.sh`
- [x] Line 192: `python scripts/build_prompt.py` in Available Commands
  - → `python .claude/skills/transaction-categorizer/scripts/build_prompt.py`
- [x] Line 244: `examples/interactive-review.md`
  - → `.claude/skills/transaction-categorizer/examples/interactive-review.md`
- [x] Line 245: `examples/pattern-learning.md`
  - → `.claude/skills/transaction-categorizer/examples/pattern-learning.md`
- [x] Line 246: `reference/common-categories.md`
  - → `.claude/skills/transaction-categorizer/reference/common-categories.md`

## Phase 3: ledger-query ✅

**Paths to update:**
- [x] Line 38, 48, 55: `reference/saved-queries.md`
  - → `.claude/skills/ledger-query/reference/saved-queries.md`
- [x] Line 54: `examples/common-queries.md`
  - → `.claude/skills/ledger-query/examples/common-queries.md`

## Phase 4: spending-analyzer ✅

**Paths to update:**
- [x] Line 56: `examples/custom-reports.md`
  - → `.claude/skills/spending-analyzer/examples/custom-reports.md`
- [x] Line 57: `examples/common-queries.md`
  - → `.claude/skills/spending-analyzer/examples/common-queries.md`
- [x] Line 58: `examples/insights.md`
  - → `.claude/skills/spending-analyzer/examples/insights.md`
- [x] Line 61: `reference/all-analyzers.md`
  - → `.claude/skills/spending-analyzer/reference/all-analyzers.md`

## Phase 5: Verification

For each skill, verify paths work by:
- [x] statement-processor: Run bootstrap script ✓ Works correctly
- [x] transaction-categorizer: Run bootstrap script ✓ Works correctly
- [x] ledger-query: Verify documentation references exist ✓ All files found
- [x] spending-analyzer: Verify documentation references exist ✓ All files found

## Completion Summary

**Status**: ✅ Complete

All 4 skills have been successfully updated with repo-relative paths:
1. ✅ statement-processor - 12 path references updated
2. ✅ transaction-categorizer - 8 path references updated
3. ✅ ledger-query - 4 path references updated
4. ✅ spending-analyzer - 4 path references updated

**Verification Results**:
- Bootstrap scripts execute correctly from repo root
- All documentation file paths are valid and accessible
- Pattern: All paths now use `.claude/skills/<skill-name>/...` format

## Technical Notes

- All bash commands execute from repo root: `/Users/vishal/GiantThings/repos/fin-agent`
- The skill SKILL.md files acknowledge this with: "The harness resets the shell's CWD between commands"
- Environment variables (e.g., `$FIN_STATEMENT_WORKDIR`) are still used correctly and don't need updating
- Only file path references in the skill documentation need updates

## Related Issue

This discrepancy between documented behavior (skill-relative paths) and actual behavior (repo-relative paths) should be reported to Claude Code maintainers.
