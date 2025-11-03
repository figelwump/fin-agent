# fin-cli Build & Release Notes

The package ships as a standard Python project (PEP 517 via Hatchling). Use the steps below when preparing reproducible builds or publishing to PyPI.

## Local Environment
- Create a clean virtual environment or use an isolated tool like `pipx`, `uv`, or `rye`.
- Install the project with the development extras when iterating:
  ```bash
  python -m pip install -e .[dev]
  ```
- For an isolated install (no repository virtualenv), prefer pipx:
  ```bash
  pipx install 'fin-cli[analysis,pii]'
  ```

## Reproducible Dependency Locks
- Use `uv pip compile` (or `pip-compile` from pip-tools) to generate a fully pinned requirements set:
  ```bash
  uv pip compile pyproject.toml -o requirements.lock
  ```
- Commit lock files per environment when distributing to teammates/CI, and install with:
  ```bash
  uv pip sync requirements.lock
  ```
- For Node/Bun tooling, run `bun install --frozen-lockfile` to respect the checked-in `bun.lock`.

## Building Artifacts
- Ensure the tree is clean and tests pass: `pytest` (Python) and `bun test` (ccsdk).
- Build source and wheel distributions with Hatch:
  ```bash
  python -m build
  ```
  Artifacts land under `dist/`.
- Verify the metadata:
  ```bash
  twine check dist/*
  ```

## Publishing
- Upload to TestPyPI first:
  ```bash
  twine upload --repository testpypi dist/*
  ```
- Validate installation from TestPyPI in a fresh environment:
  ```bash
  pipx install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple fin-cli
  ```
- Promote to PyPI with `twine upload dist/*` once validation passes.

## Versioning
- Update `pyproject.toml` version before building. Follow semantic versioning (`MAJOR.MINOR.PATCH`).
- Tag releases in git (e.g., `git tag v0.1.0 && git push origin v0.1.0`).

These steps make it easy for contributors (and CI) to reproduce builds without depending on the repository’s virtualenv.
