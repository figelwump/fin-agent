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
- [x] Relocate first-party YAML specs into the repo and register them as part of the built-in extractor set.
- [x] Add `plugin_loader.py` with utilities to scan user directories for `.py` and `.yaml` files.
- [x] Load Python plugins via importlib, register subclasses of `StatementExtractor`.
- [x] Load YAML specs, validate, wrap in `DeclarativeExtractor`, and register under spec name.
- [x] Prevent duplicate name collisions (built-in precedence unless override allowed).
- [x] Ensure loader surfaces structured diagnostics (success/failure, skipped files).

Notes (2025-10-15):
- Bundled specs now live under `fin_cli/fin_extract/bundled_specs/`; loader registers them as alternates while preserving Python extractors as primary. (`pyproject.toml` updated to ship YAML data.)
- New `fin_cli/fin_extract/plugin_loader.py` manages bundled/user discovery, returns structured `PluginLoadReport`, and respects registry precedence semantics (tests in `tests/fin_extract/test_plugin_loader.py`).

#### Phase 2 — Configuration & CLI Controls
- [x] Extend `ExtractionSettings` with `plugin_paths`, `enable_plugins`, and optional allowlist/denylist.
- [x] Add CLI switches (`--no-plugins`, `--allow-plugin <name>`) to override config per run.
- [x] Wire loader invocation into CLI bootstrap respecting config/CLI flags.
- [x] Update logging to show loaded plugin count and any warnings.

Notes (2025-10-15):
- `ExtractionSettings` now owns plugin knobs (`enable_plugins`, paths, allow/block lists) with env overrides (`FINCLI_EXTRACTION_*`). Config defaults point at `~/.finagent/extractors` and surface through new tests (`tests/shared/test_config.py`).
- `fin-extract` CLI accepts `--no-plugins` / `--allow-plugin` and loads user plugins once per run via `_initialize_plugins`, storing the report in `cli_ctx.state`. Loader respects allow/block policies and logs successes/failures (`fin_cli/fin_extract/main.py`).
- Plugin loader enforces configuration filters during discovery; new tests cover allowlist/denylist behavior (`tests/fin_extract/test_plugin_loader.py`).

#### Phase 3 — Developer UX & Validation
- [x] Add a `fin-extract dev:list-plugins` (or similar) command to list discovered plugins/specs.
- [x] Expose validation helper (`fin-extract dev:validate-spec <yaml>`) reusing existing runtime diagnostics.
- [x] Document plugin authoring workflow in README/docs (Python + YAML), including safety guidance.
- [x] Provide sample skeleton under `docs/examples/` for community extension.

Notes (2025-10-15):
- New developer commands live under `fin-extract dev`; `list-plugins` prints origin/kind metadata (built-in vs bundled vs user) and surfaces loader warnings, `validate-spec` loads YAML and warns about collisions/missing sections.
- Documentation added at `docs/plugin_workflow.md` with LLM-friendly steps plus example skeletons (`docs/examples/example_spec.yaml`, `docs/examples/example_extractor.py`). README now links to the guide for quick discovery.

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
