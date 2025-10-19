---
name: transaction-categorizer
description: Interactively categorize uncategorized transactions and learn merchant patterns.
---

# Transaction Categorizer Skill

Teach the agent how to interactively categorize transactions using conversation,
validate against the existing taxonomy, and record safe changes.

Environment
- `source .venv/bin/activate`

Principles
- Always load the existing taxonomy first to prevent bloat:
  - `fin-query saved categories --format json`
- Use `fin-edit` for writes (dry-run by default; add `--apply`).
- Prefer existing categories; only create new ones if the user insists.

Workflow
0) Load taxonomy (REQUIRED)
```bash
fin-query saved categories --format json
```

1) Find uncategorized
```bash
fin-query saved uncategorized --format json
```

2) Present to user
- Show date, merchant, amount, description
- Suggest categories from existing taxonomy and ask for confirmation

3) Update database (preferred: fin-edit)
```bash
# Preview (no writes)
fin-edit --db ~/.finagent/data.db \
  set-category --transaction-id <id> \
  --category "Food & Dining" --subcategory "Coffee" \
  --confidence 1.0 --method claude:interactive

# Apply after user confirms
fin-edit --db ~/.finagent/data.db --apply \
  set-category --transaction-id <id> \
  --category "Food & Dining" --subcategory "Coffee"
```

4) Learn the pattern (optional)
```bash
# Preview
fin-edit --db ~/.finagent/data.db \
  add-merchant-pattern --pattern 'STARBUCKS%' \
  --category "Food & Dining" --subcategory "Coffee" --confidence 0.95

# Apply when confirmed
fin-edit --db ~/.finagent/data.db --apply \
  add-merchant-pattern --pattern 'STARBUCKS%' \
  --category "Food & Dining" --subcategory "Coffee" --confidence 0.95
```

References
- examples/interactive-review.md
- examples/pattern-learning.md
- reference/common-categories.md

