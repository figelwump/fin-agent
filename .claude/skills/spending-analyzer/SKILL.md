---
name: spending-analyzer
description: Analyze spending patterns and assemble custom reports using fin-analyze.
---

# Spending Analyzer Skill

Teach the agent how to run analyzers and assemble narrative reports.

Environment
- `source .venv/bin/activate`

Guidelines
- Prefer `--format json` for parsing analyzer output
- Use multiple analyzers for "report" requests and assemble results
- To cover the full history, use `--period all` (do not combine with `--compare`)
- The `--compare` flag adds comparison data vs the previous period (e.g., if analyzing Sept 2025, compares to Aug 2025). Only works with specific time windows (month/quarter/year), not with `--period all`.

Report Assembly Patterns

**Monthly Summary Report**
Combine: spending-trends, category-breakdown, merchant-frequency, unusual-spending, subscription-detect
Use case: Regular monthly review of spending habits

**Category Deep-Dive**
Combine: category-breakdown, category-timeline, merchant-frequency (filtered)
Use case: Analyze spending in a specific category over time

**Subscription Audit**
Combine: subscription-detect, merchant-frequency
Use case: Review all recurring charges and identify cancellation opportunities

**Spending Anomaly Investigation**
Combine: unusual-spending, category-breakdown, merchant-frequency
Use case: Understand spikes or unusual patterns in spending

Common Analyzers
```bash
fin-analyze spending-trends --month 2025-09 --format json
fin-analyze category-breakdown --month 2025-09 --format json
fin-analyze merchant-frequency --month 2025-09 --min-visits 2 --format json
fin-analyze subscription-detect --period 12m --format json
fin-analyze unusual-spending --month 2025-09 --sensitivity 3 --format json
fin-analyze category-timeline --period 6m --category "Food & Dining" --format json
```

Common Errors
- **Invalid date format**: Use `YYYY-MM` for `--month` (e.g., `2025-09`) and periods like `3m`, `6m`, `12m`, or `all` for `--period`
- **No data for period**: Check if transactions exist in the specified time range with `fin-query saved transactions_month --param month=YYYY-MM`
- **Unknown analyzer**: Run `fin-analyze --help` to see available analyzers or check `reference/all-analyzers.md`
- **Unknown category**: Verify category name with `fin-query saved categories`. Use exact spelling including ampersands (e.g., `"Food & Dining"`).
- **Cannot use --compare with --period all**: The `--compare` flag requires a specific time window (month, quarter, year), not the entire history

Examples
- examples/custom-reports.md
- examples/common-queries.md
- examples/insights.md

Reference
- reference/all-analyzers.md
