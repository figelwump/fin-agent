# Financial CLI Tools Suite

This repository hosts the `fin-cli` Python package that powers the local-first
financial tooling described in the product and implementation specifications.
Work is organized around the multi-phase implementation plan in
`plans/fin_cli_implementation_plan.md`.

## Getting Started

1. **Python environment**
   - Install Python 3.11 or newer.
   - Create and activate a virtual environment:
     ```bash
     python3.11 -m venv .venv
     source .venv/bin/activate
     ```
2. **Install dependencies**
   - Core tooling:
     ```bash
     pip install -e .
     ```
   - Full feature set (PDF parsing, LLM, analysis, and developer tooling):
     ```bash
     pip install -e .[pdf,llm,analysis,dev]
     ```
3. **Environment configuration**
   - PDF extraction and categorization are local-first by design.
   - When enabling LLM features in later phases, export the relevant API key
     (default: `OPENAI_API_KEY`).
   - Global configuration defaults to `~/.finconfig/config.yaml`; this file will
     be generated or edited by upcoming implementation phases.

## Available CLI Entry Points

The package exposes stubbed commands to preserve CLI contracts while
implementation progresses:

- `fin-extract` – PDF statement ingestion (Phase 3)
- `fin-enhance` – Transaction import and categorization (Phases 4-5)
- `fin-query` – Database exploration (Phase 7)
- `fin-analyze` – Analytical reports (Phase 8)
- `fin-export` – Markdown report generation (Phase 9)

Each command currently raises a friendly `ClickException` until the relevant
phase is complete.

## Development Workflow

- Follow the phased checklist in `plans/fin_cli_implementation_plan.md`.
- Use the `dev` extras for linting (`ruff`, `black`), typing (`mypy`), and tests
  (`pytest`, `pytest-mock`). Tool configuration lives in `pyproject.toml`.
- Future phases will populate `tests/` with fixtures and integration coverage.

## Repository Structure

```
fin_cli/
  fin_extract/      # Phase 3 implementation target
  fin_enhance/      # Phases 4-5 implementation target
  fin_query/        # Phase 7 implementation target
  fin_analyze/      # Phase 8 implementation target
  fin_export/       # Phase 9 implementation target
  shared/           # Shared infrastructure (Phases 1-2 foundation)
plans/              # Active implementation plan(s)
specs/              # Product & implementation specifications
```

Refer to `AGENTS.md` for collaboration ground rules and plan updates while the
project evolves.
