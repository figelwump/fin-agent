# plan_cli_entrypoints_110325

## Goal
- Remove deprecated standalone console entry points (`fin-extract`, `fin-enhance`, `fin-export`) from the default fin-cli install while keeping core CLIs (`fin-scrub`, `fin-edit`, `fin-query`, `fin-analyze`) untouched.
- Update docs/tests to reflect the new packaging behavior and document how to access legacy flows if ever needed.

## Context & Notes
- `pyproject.toml` currently defines all console scripts under `[project.scripts]`, so removing entries is sufficient to stop packaging stubs.
- Tests in `tests/cli/test_entrypoints.py` assert that each CLI exports `--help`; they will need to be updated to align with the slimmer command surface.
- README still mentions the deprecated commands under "Deprecated Commands"; clarify availability and potential manual invocation path (`python -m`).
- No schema or runtime changes expected—pure packaging + documentation update.

## Tasks
### Phase 1 – Packaging Cleanup
- [x] Update `pyproject.toml` to drop the deprecated console script entries and, if necessary, expose an alternative (e.g., note on `python -m` usage) without shipping new executables. *(pyproject now only publishes `fin-scrub`, `fin-edit`, `fin-query`, `fin-analyze`.)*

### Phase 2 – Tests & Documentation
- [x] Adjust `tests/cli/test_entrypoints.py` to reflect the reduced CLI list (remove legacy cases, ensure core CLIs still smoke test).
- [x] Refresh README (and any other references surfaced by search) to mention that legacy commands are no longer installed by default and provide guidance for power users. *(README now points to `python -m fin_cli.<module>` for legacy access.)*

### Phase 3 – Validation
- [x] Run `pytest` to confirm the test suite passes after the adjustments.
- [x] (Optional) Perform a local `pipx install --force '.[all]'` dry-run or equivalent check to verify only expected scripts are generated. *(Required one-time cleanup: pipx uninstall left stale symlinks; removed `~/.local/pipx/venvs/fin-cli` + old `fin-*` links, then fresh install showed only supported executables.)*
