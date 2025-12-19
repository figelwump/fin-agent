# fin-agent

Finance agent powered by the `fin-cli` Python toolkit and a catalog of Claude agent skills. The repository bundles command-line utilities, skills documentation, and a light web surface so you can ingest statements, learn patterns, and answer questions about your personal ledger. Privacy-first approach to scrubbing sensitive data before sending anything to an LLM.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Skills Summary](#skills-summary)
- [Codebase Structure](#codebase-structure)
- [Quickstart](#quickstart)
- [Complete Workflow Example](#complete-workflow-example)
- [Usage Examples](#usage-examples)
- [CLI Reference](#cli-reference)
- [Upgrading](#upgrading)
- [Contributor Docs](#contributor-docs)
- [Code Style](#code-style)
- [Troubleshooting](#troubleshooting)
- [Deprecated Commands](#deprecated-commands)
- [License](#license)

## Prerequisites

- **Python 3.10 or later** 
- **Claude Code** (for skills workflow)
- **Optional**: Homebrew (for macOS users installing pipx)

## Skills Summary

Some notes on Claude Skills I put together while working on this project: https://vishalkapur.com/posts/2025-11-06-notes-on-claude-skills

- **statement-processor** – Scrub bank/credit card PDF statements, build LLM prompts to extract transaction data, and import transactions into a local sqlite DB.
- **transaction-categorizer** – Bulk-categorize outstanding transactions using the agent's LLM, learn merchant patterns, and run guided manual review when needed.
- **spending-analyzer** – Run analytical reports (trend, subscription, merchant activity) and assemble summaries for users.
- **ledger-query** – Execute saved or ad-hoc SQL queries against the normalized ledger to answer targeted questions.
- **asset-tracker** – Extract holdings from investment/brokerage statements (UBS, Schwab, Fidelity, etc.) and import into the asset tracking database. Supports portfolio analysis, allocation breakdowns, rebalancing suggestions, and concentration risk reports.

Each skill lives under `.claude/skills/<name>` with a `SKILL.md`, helper scripts, and references. Skills will be loaded by Claude Code. Multiple skills can be chained together (for example, importing a statement and categorizing uncategorized transactions). More details on how skills work: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview

## Codebase Structure

```
fin-agent/
├── .claude/skills/          # Claude Agent Skills (statement-processor, transaction-categorizer, spending-analyzer, ledger-query, asset-tracker)
├── fin_cli/                 # Python CLI package (fin-scrub, fin-query, fin-edit, fin-analyze)
│   ├── fin_scrub/          # PII redaction for statements
│   ├── fin_query/          # Read-only ledger queries (transactions + assets)
│   ├── fin_edit/           # Write operations (imports, categorization, asset tracking)
│   └── fin_analyze/        # Analytical reports (spending + asset allocation)
├── web_client/              # Web UI for Claude Agent SDK
│   ├── client/             # React frontend
│   ├── server/             # Bun backend server
│   └── ccsdk/              # Claude Agent SDK integration
├── tests/                   # Test suite for fin_cli
├── plans/                   # Implementation plans and documentation
└── pyproject.toml          # Python package configuration
```

## Quickstart

### 1. Install the CLI

Choose one of the following installation methods:

#### Option A: Global/isolated setup with pipx or uv

Use this method if you just want to install the CLI commands globally and don't want to edit them.

**Using pipx:**

Install pipx (one time):
- **macOS with Homebrew**: `brew install pipx && pipx ensurepath`
- **Other systems**: `python3 -m pip install --user pipx && python3 -m pipx ensurepath`

Then install fin-cli from the repository:

```bash
cd /path/to/fin-agent
pipx install '.[all]'
```

Pipx creates a dedicated venv and exposes the executables (`fin-scrub`, `fin-query`, etc.) on your PATH without activating `.venv`.

**Using uv (faster alternative):**

```bash
# Install uv once (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

cd /path/to/fin-agent
uv tool install '.[all]'
```

Like pipx, `uv tool` creates an isolated environment and exposes CLI commands globally.

#### Option B: Local dev (editable install)

For active development work, use a local venv:

```bash
cd /path/to/fin-agent

# Create venv if it doesn't exist
python3 -m venv .venv

# Activate venv (macOS/Linux)
source .venv/bin/activate

# Install editable with dev dependencies
python3 -m pip install --upgrade pip
python3 -m pip install -e .[dev,all]
```

**Development workflow:**
- When `.venv` is **active**: Commands like `fin-scrub`, `fin-query` run from your working tree (editable install). Code changes take effect immediately.
- When `.venv` is **deactivated**: Commands fall back to the pipx-installed versions (if any).
- Skills automatically use whichever version is first in `PATH`.

#### Option C: Local dev with uv (fast dependency resolver)

If you use [uv](https://github.com/astral-sh/uv), you can let it manage the virtual environment and dependency installation:

```bash
# Install uv once (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

cd /path/to/fin-agent

# Create and activate the project venv
uv venv .venv
source .venv/bin/activate

# Install editable with dev extras using uv's pip shim
uv pip install -e '.[dev,all]'
```

### 2. Verify Installation

Confirm the CLI tools are available:

```bash
fin-scrub --help
fin-query --help
fin-analyze --help
fin-edit --help
```

**Check which version is running:**
```bash
which fin-scrub
# venv active: /path/to/fin-agent/.venv/bin/fin-scrub
# venv inactive (pipx): ~/.local/bin/fin-scrub (or similar)
```

### 3. Configure SQLite Database (optional)

The database is **automatically created** on first use.

- **Default path**: `~/.finagent/data.db`
- **Override via environment**: Set `FINAGENT_DATABASE_PATH` in your environment (see [`.env.example`](.env.example))
- **Override via CLI flag**: Use `--db /path/to/custom.db` on any command

### 4. Load Skills for Claude Code

To use the skills workflow:
- Work from this repository and run Claude Code here, or
- Copy `.claude/skills/<name>` directories into another project's `.claude/skills/` (or `~/.claude/skills/`) to reuse the workflows.

### 5. Run Web Client (optional)

The repository includes a lightweight web agent UI in `web_client/` built on the Claude Agent SDK (largely based on Anthropic's demo [email-agent](https://github.com/anthropics/claude-agent-sdk-demos/tree/main/email-agent)). The web UI provides an equivalent interface to the CLI workflow with the same skills.

#### Running the Web UI

```bash
cd web_client
bun install
bun run dev
```

Open `http://localhost:3000` to interact with the UI. The dev server proxies API calls to the Bun backend.

See `web_client/README.md` for more details on the web client architecture and code layout.

## Complete Workflow Example

Here's a typical end-to-end workflow:

**1. Install (one time)**

Using pipx:
```bash
brew install pipx && pipx ensurepath
cd fin-agent && pipx install '.[all]'
```

Or using uv (faster):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd fin-agent && uv tool install '.[all]'
```

**2. Open Claude Code in this directory**

The skills are automatically loaded from `.claude/skills/`

**3. Import a statement**

Say: `import ~/Downloads/chase-statement-2025-09.pdf`

The statement-processor skill will:
- Scrub PII from the PDF
- Extract transactions using LLM
- Enrich with known merchant patterns
- Import to the database
- Auto-categorize using the transaction-categorizer skill

**4. Review your spending**

Say: `Give me a September 2025 spending report with category breakdown and subscriptions`

The spending-analyzer skill provides detailed analysis.

**5. Ask specific questions**

Say: `How much did we spend at Costco in 2025?`

The ledger-query skill answers targeted questions.

## Usage Examples

Below are example prompts that will trigger these skills, the actions each skill performs, and the kind of responses to expect.

### Process a new statement

- **Skill**: statement-processor
- **Example prompt**: `import ~/Downloads/chase-2025-09.pdf` or `import all statements in ~/Downloads/bofa`
  - **Note**: Do NOT use Claude Code's "@" mention syntax to import statements. This will import the file natively and CC will not invoke the skill (and it may read the PDF statement which defeats the purpose of fin-scrub)
- **Workflow**: `fin-scrub` scrubs PII → transactions extracted from the scrubbed text using the LLM → enrich with cached merchant patterns
- If uncategorized transactions remain, then the `transaction-categorizer` skill will be invoked.
- **Result**: Transactions added to the ledger, new merchant patterns learned, and a confirmation summary returned to the user.
- Works for bulk imports too. Just let Claude Code know which directory (or which set of statements) you'd like to import and it will loop through them. Imports get more efficient over time because we cache known merchant patterns.

### Triage uncategorized spend

- **Skill**: transaction-categorizer
- **Example prompt**: `Categorize any uncategorized transactions.`
- **Workflow**: Queries the local database for uncategorized transactions → attempts to categorize them automatically via the LLM (the prompt grounds the categorizations in the existing taxonomy)
- If any transactions could not be categorized with a high confidence, then the skill interactively asks the user for categorization confirmations
- **Result**: Category metadata added to all uncategorized transactions in the DB

### Spending analysis

- **Skill**: spending-analyzer
- **Example prompt**: `Categorize my spending over the past 12 months` or `What subscriptions do I currently have?`
- **Workflow**: Query the database to retrieve transactions over the given time period, and analyze them in various ways, including category breakdown, subscriptions detection, unusual spend detection, trends, etc.

### Answer ledger questions

- **Skill**: ledger-query
- **Example prompt**: `How much did we spend at Costco in 2025?` or `What transactions are in the fitness category?`
- **Workflow**: Uses `fin-query` where possible to retrieve the info to answer the user's question. Typically used for more adhoc questions rather than full analyses.

### Track investment holdings

- **Skill**: asset-tracker
- **Example prompt**: `import my Schwab statement ~/Downloads/schwab-nov-2025.pdf` or `show my current portfolio allocation`
- **Workflow**: For imports, scrubs PII from the PDF → extracts holdings via LLM → validates JSON → imports instruments, holdings, and values into the database. For analysis, runs `fin-analyze` asset analyzers and `fin-query` asset queries.
- **Supported prompts**:
  - Import: `import ~/Downloads/ubs-statement.pdf`, `import all statements in ~/Downloads/schwab/`
  - Allocation: `show my asset allocation`, `what's my portfolio breakdown by asset class?`
  - Trends: `show portfolio value over the last 6 months`
  - Rebalancing: `suggest rebalancing for 60/30/10 target`
  - Cash runway: `analyze my cash position`, `how much cash do I have?`
  - Concentration: `show my top 10 holdings`, `what's my concentration risk?`
- **Result**: Holdings imported to the database with instruments, classifications, and valuations; analysis reports with allocation breakdowns, trends, and recommendations.

### Integrating Skills into Another Repository

Copy each skill directory (and its `reference/` and `scripts/` subfolders) into the destination `.claude/skills/`.

See `.claude/skills/README.md` and the `SKILL.md` files for each skill in `.claude/skills` for deeper guidance, decision trees, and hand-off details between skills.

## CLI Reference

### `fin-scrub`

Redacts PII from statements before extraction. Key options:
- `--output / --output-dir / --stdout` to choose destinations.
- `--stdin` for piping input text.
- `--engine auto|pdfplumber` to select the PDF parser (auto uses pdfplumber with Camelot fallback when enabled).
- `--config path/to/fin-scrub.yaml` to override detection rules.
- `--report` to emit redaction counts to stderr.

### `fin-edit`

Write operations for the ledger
- Dry run by default; use --apply to apply changes.
- `import-transactions <csv>`: preview/import enriched CSVs (add `--apply`, `--default-confidence`, `--learn-patterns`).
- `set-category` / `clear-category`: adjust individual transactions by id or fingerprint. `set-category` also accepts `--where "merchant LIKE '%Amazon%'"` to bulk recategorize after you've inspected the matching rows (dry-run preview first, then rerun with `--apply`).
- `add-merchant-pattern` / `delete-merchant-pattern`: manage learned rules.
- `delete-transactions`: bulk delete (with preview) using fingerprints or IDs; confirm with `--apply` to perform the removal.
- Global flags from `common_cli_options` apply (`--db`, `--verbose`, `--dry-run`).

**Asset tracking commands:**
- `accounts-create --name <name> --institution <inst> --type <type>`: create a new account for tracking holdings (types: brokerage, checking, credit, investment, retirement, savings).
- `asset-import --from <file.json>`: import a complete asset payload (instruments, holdings, holding_values) from normalized JSON.
- `instruments-upsert --from <file.json>`: upsert instrument records (securities) from JSON.
- `holdings-add`: create holdings linking accounts to instruments.
- `holdings-transfer --symbol <sym> --from <account> --to <account>`: transfer holdings between accounts (closes source, creates destination with optional cost basis carry).
- `holdings-deactivate --holding-id <id>`: mark a holding as closed.
- `holding-values-upsert --from <file.json>`: upsert valuation snapshots for holdings.
- `documents-register / documents-delete`: manage document hashes for idempotent imports.

### `fin-query`

Read-only exploration with saved queries and safe SQL.
- `fin-query saved --list` to enumerate templates from `fin_cli/fin_query/queries/index.yaml`.
- `fin-query saved merchant_search --param pattern="%Costco%" --limit 20 --format csv` (the first column is always `id`, making it easy to feed the results into `fin-edit set-category`).
- `fin-query schema --table transactions --format table` to inspect structure.
- `fin-query sql "SELECT ..."` supports a single SELECT/WITH statement guarded by limits.
- Most commands emit tables by default; add `--format csv` for agent-friendly output or `--format json` where supported (`saved` queries and `schema`).
- Typical prompts: "What is Amazon categorized as?" → should run `fin-query saved merchant_search --param pattern=%Amazon% --limit 50 --format csv` so you can review the existing categories before making changes.

**Asset tracking queries:**
- `fin-query unimported <directory>`: list PDF files not yet imported (compares SHA256 hashes against database). Use before bulk imports to avoid reprocessing.
- `fin-query saved portfolio_snapshot`: current holdings with values and classifications.
- `fin-query saved holding_latest_values`: latest valuation per holding (source priority + recency).
- `fin-query saved allocation_by_class`: allocation breakdown by main/sub asset class.
- `fin-query saved allocation_by_account`: allocation breakdown by account.
- `fin-query saved stale_holdings`: holdings without recent valuation updates.
- `fin-query saved instruments`: instrument catalog with classifications.
- `fin-query saved asset_classes`: asset class taxonomy catalog.

### `fin-analyze`

Analytical rollups on top of the SQLite ledger.
- Choose a window: `--month`, `--year`, `--period Nd|Nw|Nm`, or `--period all`.
- Add `--compare` for previous-period deltas, `--format json` for machine-readable output.
- Analyzers include `spending-trends`, `category-breakdown`, `category-timeline`, `merchant-frequency`, `subscription-detect`, `unusual-spending`, and more (run `fin-analyze --help-list`).
- Use `--threshold` to control highlight sensitivity and `--include-merchants` for drill-downs when supported.
- Text output is default; pass `--format csv` for tabular exports (analyzers that support tables) or `--format json` for structured payloads.

**Asset analyzers** (require `pandas` via `pip install '.[analysis]'`):
- `allocation-snapshot`: current allocation by asset class and account.
- `portfolio-trend --period 6m`: track portfolio value over time.
- `concentration-risk --top-n 10`: identify top holdings and concentration.
- `cash-mix`: analyze cash vs non-cash positions.
- `rebalance-suggestions --target equities=60 --target bonds=30`: compare current allocation to targets.

## Upgrading

### pipx or uv tool installs
- **pipx**: Reinstall from the repo: `pipx install --force '.[all]'`
- **pipx**: Upgrade from PyPI (once published): `pipx upgrade fin-cli` (add `--include-deps` if dependencies changed)
- **uv**: Reinstall from the repo: `uv tool install --force '.[all]'`
- **uv**: Upgrade from PyPI (once published): `uv tool upgrade fin-cli`

### Editable venv installs
- Pull the latest branch (`git pull`); editable installs pick up code changes instantly
- Activate the venv before testing: `source .venv/bin/activate`

### Standard pip installs
- Local repo: `pip install --upgrade .[all]`
- PyPI: `pip install --upgrade fin-cli`

## Contributor Docs
- `fin_cli/README.md` – package layout, test commands, and release checklist
- `docs/dev/release.md` – reproducible builds, TestPyPI validation, publishing steps
- `plans/plan_open_source_cleanup_103025.md` – current open-source roadmap and status

## Code Style

This project uses **black** for code formatting and **ruff** for linting to ensure consistent code style.

### Running Formatters and Linters

```bash
# Activate venv first
source .venv/bin/activate

# Format all code with black
black fin_cli tests

# Lint with ruff
ruff check fin_cli tests

# Auto-fix linting issues
ruff check --fix fin_cli tests

# Check a specific file
black fin_cli/fin_scrub/main.py
ruff check fin_cli/fin_scrub/main.py
```

### Pre-commit Hook

A pre-commit hook is configured in `.git/hooks/pre-commit` that automatically runs black and ruff before each commit. If issues are found:

- **black**: Auto-fixes formatting, then exits. Review changes and re-stage files.
- **ruff**: Reports linting errors. Run `ruff check --fix` to auto-fix where possible.

### Configuration

Code style settings are in `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F", "B", "I", "UP", "NPY", "G"]  # Enable specific rule sets
ignore = [
    "E501",  # Line too long (handled by black)
    "G004",  # Logging f-string
    "B904",  # raise-without-from-inside-except
]

[tool.black]
line-length = 100
target-version = ["py310"]
```

### CI/CD Integration

When setting up CI/CD, add these checks:

```bash
# In CI, use --check mode (don't auto-fix)
black --check fin_cli tests
ruff check fin_cli tests
```


## Testing

Run the full suite from the repo venv:

```bash
./.venv/bin/python -m pytest
```

Useful subsets during development:

```bash
# CLI regressions
./.venv/bin/python -m pytest tests/fin_query/test_cli.py tests/fin_edit/test_fin_edit.py

# Statement-processor pipeline smoke test
./.venv/bin/python -m pytest tests/statement_processor/test_pipeline_smoke.py
```

The pipeline smoke test fabricates scrubbed text and relies on the bundled skill scripts under `.claude/skills/statement-processor/`. Synthetic fixtures live in `tests/fixtures/`, including `scrubbed/sample_raw_statement.txt` for fin-scrub.


## Troubleshooting

### PEP 668 / externally-managed-environment error

**Problem**: On macOS with Homebrew Python, `pip install --user pipx` fails with:
```
error: externally-managed-environment
```

**Solution**: Use Homebrew to install pipx instead:
```bash
brew install pipx
pipx ensurepath
```

### Commands not found after installation

**Problem**: After installing with pipx, commands like `fin-scrub` are not found.

**Solution**:
1. Restart your terminal to pick up the updated PATH
2. Or manually run: `pipx ensurepath` and restart your terminal
3. Verify installation: `which fin-scrub`

### Code changes not taking effect

**Problem**: Modified CLI code but commands still run old behavior

**Solution**: Check which version is active:
```bash
which fin-scrub
```

- If it shows `.venv/bin/fin-scrub`: You're using the editable install. Code changes should work immediately.
- If it shows `~/.local/bin/fin-scrub` (or similar): You're using pipx. Either:
  1. Activate your venv: `source .venv/bin/activate`, or
  2. Reinstall pipx version: `pipx install --force '.[all]'`

**Tip**: When developing, keep `.venv` activated. When using skills in production, deactivate venv to use stable pipx version.

### Database permission errors

**Problem**: Permission denied when accessing `~/.finagent/data.db`

**Solution**: Check that the directory exists and has correct permissions:
```bash
mkdir -p ~/.finagent
chmod 755 ~/.finagent
```

### PDF parsing issues

**Problem**: Statement processing fails on certain PDFs

**Solution**:
- Check that the PDF is not password-protected or corrupted
- Configure custom scrubbing rules in `~/.finagent/fin-scrub.yaml` to handle PDFs with different layouts or formats
- See `fin_cli/fin_scrub/default_config.yaml` for configuration examples

### Skills not loading in Claude Code

**Problem**: Claude Code doesn't recognize the skills

**Solution**:
1. Ensure you're running Claude Code from the `fin-agent` repository root
2. Verify skills exist: `ls .claude/skills/`
3. Check that each skill has a `SKILL.md` file

### Import statement showing raw data

**Problem**: When importing a statement, Claude Code reads the raw PDF content

**Solution**:
- Do NOT use the "@" mention syntax when importing statements
- Instead, use a text prompt: `import ~/Downloads/statement.pdf`
- This ensures the statement-processor skill is invoked, which handles PII scrubbing

## Deprecated Commands

The original extraction pipeline remains available but is no longer part of the primary skills flow:
- `fin-extract` – PDF extractor that emitted CSVs directly from PDF parsing.
- `fin-enhance` – Legacy importer/categorizer that relied on review JSON workflows.
- `fin-export` – Markdown/JSON report generator built on the legacy analyzer stack.

Legacy commands remain in the source tree (invoke via `python -m fin_cli.fin_extract`, etc.) but no longer install as standalone executables; future development focuses on the skills-first workflow above.

## License

Source code is released under the standard MIT license.
