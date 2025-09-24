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

The package exposes the following commands (phases denote the primary
implementation milestones from the plan):

- `fin-extract` – PDF statement extractor (Phase 3) — **implemented**; parses
  statements locally and emits CSV with account metadata, never touching SQLite.
- `fin-enhance` – Transaction import and categorization (Phases 4-5) — consumes
  extractor CSVs, upserts accounts, and writes transactions into SQLite with
  optional LLM-assisted categorization.
- `fin-query` – Database exploration (Phase 7)
- `fin-analyze` – Analytical reports (Phase 8)
- `fin-export` – Markdown report generation (Phase 9)

Commands beyond `fin-extract`/`fin-enhance` remain stubs until their phases are
implemented.

## Pipe Mode: Composable Unix-style Processing

The tools support Unix-style piping for efficient, composable workflows:

### Basic Usage

Traditional file-based workflow:
```bash
# Extract to file, then enhance (fin-extract never touches the DB)
fin-extract statement.pdf --output transactions.csv
fin-enhance transactions.csv
```

New pipe mode for direct processing:
```bash
# Extract and enhance in one pipeline
fin-extract statement.pdf | fin-enhance --stdin
```

### Advanced Examples

Process multiple PDFs in one pipeline:
```bash
for pdf in *.pdf; do
    fin-extract "$pdf"
done | fin-enhance --stdin
```

Filter transactions before import:
```bash
# Exclude pending transactions
fin-extract statement.pdf | grep -v "PENDING" | fin-enhance --stdin
```

Inspect data mid-pipeline:
```bash
# Use 'tee' to save intermediate data for debugging
fin-extract statement.pdf | tee extracted.csv | fin-enhance --stdin
```

### Benefits of Pipe Mode

- **Memory efficient**: No intermediate file storage required
- **Faster processing**: Eliminates disk I/O for temporary files
- **Composable**: Works with standard Unix tools (grep, awk, sed, cut)
- **Agent-friendly**: Single command for extract+enhance operations

### Limitations

- Review JSON export (`--review-output`) is not available with stdin
- Pipeline breaks lose intermediate data (use `tee` for debugging)
- Only supports single CSV stream (cannot mix multiple CSVs via stdin)

### CSV Output & Metadata

`fin-extract` writes eight columns so downstream tools can recreate account
context without touching the database during extraction:

```
date,merchant,amount,original_description,account_name,institution,account_type,account_key
```

- `account_name`, `institution`, and `account_type` describe the inferred
  account. These are required when importing via `fin-enhance`.
- `account_key` is a deterministic SHA-256 hash based on the three descriptive
  fields; it helps deduplicate statements before a numeric `account_id` exists.
- `fin-enhance` recomputes the key if the column is missing (for legacy CSVs).

## Development Workflow

- Follow the phased checklist in `plans/fin_cli_implementation_plan.md`.
- Use the `dev` extras for linting (`ruff`, `black`), typing (`mypy`), and tests
  (`pytest`, `pytest-mock`). Tool configuration lives in `pyproject.toml`.
- Future phases will populate `tests/` with fixtures and integration coverage.

## Inspecting the SQLite database

Use the `sqlite3` CLI to inspect imported data. This keeps tooling lightweight
and makes it easy to share copy/pasteable commands.

```bash
sqlite3 ~/.findata/transactions.db   # open the shell
```

Once inside the prompt, helpful commands include:

- `.tables` – list available tables (e.g., `accounts`, `transactions`)
- `.schema transactions` – display the CREATE TABLE statement
- `SELECT COUNT(*) FROM transactions;` – confirm the number of imported rows
- `SELECT date, merchant, amount FROM transactions ORDER BY date DESC LIMIT 5;` –
  sample recent activity

Exit the shell with `.quit` when finished.

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
