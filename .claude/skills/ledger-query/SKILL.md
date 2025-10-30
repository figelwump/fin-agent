---
name: ledger-query
description: List, search, and filter transaction records from the financial database. Use when user asks to show/list/find specific transactions by category, merchant, date, or wants to view transaction details. Does NOT analyze or summarize - just retrieves raw transaction data.
allowed-tools: Bash, Read, Grep
---

# Ledger Query Skill

Teach the agent how to answer direct data questions (e.g., "When did YouTube TV start?",
"Show Entertainment > Comedy transactions") using `fin-query`.

## Configuration

**Resource root (do not `cd` here):** `$SKILL_ROOT` = `.claude/skills/ledger-query`

When executing commands or referencing paths, use `$SKILL_ROOT` only to build absolute paths to helper resources and keep the shell working directory at the repository root.

Environment
- Activate the venv first: `source .venv/bin/activate`

Database Schema Overview
The financial database uses a normalized schema with foreign key relationships:

**transactions** table (main table):
- Stores: id, date, merchant, amount, original_description, fingerprint, metadata
- Foreign keys: `category_id` → categories.id, `account_id` → accounts.id
- ⚠️ Does NOT have category, subcategory, or account_name columns directly

**categories** table:
- Stores: id, category, subcategory
- To get category/subcategory names, you MUST JOIN transactions with categories

**accounts** table:
- Stores: id, name, institution, account_type, is_active
- To get account details, you MUST JOIN transactions with accounts

**Important**: When writing custom SQL, always JOIN with categories/accounts tables. Don't assume denormalized columns exist in transactions.

Guidelines
- Prefer saved queries (see reference) before dropping to `fin-query sql`.
- Include `--limit <N> --format csv` on every query to keep outputs compact; switch to `--format table` only for quick human eyeballing with very small result sets.
- Use `--db` only when the user explicitly points to an alternate database.
- Need schema details? Run `fin-query schema --table transactions --format table` (or `--all`).
- When writing custom SQL, remember the normalized schema - JOIN with categories/accounts tables as needed.

Decision Tree: Saved Query vs SQL
1. **Use saved query** when:
   - Looking up transactions by merchant name → `merchant_search`
   - Getting transactions for a category/subcategory → `category_transactions`
   - Finding uncategorized transactions → `uncategorized`
   - Viewing recent transactions → `recent_transactions`
   - Checking category taxonomy → `categories`
   - Reviewing merchant patterns → `merchant_patterns`
   - Summarizing spending by month → `category_summary` or `transactions_month`

2. **Use `fin-query sql`** when:
   - Query requires complex joins not covered by saved queries
   - Need custom aggregations or window functions
   - Combining multiple conditions not supported by saved query parameters
   - Debugging or exploring schema structure

3. **Always check** `$SKILL_ROOT/reference/saved-queries.md` first before writing custom SQL

Workflow
1. Clarify the time frame, category, or pattern the user cares about. If the user does not specify dates, ask before running queries.
2. Pick an existing saved query (reference doc lists them) or compose a `fin-query sql` query.
3. Run with `--limit <N> --format csv` so the agent can parse the output reliably.
4. Summarise findings back to the user, citing totals, dates, or counts.

Common Errors
- **"no such column: category" or "no such column: subcategory"**: The transactions table uses `category_id` (FK), not denormalized text. JOIN with categories table: `FROM transactions t JOIN categories c ON t.category_id = c.id`, then use `c.category` and `c.subcategory`
- **"no such column: account_name"**: The transactions table uses `account_id` (FK). JOIN with accounts: `FROM transactions t JOIN accounts a ON t.account_id = a.id`, then use `a.name`
- **Query returns no results**: Verify the time frame (e.g., `--param month=YYYY-MM`), check category spelling with `fin-query saved categories --limit 200 --format csv`, or try broadening the search (e.g., remove subcategory filter)
- **Unknown saved query**: Run `fin-query saved --list` to see available templates or check `$SKILL_ROOT/reference/saved-queries.md`
- **Invalid parameter name**: Consult `$SKILL_ROOT/reference/saved-queries.md` for the correct parameter names (e.g., `pattern` not `search`)
- **LIKE pattern not matching**: Remember SQL LIKE syntax requires `%` wildcards (e.g., `%YouTube%` not `YouTube`)
- **Database not found**: Verify `--db` path if using alternate database, otherwise check `~/.finagent/data.db` exists

SQL Examples for Custom Queries
When saved queries don't cover your needs, use these JOIN patterns:

```sql
-- Get transactions with category/subcategory names
SELECT t.date, t.merchant, t.amount, c.category, c.subcategory
FROM transactions t
JOIN categories c ON t.category_id = c.id
WHERE c.category = 'Shopping'
ORDER BY t.date DESC;

-- Get transactions with account details
SELECT t.date, t.merchant, t.amount, a.name as account, a.institution
FROM transactions t
JOIN accounts a ON t.account_id = a.id
WHERE a.institution = 'Chase'
ORDER BY t.date DESC;

-- Group by subcategory (common pattern)
SELECT c.subcategory, COUNT(*) as count, ROUND(SUM(t.amount), 2) as total
FROM transactions t
JOIN categories c ON t.category_id = c.id
WHERE c.category = 'Shopping'
GROUP BY c.subcategory
ORDER BY total DESC;
```

Reference
- `$SKILL_ROOT/examples/common-queries.md` – ready-to-run snippets for frequent questions.
- `$SKILL_ROOT/reference/saved-queries.md` – parameters for each saved template.
