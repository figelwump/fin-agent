# Plan: Sequential Statement Processing & Categorizer Coordination

## Context
- Current batch import flow loads many statements at once, generating oversized LLM prompts, leading agents to fabricate helper scripts.
- Goal: enforce per-statement end-to-end processing, ensure categorizer learning happens immediately, and share a deterministic workspace between skills.

## Phase 1 – Discovery & Constraints
- [x] Create feature branch for this work (e.g., `git checkout -b feature/sequential-statement-flow`). (Created `feature/sequential-statement-flow`)
- [x] Review `.claude/skills/statement-processor` scripts (`bootstrap.sh`, `run_batch.sh`, preprocess/postprocess helpers) to locate batching logic entry points. (Noted batch flags in `preprocess.py` and automation in `run_batch.sh`.)
- [x] Audit `.claude/skills/statement-processor/SKILL.md` instructions for guidance that encourages bulk processing. (Identified “Batch Workflow” section promoting multi-statement processing.)
- [x] Examine `.claude/skills/transaction-categorizer` workflow (SKILL.md + scripts) to confirm how workspaces and learning are currently handled. (Confirmed separate bootstrap + LLM-first process; learning step manual via `fin-edit`.)
- [x] Trace existing environment variables (`FIN_*`) passed between skills during a typical run (use recent logs as reference). (Currently separate `FIN_STATEMENT_*` and `FIN_CATEGORIZER_*` namespaces; no shared slug.)

## Phase 2 – Statement Processor Updates
- [x] Remove dedicated batch-processing guidance (delete `.claude/skills/statement-processor/examples/batch-processing.md` and strip batch workflow sections from `SKILL.md`), replacing it with a single sequential per-statement loop for all scenarios. (Docs now describe per-statement loop; batch example removed.)
- [x] Decide fate of `scripts/run_batch.sh`: either retire it entirely or refactor into a sequential orchestrator; update docs accordingly. (Script removed; references cleaned.)
- [x] Introduce guardrails in helper scripts (or new controller) to iterate statements individually, invoking the full extract→enhance→import→categorize loop before moving on. (Preprocess CLI now rejects multiple inputs and build_prompt enforces single statement.)
- [x] Add failure-safe checks that halt the loop if categorization or learning steps fail, preventing cascading bulk imports. (Skill doc now mandates post-loop sanity checks and pause-on-failure.)

## Phase 3 – Categorizer Coordination
- [x] Extend bootstrap tooling to accept an explicit workspace slug so statement-processor and categorizer share the same directories. (Both `bootstrap.sh` scripts accept `--session` to reuse shared slugs.)
- [x] Ensure sequential loop exports/propagates the shared workspace env vars for every categorization call. (Updated Quick Start instructs storing `SESSION_SLUG` and bootstrapping both skills with it.)
- [x] Make the learning/apply step explicit (e.g., mandatory `fin-edit --apply ... --learn-patterns`) and verify success before continuing. (Docs now include post-import `fin-query` checks before proceeding.)

## Phase 4 – Validation & Documentation
- [ ] Dry-run the sequential loop on a subset of BOFA statements to confirm prompts stay small and learning occurs after each file.
- [ ] Run `pytest` (targeted modules touched, then full suite if time permits) to ensure regressions aren’t introduced.
- [ ] Update troubleshooting or README sections with new sequential workflow guidance and workspace reuse instructions.
- [ ] Capture follow-up questions or open decisions (e.g., thresholds for auto-batching) for future iterations.

## Notes
- Primary touchpoint files: `.claude/skills/statement-processor/SKILL.md`, `scripts/*.sh|py`, `.claude/skills/transaction-categorizer/SKILL.md`, `bootstrap.sh` helpers.
- Preserve deterministic naming by combining provider + account + session timestamp (e.g., `bofa-visa0653-20251022T2105`); document cleanup expectations.
- Batch artifacts (`run_batch.sh`, `examples/batch-processing.md`, `batch_extraction_prompt.txt`) removed to avoid regression into bulk workflows.
