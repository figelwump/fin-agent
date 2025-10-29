# Common Spending Queries

How much did I spend last month?
```bash
fin-analyze spending-trends --month 2025-09 --format json
```

Show my spending by category this month
```bash
fin-analyze category-breakdown --month 2025-10 --format json
```

Find all my subscriptions
See `$SKILL_ROOT/workflows/subscription-detection.md` for the LLM-based subscription detection workflow.

What restaurants did I visit most in September?
```bash
fin-analyze merchant-frequency --month 2025-09 --category "Food & Dining" --subcategory "Restaurants" --format json
```

Has my spending changed compared to last month?
```bash
fin-analyze category-breakdown --month 2025-10 --compare --format json
```

Show my dining spending over the last 6 months
```bash
fin-analyze category-timeline --period 6m --category "Food & Dining" --interval month --format json
```

Summarize all-time spending
```bash
fin-analyze category-breakdown --period all --format json
```
> Note: `--period all` cannot be combined with `--compare`.

Any unusual charges this month?
See `$SKILL_ROOT/workflows/unusual-spending-detection.md` for the LLM-based unusual spending detection workflow.
