# Common Ledger Queries

## First charge for a subscription
```bash
fin-query saved merchant_search --param pattern=%YouTube TV% --limit 20 --format json
```

Looks up all transactions where the merchant contains "YouTube TV" and returns them in
chronological order (earliest first). Adjust `--limit` if you need more history.

## Entertainment > Comedy spending recap
```bash
fin-query saved category_transactions \
  --param category=Entertainment \
  --param subcategory=Comedy \
  --limit 25 --format json
```

Returns recent transactions tagged as Entertainment > Comedy so you can see dates, amounts,
and account context.

## Quick ad-hoc SQL sample
```bash
fin-query sql "SELECT date, merchant, amount FROM transactions WHERE amount < -200 ORDER BY date DESC" --limit 10
```

Use SQL when no saved query fits. Stick to read-only `SELECT` statements.

## Schema inspection reminder
```bash
fin-query schema --table transactions --format table
```

Always confirm column names here before crafting custom SQL (e.g., the ledger uses
`original_description`, not `description`).
