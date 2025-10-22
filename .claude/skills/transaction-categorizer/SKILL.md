---
name: transaction-categorizer
description: Interactively categorize uncategorized transactions and learn merchant patterns.
---

# Transaction Categorizer Skill

Teach the agent how to interactively categorize transactions using conversation,
validate against the existing taxonomy, and record safe changes.

Environment
- `source .venv/bin/activate`

Database Path
- Omit `--db` to use the default location (`~/.finagent/data.db`)
- Only specify `--db <path>` when the user explicitly provides an alternate database

Principles
- Always load the existing taxonomy first to prevent bloat:
  - `fin-query saved categories --format json`
- Use `fin-edit` for writes (dry-run by default; add `--apply`).
- Prefer existing categories; only create new ones if the user insists.

Workflow (Interactive, 1-5 transactions)
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
fin-edit set-category --transaction-id <id> \
  --category "Food & Dining" --subcategory "Coffee" \
  --confidence 1.0 --method claude:interactive

# Apply after user confirms
fin-edit --apply set-category --transaction-id <id> \
  --category "Food & Dining" --subcategory "Coffee"
```

4) Learn the pattern (optional)
```bash
# Preview
fin-edit add-merchant-pattern --pattern 'STARBUCKS%' \
  --category "Food & Dining" --subcategory "Coffee" --confidence 0.95

# Apply when confirmed
fin-edit --apply add-merchant-pattern --pattern 'STARBUCKS%' \
  --category "Food & Dining" --subcategory "Coffee" --confidence 0.95
```

Bulk Categorization Workflow (10+ transactions)
When facing many uncategorized transactions:

1) **Group by merchant pattern**: Identify common merchants
```bash
# Find uncategorized and analyze merchant patterns
fin-query saved uncategorized --format json
```

2) **Prioritize high-frequency merchants**: Tackle merchants that appear most often first to maximize impact

3) **Batch by category**: Present transactions grouped by suggested category (e.g., "I found 12 Starbucks transactions - categorize as Food & Dining > Coffee?")

4) **Use pattern learning aggressively**: For each approved merchant, immediately add pattern so future transactions auto-categorize
```bash
fin-edit --apply add-merchant-pattern --pattern 'MERCHANT%' \
  --category "Category" --subcategory "Subcategory" --confidence 0.95
```

5) **Update in batches**: Process 5-10 transactions at a time, then show progress ("Categorized 45 of 120 remaining")

Common Errors
- **Unknown category**: Category doesn't exist in taxonomy. Check spelling with `fin-query saved categories` or create it if the user insists on a new category.
- **Transaction not found**: Verify the transaction ID is correct. Use `fin-query saved uncategorized` or `fin-query saved recent_transactions` to find the correct ID.
- **Category already set**: Transaction is already categorized. Use `fin-edit set-category` to update it (overwrites existing category).
- **Pattern already exists**: Merchant pattern is already learned. Use `fin-edit set-merchant-pattern` to update the existing pattern or choose a more specific pattern key.
- **Duplicate fingerprint**: Transaction may already exist in database from a previous import. Check with `fin-query saved recent_transactions`.

Validation After Categorization
After categorizing transactions, verify the changes:
```bash
# Verify the transaction was updated
fin-query saved recent_transactions --limit 5 --format table

# Check remaining uncategorized count
fin-query saved uncategorized --format json | jq 'length'

# Verify merchant pattern was learned (if applicable)
fin-query saved merchant_patterns --param pattern='PATTERN%' --limit 5
```

Cross-Skill Transitions
- **To explore similar transactions**: Use `ledger-query` skill with `merchant_search` or `category_transactions` saved queries to see historical patterns
- **After categorization is complete**: Use `spending-analyzer` skill to analyze spending patterns across the newly categorized transactions
- **For bulk imports needing categorization**: Consider using `statement-processor` skill's `--learn-patterns` flag during import to automatically learn high-confidence patterns

References
- examples/interactive-review.md
- examples/pattern-learning.md
- reference/common-categories.md

