# fin-query Saved Queries Cheat Sheet

| Name | Description | Key Parameters |
| ---- | ----------- | -------------- |
| `recent_transactions` | Most recent transactions with category metadata. | `limit` (default 25), `month=YYYY-MM` |
| `category_summary` | Total spend per category for a specific month. | `month` *(required)*, `account_id` |
| `transactions_month` | Full transaction export for a month. | `month` *(required)*, `account_id`, `category`, `subcategory` |
| `uncategorized` | Transactions missing categories. | *(none)* |
| `merchant_patterns` | Learned merchant rules with usage stats. | `pattern`, `limit` |
| `merchant_search` | Transactions whose merchant matches a LIKE pattern (sorted oldest → newest). | `pattern` *(required)*, `limit` |
| `category_transactions` | Transactions filtered by category and optional subcategory. | `category`, `subcategory`, `limit` |
| `recent_imports` | Most recently imported batches. | `limit` |
| `categories` | Category catalog with usage counts and approval flags. | `limit`, `category`, `subcategory` |

Usage pattern:
```bash
fin-query saved <name> --param key=value --limit 25 --format csv
```

Tips
- Parameters are case-sensitive; wrap values containing spaces in quotes (e.g., `--param category="Food & Dining"`).
- Omit a parameter completely to accept the default (e.g., pass no `subcategory` to include all subcategories).
- Add `--db <path>` when the user specifies an alternate database file.
- Some saved queries expose a `limit` parameter; still pass the CLI-level `--limit <N>` so `fin-query` does not truncate at 200 rows. The CLI limit is safe even when the SQL also receives a `:limit` binding.
