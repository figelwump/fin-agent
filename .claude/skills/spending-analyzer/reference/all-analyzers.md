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
- Category spend over time (month/quarter/year)
- Example: `fin-analyze category-timeline --period 6m --category "Food & Dining" --interval month --format json`

subscription-detect
- Identify recurring charges (active/inactive)
- Example: `fin-analyze subscription-detect --period 12m --all --format json`

unusual-spending
- Detect anomalies
- Example: `fin-analyze unusual-spending --month 2025-09 --sensitivity 3 --format json`

spending-patterns
- Analyze by day/week/date patterns
- Example: `fin-analyze spending-patterns --period 3m --by day --format json`

category-suggestions
- Suggest category consolidations
- Example: `fin-analyze category-suggestions --period 6m --format json`

category-evolution
- Track category usage changes
- Example: `fin-analyze category-evolution --period 12m --compare --format json`

