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

Pipe mode for direct processing:
```bash
# Extract and enhance in one pipeline
fin-extract statement.pdf --stdout | fin-enhance --stdin

# Enhanced CSV output (updates DB and outputs enhanced CSV)
fin-enhance transactions.csv --stdout > enhanced.csv

# Inspect categorization results without files
fin-enhance transactions.csv --stdout | grep "Shopping"
```

### Advanced Examples

Process multiple PDFs in one pipeline:
```bash
for pdf in *.pdf; do
    fin-extract "$pdf" --stdout
done | fin-enhance --stdin --stdout > all_enhanced.csv
```

Filter transactions before import:
```bash
# Exclude pending transactions
fin-extract statement.pdf --stdout | grep -v "PENDING" | fin-enhance --stdin
```

Inspect data mid-pipeline:
```bash
# Use 'tee' to save intermediate data for debugging
fin-extract statement.pdf --stdout | tee extracted.csv | fin-enhance --stdin

# Save both extracted and enhanced versions
fin-extract statement.pdf --stdout | tee raw.csv | \
  fin-enhance --stdin --stdout | tee enhanced.csv > /dev/null
```

Audit categorization quality:
```bash
# Show low-confidence categorizations
fin-enhance transactions.csv --stdout | \
  awk -F, '$11 < 0.5 && $11 != "" {print $2, $9, $10, $11}'
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

`fin-extract` outputs eight columns (requires `--stdout` or `--output`):

```
date,merchant,amount,original_description,account_name,institution,account_type,account_key
```

- `account_name`, `institution`, and `account_type` describe the inferred
  account. These are required when importing via `fin-enhance`.
- `account_key` is a deterministic SHA-256 hash based on the three descriptive
  fields; it helps deduplicate statements before a numeric `account_id` exists.
- `fin-enhance` recomputes the key if the column is missing (for legacy CSVs).

`fin-enhance --stdout` adds four categorization columns:

```
date,merchant,amount,original_description,account_name,institution,account_type,account_key,category,subcategory,confidence,method
```

- `category` and `subcategory`: The assigned categories (empty if uncategorized)
- `confidence`: Categorization confidence score (0.0-1.0)
- `method`: How the category was determined (e.g., "rule:pattern", "llm:auto")

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

## Using `fin-analyze`

```bash
# Spending trends for August 2025 printed as Rich tables
fin-analyze spending-trends --month 2025-08

# Merchant frequency with JSON output suitable for automation
fin-analyze merchant-frequency --month 2025-08 --min-visits 2 --format json

# Category timeline for Shopping spend over the last 6 months with merchant drilldown
fin-analyze category-timeline --period 6m --category "Shopping" --include-merchants --format json

# Merchant frequency scoped to Shopping category only
fin-analyze merchant-frequency --month 2025-08 --category "Shopping"
```

## Using `fin-export`

`fin-export` turns the analyses above into shareable reports. Make sure your
SQLite database already contains enhanced transactions (via `fin-enhance`) so
the analyzers have data to summarize.

```bash
# Default Markdown report for a single month (written to stdout)
fin-export --month 2025-08

# Save Markdown to disk
fin-export --month 2025-08 --output ~/reports/august.md

# Emit machine-readable JSON (explicit flag)
fin-export --month 2025-08 --format json > august.json

# Emit JSON inferred from output extension
fin-export --month 2025-08 --output ~/reports/august.json

# Limit to specific sections in the final report
fin-export --month 2025-08 --sections summary,trends,unusual

# Use the trailing 3 months instead of a specific calendar month
fin-export --period 3m --sections all

# Skip comparison to the prior window and loosen change sensitivity
fin-export --month 2025-08 --no-compare --threshold 0.2

# Render with a custom Jinja2 template (Markdown only)
fin-export --month 2025-08 --template ~/my_templates/audit.md.j2
```

Section slugs currently available: `summary`, `categories`, `subscriptions`,
`patterns`, `unusual`, `merchants`, `trends`, `evolution`, and `all` (alias for
the full default set). JSON exports follow a stable `version: "1.0"` schema, so
web apps and agents can ingest `sections` directly without scraping Markdown.

## Using `fin-query`
The current saved query catalog includes:

- `recent_transactions` – most recent transactions, optional month filter.
- `category_summary` – total spend per category for a required month.
- `transactions_month` – denormalised transactions for a YYYY-MM window, matching `fin-analyze` time slices and supporting optional `account_id`/category filters.
- `uncategorized` – transactions without category assignments.
- `merchant_patterns` – learned merchant rules with confidence/usage metrics.
- `recent_imports` – most recent imports ordered by `import_date`.
- `categories` – category catalog with usage counts and approval flags.


`fin-query` provides read-only access to the SQLite database with support for
ad-hoc SQL, saved templates, and schema exploration.

```bash
# Run ad-hoc SQL (defaults to Rich table output)
fin-query sql "SELECT merchant, amount FROM transactions ORDER BY date DESC LIMIT 5;"

# Execute a saved query (parameters use KEY=VALUE syntax)
fin-query saved category_summary --param month=2025-08 --format json

# Inspect merchant pattern catalog with optional wildcard filter
fin-query saved merchant_patterns --param pattern=%AMAZON% --limit 20

# View the most recently imported transactions (ordered by import timestamp)
fin-query saved recent_imports --limit 15

# Review the category catalog with optional filters
fin-query saved categories --param category=%Dining% --format table

# List available saved queries and their parameters
fin-query list

# Inspect table metadata (tables, columns, indexes, foreign keys)
fin-query schema --table transactions --format table

# Point a single command at an alternate database path
fin-query saved recent_transactions --db /tmp/alt.db --limit 10
```

Output formats include `table` (Rich), `csv`, `tsv`, and `json`. Results are
limited to 200 rows by default; pass `--limit` on `sql` or `saved` to adjust.
You can supply `--db` either globally (`fin-query --db … saved …`) or per
command as shown above when you need to inspect another SQLite file.

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
