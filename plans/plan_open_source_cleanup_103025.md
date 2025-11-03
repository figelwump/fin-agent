---
title: Open Source Readiness Cleanup
owner: codex
created: 2025-10-30
status: pending
---

# plan_open_source_cleanup_103025

## Phase 1 – Repository Hygiene & Sensitive Artifact Removal
- [x] Audit and delete debug helpers (e.g., `debug_docling.py`, stray test harnesses in `tmp/`, unused scripts in `output/`)
- [x] Remove committed/sample data containing real statements or PII (`statements/`, `output/`, `tmp/`, scrub temporary DBs)
- [x] Replace environment templates with a safe `.env.example` (no keys; documents `FINAGENT_DATABASE_PATH`)
- [x] Purge personal configs/secrets (`.env`, `.DS_Store`, stray `.venv*` folders) and ensure `.gitignore` covers them
- [x] Double-check for other large or unused resources (images, JSON dumps) and replace with README placeholders where helpful

Notes: Removed `debug_docling.py`, cleared `statements/`, `output/`, `tmp/` directories (now empty and ignored), deleted committed secrets, and reintroduced a sanitized `.env.example`.

## Phase 2 – Documentation Restructure (Repository Root)
- [x] Rewrite `README.md` around the skills-driven workflow (hero summary, skills catalog, quickstart, CSV formats)
- [x] Move legacy CLI coverage (`fin-extract`, `fin-enhance`, `fin-export`) into a deprecated section with migration notes
- [x] Expand documentation for active CLIs (`fin-scrub`, `fin-analyze`, `fin-edit`, `fin-query`) and highlight new usage patterns
- [x] Add explicit mention of the web agent/ccsdk near the end as non-primary workflow

Notes: README now leads with skills summary, refreshed quickstart, skill-usage examples, CLI reference updates (with format flags), and a deprecated commands section covering fin-extract/enhance/export. Web agent note moved near the end; CSV format details will shift to the fin-cli README in Phase 7.

## Phase 3 – Skills Documentation Refresh
- [x] Update `.claude/skills/README.md` with a full catalog summary, capability matrix, and modern usage notes
- [x] Revise each skill `SKILL.md` to remove `source .venv` prerequisites, describe productionized CLI entry points, and add examples
- [x] Document how skills interoperate (handoffs, expected inputs/outputs) and cross-link CSV schema references

Notes: Catalog README now highlights prerequisites, conventions, and a detailed skill-by-skill breakdown. All SKILL guides reference installed `fin-*` CLIs (no virtualenv activation), refreshed command snippets, and updated cross-skill guidance; related workflow docs were updated to match.

## Phase 4 – Agent Prompt Updates
- [x] Review `AGENTS.md` for outdated schema hints or CLI syntax; align with new skills workflow and CSV columns
- [x] Update `CLAUDE.md` to match the current agent orchestration flow and tool expectations
- [x] Remove legacy sections such as the “fin-enhance review process” and replace with skills-first guidance
- [x] Ensure both docs point to the refreshed README, skills catalog, and any new developer workflows

Notes: `AGENTS.md` (symlinked by `CLAUDE.md`) now documents the skills-first flow, references the skills directories, links to official agent skills docs, and adds safety reminders (fin-scrub before PDF ingestion, saved queries, category validation, fin-query/fin-edit best practices). Legacy fin-enhance review instructions removed.

## Phase 5 – Fin-CLI Productionization
- [x] Ensure the Python package can be installed/executed without an activated repo venv (pip/pipx workflows, PATH-safe entry points)
- [x] Normalize CLI invocations in skills/docs to use installed entry points or `python -m` fallbacks that work cross-platform
- [x] Update packaging metadata (versioning, license switch, classifiers) and prepare for PyPI distribution
- [x] Add automated smoke tests (or fixtures) that exercise `fin-scrub`, `fin-analyze`, `fin-edit`, `fin-query` via the installed CLI
- [x] Provide guidance for reproducible builds (lockfiles, dependency pins, optional Dockerfile if needed for CI)

Notes: Added MIT `LICENSE`, updated `pyproject.toml` metadata (version bump, classifiers), and documented pip/pipx workflows in README. Introduced CLI smoke tests (`tests/cli/test_entrypoints.py`) validating entry points with Click. Authored `docs/dev/release.md` covering lockfiles, build tooling, and publish steps; README now highlights pipx installs. Deprecated Docling support (removed extra dependency, CLI engine option, and loader) so pdfplumber + Camelot remain the maintained extraction path.

## Phase 6 – Web UI Simplification
- [x] Remove the Plaid-powered component from the web UI surface (retain underlying Plaid integration code for future opt-in use)
- [x] Write/update a `client/README.md` (or similar) describing the remaining web agent capabilities and local setup
- [x] Audit `ccsdk/` and `server/` for additional cleanup opportunities or unused endpoints
- [x] Confirm the UI still builds/tests after dependencies are trimmed (`bun test`, `bun run server/server.ts`)

Notes: Removed Plaid-specific React components/utilities, updated the chat interface to drop the connect button, and documented the trimmed web UI in `client/README.md`. Reviewed ccsdk/server code—Plaid helpers remain for future opt-in flows. Added README guidance clarifying that Plaid Link is not surfaced by default. Verified Bun tests succeed.

## Phase 7 – Developer Experience & Fin-CLI Guidance
- [x] Author `fin_cli/README.md` capturing package layout, local development workflow, testing strategy, and release steps
- [x] Document a consistent “fin-cli development workflow” (tooling, testing, linting) and surface it from the root docs
- [x] Review ancillary docs (`AGENTS.md`, `CLAUDE.md`, `docs/**`) to align terminology and remove conflicting guidance

Notes: Added `fin_cli/README.md` outlining package structure, testing, and release flow; root README now links to contributor docs and details pipx/pip upgrade paths. Existing docs already reflected skills-first terminology after Phase 4; cross-checked references to ensure consistency.

## Phase 8 – Verification & Release Prep
- [x] Run `pytest` and any targeted tests (`bun test`, relevant integration checks) after refactors
- [x] Validate packaging metadata (`pyproject.toml`) for open-source license, extras, and sdist/wheel contents
- [x] Final pass to ensure no references remain to removed tooling, debug scripts, or internal-only processes

Notes: Full `pytest` suite now passes with legacy extractor tests skipped when sample PDFs are absent; `bun test` still green. `pyproject.toml` reflects MIT license, trimmed extras, and active console scripts only. Root/skills docs audited to ensure removed tooling (Docling, Plaid UI, fin-enhance review flow) is either deprecated or omitted.

### Notes & Risks
- Removing large directories may require replacing them with minimal README placeholders so workflows remain discoverable.
- Need to scrub saved keys (OpenAI, Plaid) from history; confirm removal and advise user on secret rotation if ever exposed.
- Ensure documentation changes stay synchronized between root README and skills guides to avoid conflicting instructions.
