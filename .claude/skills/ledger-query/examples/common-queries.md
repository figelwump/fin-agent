# Common Ledger Queries

## `recent_transactions` – latest activity snapshot
```bash
fin-query saved recent_transactions --param limit=15 --format json
```

Returns the most recent 15 transactions with category metadata; add `--param month=2025-09`
to restrict to a specific month.

## `category_summary` – spend totals for a month
```bash
fin-query saved category_summary --param month=2025-09 --format json
```

Produces total spend per category for the supplied month.

## `transactions_month` – full month extract
```bash
fin-query saved transactions_month --param month=2025-09 --limit 200 --format json
```

Emits denormalised transactions for the month. Add filters like
`--param category="Food%" --param subcategory=Restaurants` when needed.

## `uncategorized` – find items missing categories
```bash
fin-query saved uncategorized --limit 50 --format json
```

Lists uncategorized transactions so you can triage them.

## `merchant_patterns` – learned merchant rules
```bash
fin-query saved merchant_patterns --param pattern=%AMAZON% --limit 20 --format json
```

Examines pattern-based categorization rules and their usage counts.

## `merchant_search` – charges for a merchant pattern
```bash
fin-query saved merchant_search --param pattern=%YouTube TV% --limit 20 --format json
```

Fetches transactions whose merchant matches the provided SQL LIKE pattern (sorted oldest first).

## `category_transactions` – category/subcategory slice
```bash
fin-query saved category_transactions \
  --param category=Entertainment \
  --param subcategory=Comedy \
  --limit 25 --format json
```

Shows transactions tagged with the specified (sub)category.

## `recent_imports` – last imported files
```bash
fin-query saved recent_imports --limit 10 --format json
```

Each row shows an import batch with timestamp.

## `categories` – category catalog lookup
```bash
fin-query saved categories --param category=%Dining% --limit 50 --format json
```

Filters the category catalog using LIKE patterns for category/subcategory.

## Quick ad-hoc SQL sample
```bash
fin-query sql "SELECT date, merchant, amount FROM transactions WHERE amount < -200 ORDER BY date DESC" --limit 10
```

Use SQL when no saved query fits. Stick to read-only `SELECT` statements.

## Schema inspection reminder
```bash
fin-query schema --table transactions --format table
```

Confirm column names here before crafting custom SQL (e.g., the ledger uses
`original_description`, not `description`).
