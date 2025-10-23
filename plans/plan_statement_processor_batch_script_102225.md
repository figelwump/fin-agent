# plan_statement_processor_batch_script_102225

**Created:** 2025-10-22  
**Status:** In Progress  
**Goal:** Provide a deterministic helper script that automates batch scrubbing and prompt preparation (workflow steps 1 & 2) for the statement-processor skill, leaving LLM execution, post-processing, and imports manual.

---

## Overview & Notes
- Helper scripts live alongside the statement-processor skill under `scripts/`.
- Keep behaviour deterministic/reproducible; prefer explicit arguments over implicit globbing when possible.
- Preserve manual checkpoints: user still reviews LLM CSV output before import; script can stage files and emit instructions.
- Ensure compatibility with existing prompt chunking logic (`preprocess.py --batch` emits multiple prompts when needed).
- Handle filesystem layout under `~/.finagent/skills/statement-processor/<timestamp>/` for logs/artifacts.
- Reuse virtualenv activation guidance; script expects the user to source `.venv` beforehand rather than activating automatically.

---

## Phase 1 — Requirements & Design
- [x] Confirm script scope (scrub PDFs and invoke `preprocess.py --batch`; no downstream automation). *(2025-10-22 — helper covers workflow steps 1–2 only.)*
- [x] Define CLI interface (inputs, output directory/working directory, optional glob vs explicit PDF list). *(2025-10-22 — script accepts PDF args, optional `--workdir`, knobs for merchant limits/chunk size.)*
- [x] Decide defaults for merchant/category limits and chunk size; allow overrides. *(2025-10-22 — defaults: max merchants 150, chunk size 3, min merchant count 1.)*
- [x] Specify logging/output format so the agent knows where prompt files land, leveraging preprocess.py default naming via `--output-dir`. *(2025-10-22 — script surfaces workspace path and prompt file list; relies on preprocess default naming.)*
- [x] Determine policy for cleaning pre-existing `*-scrubbed.txt` (e.g., delete or archive within working directory before new run). *(2025-10-22 — default cleans scrubbed files; `--no-clean` preserves.)*

## Phase 2 — Implementation
- [x] Scaffold batch helper (`run_batch.sh`) with usage/help output. *(2025-10-22)*
- [x] Implement scrub loop (honours include/exclude patterns; removes stale `*-scrubbed.txt` in workdir, then writes fresh files). *(2025-10-22 — loop runs fin-scrub per PDF, cleans existing files by default.)*
- [x] Invoke `preprocess.py --batch` with configured limits and `--output-dir` so prompt filenames follow default naming. *(2025-10-22 — passes `--output-dir $WORKDIR` with configurable knobs.)*
- [x] Emit clear next-step instructions indicating where prompt chunks are located. *(2025-10-22 — script prints workspace summary and follow-up checklist.)*
- [x] Consolidate helper scripts under `scripts/` and update references. *(2025-10-22 — relocated bootstrap/preprocess/postprocess/run_batch + doc updates.)*

## Phase 3 — Documentation & Validation
- [x] Update `.claude/skills/statement-processor/SKILL.md` batch workflow to reference the script for steps 1–2. *(2025-10-22)*
- [x] Provide example session/log showing script output in docs or `examples/batch-processing.md`. *(2025-10-22 — added helper run example to examples/batch-processing.md.)*
- [x] Smoke-test script on sample statements (fixtures) and confirm prompt files are generated correctly. *(2025-10-22 — ran against mercury statements; prompts now emitted under workspace with corrected template resolution.)*
- [x] Add notes to plan on any follow-up tasks or limitations discovered. *(2025-10-22 — mapfile fallback added for macOS Bash 3.2; preprocess now auto-detects templates outside scripts dir.)*

---

## Open Questions
- Default workspace auto-derives to `~/.finagent/skills/statement-processor/<timestamp>` but remains overrideable via `--workdir`.
- Do we need macOS/Linux portability considerations (e.g., `bash` vs `sh`)?
