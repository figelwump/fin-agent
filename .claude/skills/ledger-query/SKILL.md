---
name: ledger-query
description: Query the financial ledger with fin-query saved templates and ad-hoc SQL.
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
- Merchant lookups: `fin-query saved merchant_search --param pattern=%YouTube TV% --limit 12`.
- Category slices: `fin-query saved category_transactions --param category=Entertainment --param subcategory=Comedy --limit 20`.

Workflow
1. Clarify the time frame, category, or pattern the user cares about.
2. Pick an existing saved query (reference doc lists them) or compose a `fin-query sql` query.
3. Run with `--format json` when structured parsing is needed; otherwise table output is fine.
4. Summarise findings back to the user, citing totals, dates, or counts.

Reference
- `examples/common-queries.md` – ready-to-run snippets for frequent questions.
- `reference/saved-queries.md` – parameters for each saved template.
