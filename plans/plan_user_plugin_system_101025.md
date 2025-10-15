## plan_user_plugin_system_101025

Goal: Implement Phase 4 of the fin-extract roadmap by bundling first-party extractor specs with the app, while loading user-provided plugins (Python + declarative specs) from `~/.finagent/extractors`, exposing CLI controls, and ensuring robust discovery, sandboxing, and testing support.

### Context Snapshot (2025-10-10)
- Current extractor registry is static; only built-in Chase/BofA/Mercury classes are registered (`fin_cli/fin_extract/extractors/__init__.py`).
- Declarative runtime + specs exist and live under `~/.finagent/extractors` but are manually passed via `--spec`.
- Config surface already includes `extraction.supported_banks` and engine controls; no plugin paths option yet.
- Goal of Phase 4 per master plan: auto-discover user plugins, allow opt-out (`--no-plugins`), provide allowlist, and ship developer tooling (validation command, docs).

### Architecture & Decisions (pending confirmation)
- Ship built-in declarative specs (Chase/BofA/Mercury) inside the repository (e.g., `fin_cli/fin_extract/bundled_specs/`) and register them alongside Python extractors.
- Plugin search roots: user directories (`~/.finagent/extractors` by default) plus optional project-local path (TBD).
- Discover `.py` extractors by importing with isolated module namespace; guard against side effects and duplicates.
- Discover `.yaml` specs and wrap with `DeclarativeExtractor` at load time; reuse schema validator.
- Provide config/CLI toggles: `extraction.plugin_paths`, `extraction.allow_plugins` boolean, CLI `--no-plugins`, `--allow <names>`.
- Error handling: log failures, skip faulty plugins, continue boot.

---

### plan_user_plugin_system_101025 Checklist

#### Phase 1 — Bundled Specs & Discovery Wiring
- [ ] Relocate first-party YAML specs into the repo and register them as part of the built-in extractor set.
- [ ] Add `plugin_loader.py` with utilities to scan user directories for `.py` and `.yaml` files.
- [ ] Load Python plugins via importlib, register subclasses of `StatementExtractor`.
- [ ] Load YAML specs, validate, wrap in `DeclarativeExtractor`, and register under spec name.
- [ ] Prevent duplicate name collisions (built-in precedence unless override allowed).
- [ ] Ensure loader surfaces structured diagnostics (success/failure, skipped files).

#### Phase 2 — Configuration & CLI Controls
- [ ] Extend `ExtractionSettings` with `plugin_paths`, `enable_plugins`, and optional allowlist/denylist.
- [ ] Add CLI switches (`--no-plugins`, `--allow-plugin <name>`) to override config per run.
- [ ] Wire loader invocation into CLI bootstrap respecting config/CLI flags.
- [ ] Update logging to show loaded plugin count and any warnings.

#### Phase 3 — Developer UX & Validation
- [ ] Add a `fin-extract dev:list-plugins` (or similar) command to list discovered plugins/specs.
- [ ] Expose validation helper (`fin-extract dev:validate-spec <yaml>`) reusing existing runtime diagnostics.
- [ ] Document plugin authoring workflow in README/docs (Python + YAML), including safety guidance.
- [ ] Provide sample skeleton under `docs/examples/` for community extension.

#### Phase 4 — Testing & Hardening
- [ ] Unit tests for loader (Python + YAML discovery, collision handling, error paths).
- [ ] Integration test: simulate plugin directory with both spec + Python extractors and ensure CLI picks them up.
- [ ] Regression test ensuring `--no-plugins` bypasses discovery.
- [ ] Performance sanity: loader should only scan configured dirs once per invocation.

### Notes & Follow-ups
- Revisit security posture: highlight in docs that user code runs locally; consider future sandboxing.
- Coordinate with upcoming “Learn This Bank” agent workflow to ensure generated specs land in the same directory and benefit from loader.
- Evaluate storing plugin metadata cache to speed repeated runs (optional stretch).

### Acceptance Criteria
- Plugins in `~/.finagent/extractors` (YAML or Python) are auto-registered without manual flags.
- CLI flags/config allow disabling or allowlisting plugins explicitly.
- `fin-extract` run logs indicate which plugins load or fail.
- Tests cover discovery, collision, opt-out, and spec validation helpers.
