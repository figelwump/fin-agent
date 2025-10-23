---
name: ledger-query
description: Query the financial ledger with fin-query saved templates and ad-hoc SQL.
allowed-tools: Bash, Read, Grep
---

# Ledger Query Skill

Teach the agent how to answer direct data questions (e.g., "When did YouTube TV start?",
"Show Entertainment > Comedy transactions") using `fin-query`.

Environment
- Activate the venv first: `source .venv/bin/activate`

Guidelines
- Prefer saved queries (see reference) before dropping to `fin-query sql`.
- Request JSON output when the result will be parsed: add `--format json`.
- Always cap result size (e.g., `--limit 25`) to keep responses concise.
- Use `--db` only when the user explicitly points to an alternate database.
- Need schema details? Run `fin-query schema --table transactions --format table` (or `--all`).

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

3. **Always check** `.claude/skills/ledger-query/reference/saved-queries.md` first before writing custom SQL

Workflow
1. Clarify the time frame, category, or pattern the user cares about.
2. Pick an existing saved query (reference doc lists them) or compose a `fin-query sql` query.
3. Run with `--format json` when structured parsing is needed; otherwise table output is fine.
4. Summarise findings back to the user, citing totals, dates, or counts.

Common Errors
- **Query returns no results**: Verify the time frame (e.g., `--param month=YYYY-MM`), check category spelling with `fin-query saved categories`, or try broadening the search (e.g., remove subcategory filter)
- **Unknown saved query**: Run `fin-query saved --list` to see available templates or check `.claude/skills/ledger-query/reference/saved-queries.md`
- **Invalid parameter name**: Consult `.claude/skills/ledger-query/reference/saved-queries.md` for the correct parameter names (e.g., `pattern` not `search`)
- **LIKE pattern not matching**: Remember SQL LIKE syntax requires `%` wildcards (e.g., `%YouTube%` not `YouTube`)
- **Database not found**: Verify `--db` path if using alternate database, otherwise check `~/.finagent/data.db` exists

Reference
- `.claude/skills/ledger-query/examples/common-queries.md` – ready-to-run snippets for frequent questions.
- `.claude/skills/ledger-query/reference/saved-queries.md` – parameters for each saved template.
