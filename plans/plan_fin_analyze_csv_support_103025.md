## plan_fin_analyze_csv_support_103025

- [x] Phase 1 – Requirements Review
  - [x] Inspect CLI failure and confirm docs/workflows referencing `--format csv`.
  - [x] Finalize CSV output contract covering summaries + multiple tables (note details below).

- [x] Phase 2 – Implementation
  - [x] Extend `--format` choice list to include `csv` and propagate to context.
  - [x] Add CSV rendering branch writing table sections + optional summary in `fin_cli/fin_analyze/render.py`.

- [x] Phase 3 – Tests
  - [x] Update render tests (single + multi-table) to cover csv output.
  - [x] Add CLI integration test verifying `merchant-frequency --format csv`.
  - [x] Run `pytest` in virtualenv (targeted or full) to confirm all pass.

- [x] Phase 4 – Docs & Wrap-up
  - [x] Update product spec / help text to include csv format.
  - [x] Record summary + verification steps in plan notes.

**Notes**
- CSV format finalized: start with `title,<title>` row, then `summary,<line>` rows (if any). Emit a blank separator before tables. For each table, output `table,<name>` marker, optional `metadata,<key>,<json-dumped value>` rows, then header row + data rows. Blank row separates tables. This structure stays friendly to future agents and simple parsers.
- Touch points: `fin_cli/fin_analyze/main.py`, `fin_cli/fin_analyze/render.py`, `tests/fin_analyze/test_render.py`, `tests/fin_analyze/test_cli.py`, `specs/spec_finagent_product_v0.1.md`.
- Tests: `pytest tests/fin_analyze/test_render.py tests/fin_analyze/test_cli.py` (pass, Python 3.13.2).
