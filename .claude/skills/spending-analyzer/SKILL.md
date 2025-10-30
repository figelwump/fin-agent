---
name: spending-analyzer
description: Analyze spending patterns, trends, and anomalies to generate insights and reports. Use when user asks how much they're spending, wants spending breakdowns/summaries, needs to find subscriptions, analyze trends over time, or investigate unusual charges. Provides insights and aggregated analysis, not raw transaction lists.
allowed-tools: Bash, Read
---

# Spending Analyzer Skill

Teach the agent how to run analyzers and assemble narrative reports.

## Configuration

**Resource root (do not `cd` here):** `$SKILL_ROOT` = `.claude/skills/spending-analyzer`

When executing commands or referencing paths, use `$SKILL_ROOT` only to build absolute paths to helper resources and keep the shell working directory at the repository root.

Environment
- `source .venv/bin/activate`

Guidelines
- Prefer `--format csv` with analyzers to keep transcripts compact.
- Always ask the user for the analysis window (month, quarter, custom dates). Do not assume or default to multi-year ranges without explicit direction.
- Use multiple analyzers for "report" requests and assemble results.
- To cover the full history, use `--period all` (do not combine with `--compare`).
- The `--compare` flag adds comparison data vs the previous period (e.g., if analyzing Sept 2025, compares to Aug 2025). Only works with specific time windows (month/quarter/year), not with `--period all`.

Report Assembly Patterns

**Subscription Detection**
Workflow: See $SKILL_ROOT/workflows/subscription-detection.md
Use case: LLM analyzes transaction patterns from merchant-frequency and transaction history to identify recurring charges and subscriptions.

**Unusual Spending Investigation**
Workflow: See $SKILL_ROOT/workflows/unusual-spending-detection.md
Use case: LLM compares spending patterns across time periods to identify anomalies, new merchants, and spending spikes.

**Category Deep-Dive**
Combine: category-breakdown, category-timeline (now includes evolution summaries), merchant-frequency (filtered)
Use case: Analyze spending in a specific category over time and note new/dormant subcategories.

Common Analyzers
```bash
fin-analyze spending-trends --month 2025-09 --format csv
fin-analyze category-breakdown --month 2025-09 --format csv
fin-analyze merchant-frequency --month 2025-09 --min-visits 2 --format csv
fin-analyze category-timeline --period 6m --category "Food & Dining" --format csv
fin-query saved transactions_range --param start_date=2025-06-01 --param end_date=2025-10-01 --param limit=50000 --limit 50000 --format csv
```

Common Errors
- **Invalid date format**: Use `YYYY-MM` for `--month` (e.g., `2025-09`) and periods like `3m`, `6m`, `12m`, or `all` for `--period`
- **No data for period**: Check if transactions exist in the specified time range with `fin-query saved transactions_month --param month=YYYY-MM --limit 500 --format csv`
- **Unknown analyzer**: Run `fin-analyze --help` to see available analyzers or check `$SKILL_ROOT/reference/all-analyzers.md`
- **Unknown category**: Verify category name with `fin-query saved categories --limit 200 --format csv`. Use exact spelling including ampersands (e.g., `"Food & Dining"`).
- **Cannot use --compare with --period all**: The `--compare` flag requires a specific time window (month, quarter, year), not the entire history
- **Empty or sparse transactions_range results**: If `fin-query saved transactions_range` returns empty/sparse data:
  1. Try expanding the date range (go back further, e.g., 2+ years)
  2. Check what data exists with `fin-query saved recent_imports --limit 25 --format csv` to see date ranges
  3. Use `fin-query saved transactions_month --param month=YYYY-MM --limit 500 --format csv` to verify which months have data
  4. If you need custom SQL queries, use `fin-query sql "SELECT ..."` instead of direct sqlite3 commands and include `--limit <N> --format csv`

Examples & Workflows
- $SKILL_ROOT/examples/custom-reports.md
- $SKILL_ROOT/examples/common-queries.md
- $SKILL_ROOT/workflows/subscription-detection.md
- $SKILL_ROOT/workflows/unusual-spending-detection.md

Reference
- $SKILL_ROOT/reference/all-analyzers.md
