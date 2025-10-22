# Interactive Review Workflow

0) Load taxonomy
```bash
fin-query saved categories --format json
```

1) Get uncategorized
```bash
fin-query saved uncategorized --format json
```

Presentation template (example)
```
I found 2 uncategorized transactions. Let's review:

Transaction 1:
- Date: Sept 15, 2025
- Merchant: AMZN MKTP US
- Amount: $45.67

Suggested: Shopping > Online
Use this category?
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

