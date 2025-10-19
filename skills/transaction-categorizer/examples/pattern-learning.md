# Pattern Learning Examples

Goal: capture consistent merchant → category rules so imports auto-categorize.

Preview a pattern (no writes)
```bash
fin-edit --db ~/.finagent/data.db \
  add-merchant-pattern --pattern 'AMAZON%' \
  --category "Shopping" --subcategory "Online" --confidence 0.9
```

Apply the pattern
```bash
fin-edit --db ~/.finagent/data.db --apply \
  add-merchant-pattern --pattern 'AMAZON%' \
  --category "Shopping" --subcategory "Online" --confidence 0.9 \
  --display "Amazon"
```

Tips
- Prefer normalized/robust patterns (e.g., `AMZN%`, `AMAZON%`).
- Use confidence to reflect certainty; 0.9 is a good default for user-trained rules.
- Use `--create-if-missing` if the category does not exist and the user confirms its creation.

