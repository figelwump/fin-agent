# Complete Analyzer Reference

spending-trends
- Overall spending over time
- Example: `fin-analyze spending-trends --month 2025-09 --compare --format json`

category-breakdown
- Total spending per category
- Example: `fin-analyze category-breakdown --period 3m --format json`

merchant-frequency
- Most frequently visited merchants
- Example: `fin-analyze merchant-frequency --month 2025-09 --format json`

category-timeline
- Category spend over time (month/quarter/year) with evolution summary (new/dormant/significant changes)
- Example: `fin-analyze category-timeline --period 6m --category "Food & Dining" --interval month --format json`

spending-patterns
- Analyze by day/week/date patterns
- Example: `fin-analyze spending-patterns --period 3m --by day --format json`

---

## Deprecated Analyzers

The following analyzers have been deprecated in favor of LLM-based analysis workflows:

~~subscription-detect~~ - Use $SKILL_ROOT/workflows/subscription-detection.md instead
~~unusual-spending~~ - Use $SKILL_ROOT/workflows/unusual-spending-detection.md instead
