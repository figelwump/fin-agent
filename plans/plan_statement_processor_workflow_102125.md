# plan_statement_processor_workflow_102125

## Phase 1 – Confirm Requirements & Current Behaviour
- [x] Audit existing statement-processor scripts (`bootstrap` gaps, preprocess/postprocess flags).
- [x] Identify touchpoints in documentation (`SKILL.md`, examples) that reference manual directory setup.
- [x] Note current default confidence threshold so prompts stay consistent.

## Phase 2 – Implementation
- [x] Add `.claude/skills/statement-processor/bootstrap.sh` to create deterministic working directories (shared by single/batch flows) and export helper environment variables.
- [x] Update `preprocess.py` to accept `--workdir` (auto-discover inputs/outputs) while preserving existing flags.
- [x] Update `postprocess.py` to accept `--workdir` and process all LLM CSVs into enriched outputs.
- [x] Enhance skill docs/templates/scripts to rely on bootstrap workflow (e.g., looped `fin-scrub`, instructions about shell cwd reset).
- [x] Add targeted inline comments where behaviour is non-obvious (e.g., auto-clearing categories).

## Phase 3 – Validation
- [x] Write or update unit tests for new CLI options/helpers.
- [x] Smoke-test bootstrap + preprocess + postprocess end-to-end in a temp workdir.
- [x] Update documentation (`SKILL.md`, examples) and verify links/commands render correctly.
- [x] Record results (tests run, manual checks) in this plan.

### Notes
- Bootstrap script should accept an optional label (e.g., `chase-2025-09`), defaulting to timestamp-only when omitted.
- `preprocess.py --workdir` should default input discovery to `<workdir>/scrubbed/*-scrubbed.txt` and write prompts to `<workdir>/prompts/`.
- `postprocess.py --workdir` should read `<workdir>/llm/*.csv` and write enriched files to `<workdir>/enriched/`.
- Documentation must remind agents that the CLI resets CWD, so commands rely on absolute paths or exported workdir variables.
- Default auto-approve confidence remains 0.80 per `AppConfig.categorization.confidence.auto_approve`; keep prompt guidance aligned.
- `bootstrap.sh` now prints export commands; docs instruct running via `eval "$({script})"` so environment persists between commands.
- `preprocess.py --workdir` gathers `scrubbed/*-scrubbed.txt` automatically and defaults output to `<workdir>/prompts/` via the existing `--output-dir` semantics.
- `postprocess.py --workdir` processes all `llm/*.csv` files and writes to `<workdir>/enriched/` in one invocation while retaining legacy CLI behaviour for single files.
- Unit tests added: `tests/statement_processor/test_preprocess.py::test_cli_workdir_discovers_inputs` and `tests/statement_processor/test_postprocess.py::test_cli_workdir_processes_all` cover the new options.
- Smoke test executed via temporary `FIN_STATEMENT_ROOT` to confirm bootstrap → preprocess → postprocess flow succeeds end-to-end.
