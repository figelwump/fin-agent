# fin-agent

Finance agent powered by the `fin-cli` Python toolkit and a catalog of Claude agent skills. The repository bundles command-line utilities, skills documentation, and a light web surface so you can ingest statements, learn patterns, and answer questions about your personal ledger. Privacy-first approach to scrubbing sensitive data before sending anything to an LLM.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Skills Summary](#skills-summary)
- [Quickstart](#quickstart)
- [Complete Workflow Example](#complete-workflow-example)
- [Usage Examples](#usage-examples)
- [CLI Reference](#cli-reference)
- [Upgrading](#upgrading)
- [Troubleshooting](#troubleshooting)
- [Deprecated Commands](#deprecated-commands)
- [License](#license)

## Prerequisites

- **Python 3.10 or later** 
- **Claude Code** (for skills workflow) - [Install Claude Code](https://docs.claude.com/en/docs/claude-code)
- **Optional**: Homebrew (for macOS users installing pipx)

## Skills Summary

- **statement-processor** – Scrub bank/credit card PDF statements, build LLM prompts to extract transaction data, and import transactions into a local sqlite DB.
- **transaction-categorizer** – Bulk-categorize outstanding transactions using the agent's LLM, learn merchant patterns, and run guided manual review when needed.
- **spending-analyzer** – Run analytical reports (trend, subscription, merchant activity) and assemble summaries for users.
- **ledger-query** – Execute saved or ad-hoc SQL queries against the normalized ledger to answer targeted questions.

Each skill lives under `.claude/skills/<name>` with a `SKILL.md`, helper scripts, and references. Skills will be loaded by Claude Code. Multiple skills can be chained together (for example, importing a statement and categorizing uncategorized transactions). More details on how skills work: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview

## Quickstart

### 1. Install the CLI

Choose one of the following installation methods:

#### Option A: Global/isolated setup with pipx (recommended)

Install pipx (one time):
- **macOS with Homebrew**: `brew install pipx && pipx ensurepath`
- **Other systems**: `python3 -m pip install --user pipx && python3 -m pipx ensurepath`

Then install fin-cli from the repository:

```bash
cd /path/to/fin-agent
pipx install '.[all]'
```

Pipx creates a dedicated venv and exposes the executables (`fin-scrub`, `fin-query`, etc.) on your PATH without activating `.venv`.

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

To deactivate the venv:
```bash
deactivate
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

## Complete Workflow Example

Here's a typical end-to-end workflow:

**1. Install (one time)**

```bash
brew install pipx && pipx ensurepath
cd fin-agent && pipx install '.[all]'
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
- **Prompt**: `import ~/Downloads/chase-2025-09.pdf`
  - **Note**: Do not use Claude Code's "@" mention syntax. This will import the file natively and CC will not invoke the skill (and it may read the PDF statement which defeats the purpose of fin-scrub)
- **Workflow**: `fin-scrub` scrubs PII → transactions extracted from the scrubbed text using the LLM → enrich with cached merchant patterns
- If uncategorized transactions remain, then the `transaction-categorizer` skill will be invoked.
- **Result**: Transactions added to the ledger, new merchant patterns learned, and a confirmation summary returned to the user.
- Works for bulk imports too. Just let Claude Code know which directory (or which set of statements) you'd like to import and it will loop through them. Imports get more efficient over time because we cache known merchant patterns.

### Triage uncategorized spend

- **Skill**: transaction-categorizer
- **Prompt**: `Categorize any uncategorized transactions.`
- **Workflow**: Queries the local database for uncategorized transactions → attempts to categorize them automatically via the LLM (the prompt grounds the categorizations in the existing taxonomy)
- If any transactions could not be categorized with a high confidence, then the skill interactively asks the user for categorization confirmations
- **Result**: Category metadata added to all uncategorized transactions in the DB

### Monthly spending review

- **Skill**: spending-analyzer
- **Prompt**: `Give me a September 2025 spending report with category breakdown and subscriptions.`
- **Workflow**: Query the database to retrieve transactions over the given time period, and analyze them in various ways, including category breakdown, subscriptions detection, unusual spend detection, trends, etc.

### Answer ledger questions

- **Skill**: ledger-query
- **Prompt**: `How much did we spend at Costco in 2025?`
- **Workflow**: Uses `fin-query` where possible to retrieve the info to answer the user's question. Typically used for more adhoc questions rather than full analyses.

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
- `set-category` / `clear-category`: adjust individual transactions by id or fingerprint.
- `add-merchant-pattern` / `delete-merchant-pattern`: manage learned rules.
- `delete-transactions`: bulk delete (with preview) using fingerprints or IDs; confirm with `--apply` to perform the removal.
- Global flags from `common_cli_options` apply (`--db`, `--verbose`, `--dry-run`).

### `fin-query`

Read-only exploration with saved queries and safe SQL.
- `fin-query saved --list` to enumerate templates from `fin_cli/fin_query/queries/index.yaml`.
- `fin-query saved merchant_search --param pattern="%Costco%" --limit 20 --format csv`.
- `fin-query schema --table transactions --format table` to inspect structure.
- `fin-query sql "SELECT ..."` supports a single SELECT/WITH statement guarded by limits.
- Most commands emit tables by default; add `--format csv` for agent-friendly output or `--format json` where supported (`saved` queries and `schema`).

### `fin-analyze`

Analytical rollups on top of the SQLite ledger.
- Choose a window: `--month`, `--year`, `--period Nd|Nw|Nm`, or `--period all`.
- Add `--compare` for previous-period deltas, `--format json` for machine-readable output.
- Analyzers include `spending-trends`, `category-breakdown`, `category-timeline`, `merchant-frequency`, `subscription-detect`, `unusual-spending`, and more (run `fin-analyze --help-list`).
- Use `--threshold` to control highlight sensitivity and `--include-merchants` for drill-downs when supported.
- Text output is default; pass `--format csv` for tabular exports (analyzers that support tables) or `--format json` for structured payloads.

## Upgrading

### pipx installs

Rerun `pipx install --force '.[all]'` from the repository root; pipx rebuilds the isolated environment with latest code.

```bash
cd /path/to/fin-agent
pipx install --force '.[all]'
```

### Editable venv installs

Pull the latest branch; code changes take effect immediately (no reinstall needed).

```bash
git pull

# Activate venv to use the updated code
source .venv/bin/activate

# Verify you're using the venv version
which fin-scrub  # Should show .venv/bin/fin-scrub
```

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

## Web Agent & ccsdk

The repository still includes a lightweight web agent in `ccsdk/` and associated MCP tools. They’re useful for demonstrations of the Claude Agent SDK and a simple local UI, but the recommended flow remains the CLI + skills. The open-source web UI no longer surfaces Plaid Link; backend Plaid routes remain for teams who want to wire their own consented import experience.

## License

Source code is released under the standard MIT license.
