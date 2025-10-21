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
- Use multiple analyzers for “report” requests and assemble results

Common Analyzers
```bash
fin-analyze spending-trends --month 2025-09 --format json
fin-analyze category-breakdown --month 2025-09 --format json
fin-analyze merchant-frequency --month 2025-09 --min-visits 2 --format json
fin-analyze subscription-detect --period 12m --format json
fin-analyze unusual-spending --month 2025-09 --sensitivity 3 --format json
fin-analyze category-timeline --period 6m --category "Food & Dining" --format json
```

Examples
- examples/custom-reports.md
- examples/common-queries.md
- examples/insights.md

Reference
- reference/all-analyzers.md

