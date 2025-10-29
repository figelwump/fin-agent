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

subscription-detect
- Heuristic recurring-charge detector (active/inactive); follow with $SKILL_ROOT/workflows/subscription-detection.md
- Example: `fin-analyze subscription-detect --period 12m --format json`

unusual-spending
- Heuristic anomaly detector; follow with $SKILL_ROOT/workflows/unusual-spending-detection.md
- Example: `fin-analyze unusual-spending --month 2025-09 --sensitivity 3 --format json`

spending-patterns
- Analyze by day/week/date patterns
- Example: `fin-analyze spending-patterns --period 3m --by day --format json`
