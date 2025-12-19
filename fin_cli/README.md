# fin-cli Package Overview

> Internal notes for contributors. The user-facing quickstart lives in the repository root `README.md`. This document explains how the package is structured, how to run tests, and how to publish new releases.

## Layout

```
fin_cli/
├── fin_analyze/   # Analytical CLI (`fin-analyze`) - spending trends + asset allocation
│   └── analyzers/ # Individual analyzers (spending, assets)
├── fin_edit/      # Mutation CLI (`fin-edit`) - transactions + asset tracking
├── fin_query/     # Read-only SQL/MCP CLI (`fin-query`) - ledger + portfolio queries
│   └── queries/   # Saved SQL templates (transactions + assets)
├── fin_scrub/     # PDF/text scrubbing CLI (`fin-scrub`)
├── fin_extract/   # Legacy extractor (deprecated, invoked via python -m)
├── fin_enhance/   # Legacy importer (deprecated, invoked via python -m)
├── fin_export/    # Legacy report CLI (deprecated, invoked via python -m)
└── shared/        # Common helpers (config, logging, DB access, models)
```

Each CLI exposes a `main.py` with `click` commands. Only the active commands (`fin-scrub`, `fin-edit`, `fin-query`, `fin-analyze`) are published as console scripts; legacy flows remain accessible via `python -m fin_cli.<module>`.

## Asset Tracking Commands

The CLI supports investment/brokerage portfolio tracking alongside transaction management:

**fin-edit asset commands:**
- `accounts-create`: Create accounts for tracking holdings
- `asset-import --from <json>`: Import complete asset payloads (instruments + holdings + values)
- `instruments-upsert --from <json>`: Upsert securities/instruments
- `holdings-add`, `holdings-transfer`, `holdings-deactivate`: Manage holding lifecycle
- `holding-values-upsert --from <json>`: Import valuation snapshots
- `documents-register`, `documents-delete`: Manage document hashes for idempotent imports

**fin-query asset queries:**
- `unimported <directory>`: Find PDFs not yet imported
- `saved portfolio_snapshot`: Current holdings with valuations
- `saved allocation_by_class`, `saved allocation_by_account`: Allocation breakdowns
- `saved holding_latest_values`, `saved stale_holdings`: Valuation status

**fin-analyze asset analyzers:**
- `portfolio-trend`: Portfolio value over time
- `cash-mix`: Cash vs non-cash breakdown
- `rebalance-suggestions`: Compare allocation to targets

## Development Workflow

1. Create a virtualenv (optional when using `pipx` for runtime testing):
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   python -m pip install -e .[dev,all]
   ```
2. Run tests regularly:
   ```bash
   pytest
   bun test        # Node/Bun utilities
   ```
3. Run linting if needed:
  ```bash
  ruff check fin_cli
  ```
4. For quick smoke checks without the repo venv, install via pipx:
   ```bash
   pipx install '.[all]'
   fin-scrub --help
   ```

## Packaging & Release

Steps mirror `docs/dev/release.md`:

1. Ensure tests pass (`pytest`, `bun test`).
2. Bump the version in `pyproject.toml`; commit.
3. Build artifacts:
   ```bash
   python -m build
   twine check dist/*
   ```
4. Upload to TestPyPI (`twine upload --repository testpypi dist/*`) and validate with pipx.
5. Publish to PyPI (`twine upload dist/*`) when satisfied.
6. Tag the release: `git tag vX.Y.Z && git push origin vX.Y.Z`.

## Deprecated Modules

- `fin_extract`, `fin_enhance`, and `fin_export` remain for backwards compatibility but are not installed as standalone entry points. Update documentation by referencing `python -m fin_cli.fin_extract ...` when linking to these tools.
- Docling extraction was removed; pdfplumber (with Camelot fallback) is the supported engine.

Keep this document in sync with packaging changes, especially when adding/removing CLI scripts or extras in `pyproject.toml`.
