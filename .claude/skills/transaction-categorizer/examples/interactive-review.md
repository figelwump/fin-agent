# Interactive Review Workflow

This workflow is used AFTER the LLM bulk categorization step, for transactions that:
- The LLM had low confidence on (<0.75)
- The LLM couldn't categorize at all

0) Load taxonomy and LLM suggestions
```bash
# Load taxonomy
fin-query saved categories --format json > "$FIN_CATEGORIZER_QUERIES_DIR/categories.json"

# Low-confidence LLM suggestions are already saved from the main workflow
# (in $FIN_CATEGORIZER_LLM_DIR/low-confidence.csv)
```

1) Get remaining uncategorized
```bash
fin-query saved uncategorized --format json > "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized-remaining.json"
```

Presentation template (example with LLM suggestion)
```
I found 2 uncategorized transactions. Let's review:

Transaction 1:
- Date: Sept 15, 2025
- Merchant: COFFEE BEAN #1234
- Amount: $8.50
- Description: COFFEE BEAN #1234 LOS ANGELES CA

Suggested: Food & Dining > Coffee (confidence: 0.85, from LLM)
Use this category? [y/n or provide alternative]
```

Presentation template (example without LLM suggestion)
```
Transaction 2:
- Date: Sept 16, 2025
- Merchant: UNKNOWN MERCHANT XYZ
- Amount: $125.00

No LLM suggestion available.
Available categories: Shopping > Online, Food & Dining > Restaurants, ...
Which category should I use?
```

If user approves, write safely
```bash
fin-edit --apply set-category --transaction-id <id> \
  --category "Shopping" --subcategory "Online" --method claude:interactive
```

Learn pattern when asked
```bash
fin-edit --apply add-merchant-pattern --pattern 'STARBUCKS%' \
  --category "Food & Dining" --subcategory "Coffee" --confidence 0.95
```

Done message
```
✓ Updated and recorded pattern. Future Starbucks charges will be categorized automatically.
```

