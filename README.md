# fin-agent

Finance agent powered by the `fin-cli` Python toolkit and a catalog of Claude agent skills. The repository bundles command-line utilities, skills documentation, and a light web surface so you can ingest statements, learn patterns, and answer questions about your personal ledger. Privacy-first approach to scrubbing sensitive data before sending anything to an LLM.

## Skills Summary

- **statement-processor** – Scrub bank/credit card PDF statements, build LLM prompts to extract transaction data, and import transactions into a local sqlite DB.
- **transaction-categorizer** – Bulk-categorize outstanding transactions using the agent's LLM, learn merchant patterns, and run guided manual review when needed.
- **spending-analyzer** – Run analytical reports (trend, subscription, merchant activity) and assemble summaries for users.
- **ledger-query** – Execute saved or ad-hoc SQL queries against the normalized ledger to answer targeted questions.

Each skill lives under `.claude/skills/<name>` with a `SKILL.md`, helper scripts, and references. Skills will be loaded by Claude Code. Multiple skills can be chained together as well (for example, importing a statement and categorizing uncategorized transactions). More details on how skills work: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview

## Quickstart
1. **Install Python dependencies**
 ```bash
 python3.11 -m pip install --upgrade pip
 python3.11 -m pip install -e .[analysis,pii]
 ```
  Add `[llm]` if you plan to call hosted models from the CLI.
  Prefer an isolated environment manager (pipx, uv, rye, etc.) when installing globally:
  ```bash
  pipx install '.[analysis,pii]'
  ```

2. **Choose or create a working database**
   The default location is `~/.finagent/data.db`. You can override it with the `FINAGENT_DATABASE_PATH` environment variable (sample provided in `.env.example`) or the `--db` flag on any CLI.

3. **Load the skills where you need them**
   - Keep them in this repository and run Claude Code from this directory
   - Or copy the folders under `.claude/skills/` into your own project’s `.claude/skills/` directory (or `~/.claude/skills/` for global availability) to make them discoverable.

## How to Use fin-agent skills

Below are example prompts that will trigger these skills, the actions each skill performs, and the kind of responses to expect.

- **Process a new statement**
  - Skill: **statement-processor**
  - Prompt: “import `~/Downloads/chase-2025-09.pdf`"
      - Note: do not use Claude Code's "@" mention syntax. This will import the file natively and CC will not invoke the skill (and it may read the PDF statement which defeats the purpose of fin-scrub)
  - Workflow: `fin-scrub` scrubs PII -> transactions extracted from the scrubbed text using the LLM -> enrich with cached merchant patterns
  - If uncategorized transactions remain, then the `transaction-categorizer` skill will be invoked.
  - Result: Transactions added to the ledger, new merchant patterns learned, and a confirmation summary returned to the user.
  - Works for bulk imports too. Just let CC know which directory (or which set of statements) you'd like to import and it will loop through them. Imports get more efficient over time because we cache known merchant patterns. 

- **Triage uncategorized spend**
  - Skill: **transaction-categorizer**
  - Prompt: “Categorize any uncategorized transactions.”
  - Workflow: Queries the local database for uncategorized transactions -> attempts to categorize them automatically via the LLM (the prompt grounds the categorizations in the existing taxonomy)
  - If any transactions could not be categorized with a high confidence, then the skill interactively asks the user for categorization confirmations
  - Result: Category metadata added to all uncategorized transactions in the DB

- **Monthly spending review**
  - Skill: **spending-analyzer**
  - Prompt: “Give me a September 2025 spending report with category breakdown and subscriptions.”
  - Workflow: Query the database to retrieve transactions over the given time period, and analyze them in various ways, including category breakdown, subscriptions detection, unusual spend detection, trends, etc.

- **Answer ledger questions**
  - Skill: **ledger-query**
  - Prompt: “How much did we spend at Costco in 2025?”
  - Workflow: Uses `fin-query` where possible to retrieve the info to answer the user's question. Typically used for more adhoc questions rather than full analyses.

To integrate the skills into another repository:
- Copy each skill directory (and its `reference/` and `scripts/` subfolders) into the destination `.claude/skills/`.

See `.claude/skills/README.md` and the `SKILL.md` files for each skill in `.claude/skills` for deeper guidance, decision trees, and hand-off details between skills.

## CLI Reference
### `fin-scrub`
Redacts PII from statements before extraction. Key options:
- `--output / --output-dir / --stdout` to choose destinations.
- `--stdin` for piping input text.
- `--engine auto|docling|pdfplumber` to select the PDF parser.
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

## Deprecated Commands
The original extraction pipeline remains available but is no longer part of the primary skills flow:
- `fin-extract` – PDF extractor that emitted CSVs directly from PDF parsing.
- `fin-enhance` – Legacy importer/categorizer that relied on review JSON workflows.
- `fin-export` – Markdown/JSON report generator built on the legacy analyzer stack.

These commands continue to build/install for backwards compatibility, but future development focuses on the skills-first workflow above.

## Web Agent & ccsdk
The repository still includes a lightweight web agent in `ccsdk/` and associated MCP tools. They’re useful as an example of how to use the Claude Agent SDK and as a custom web interface to the data, but the main workflow now centers on the CLI + skills described above.

## License
Source code is released under the standard MIT license.
