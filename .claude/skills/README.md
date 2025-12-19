---
title: Agent Skills Catalog
description: Directory-based skills loaded via progressive disclosure for fin-agent workflows.
---

# Agent Skills Overview

The skills in this directory teach an agent how to drive the `fin-cli` toolkit end-to-end—from scrubbing statements to analyzing trends. Each skill contains a `SKILL.md` playbook, helper scripts, and references that the agent can load incrementally based on user intent.

## Prerequisites
- Install `fin-cli` (e.g., `pip install -e .` or `pipx install fin-cli`) so `fin-scrub`, `fin-edit`, `fin-query`, and `fin-analyze` are available on `PATH`.
- The SQLite ledger defaults to `~/.finagent/data.db`; override with `FINAGENT_DATABASE_PATH` or per-command `--db` if the user points elsewhere.
- Keep the repository root as the working directory when invoking helper scripts referenced through `$SKILL_ROOT`.

## Conventions
- Prefer `fin-query` for read-only access and `fin-edit` for writes (dry-run first, add `--apply` to commit).
- Include `--format csv` to return structured output the agent can reason about; clamp result size with `--limit`.
- Avoid direct `sqlite3` mutations; rely on `fin-cli` commands unless a capability is missing.

## Skill Catalog

### statement-processor
- **Purpose:** Scrub PDFs, build extraction prompts, post-process LLM output, and import enriched CSVs into SQLite.
- **Key actions:** `fin-scrub`, `python scripts/preprocess.py`, `python scripts/postprocess.py --apply-patterns`, `fin-edit import-transactions` (preview then `--apply`).
- **Example prompt:** "Import the September 2025 Chase statement I uploaded." The agent loops through scrub → prompt → LLM CSV → post-process → import.
- **Outputs:** Clean CSVs with `account_key`/`fingerprint`, imported transactions, and learned merchant patterns.

### transaction-categorizer
- **Purpose:** Clear uncategorized transactions via LLM bulk categorization plus interactive follow-up for low-confidence leftovers.
- **Key actions:** `fin-query saved uncategorized`, `python scripts/build_prompt.py`, `fin-edit set-category`, `fin-edit add-merchant-pattern`, `fin-edit delete-transactions` for rollbacks.
- **Example prompt:** "Categorize any uncategorized transactions and show me anything under 0.75 confidence."
- **Outputs:** Updated category assignments, new merchant patterns, and a summary of items requiring manual confirmation.

### spending-analyzer
- **Purpose:** Run analyzers (spending trends, category breakdowns, subscriptions, unusual activity) and assemble narrative summaries.
- **Key actions:** `fin-analyze spending-trends|category-breakdown|merchant-frequency|subscription-detect`, optional `fin-query` lookups for supplemental context.
- **Example prompt:** "Give me a September 2025 spending report with subscriptions and notable changes."
- **Outputs:** CSV/JSON analyzer tables plus natural-language insights for the user.

### ledger-query
- **Purpose:** Answer targeted questions with saved queries or guarded SQL.
- **Key actions:** `fin-query saved merchant_search`, `fin-query saved category_transactions`, `fin-query sql "SELECT ..."` (single SELECT/WITH, implicit LIMIT), `fin-query schema` for structure.
- **Example prompt:** "How much did we spend at Costco in Q3 2025?"
- **Outputs:** Focused CSV tables and explanation of totals, merchants, or time ranges found.

### asset-tracker
- **Purpose:** Extract holdings from investment/brokerage statements and import into the asset tracking database. Supports portfolio analysis, allocation breakdowns, and rebalancing suggestions.
- **Key actions:**
  - **Import:** `fin-scrub`, `python scripts/preprocess.py`, LLM extraction, `python scripts/postprocess.py`, `fin-edit asset-import --from <json>`.
  - **Query:** `fin-query saved portfolio_snapshot`, `fin-query saved allocation_by_class`, `fin-query saved stale_holdings`, `fin-query unimported <dir>`.
  - **Analyze:** `fin-analyze portfolio-trend`, `fin-analyze cash-mix`, `fin-analyze rebalance-suggestions` (use `fin-query` for allocation + concentration).
  - **Manage:** `fin-edit accounts-create`, `fin-edit holdings-transfer`, `fin-edit holdings-deactivate`.
- **Example prompts:**
  - "Import my Schwab statement ~/Downloads/schwab-nov-2025.pdf"
  - "Show my current asset allocation"
  - "What's my portfolio trend over the last 6 months?"
  - "Suggest rebalancing for 60/30/10 equities/bonds/cash"
- **Outputs:** Instruments, holdings, and valuations imported to SQLite; allocation breakdowns; trend charts; rebalancing recommendations.

## Cross-Skill Workflow

**Transactions:**
1. **Import:** statement-processor handles scrubbing, extraction, enrichment, and import.
2. **Categorize:** transaction-categorizer bulk assigns categories and captures confidence.
3. **Analyze:** spending-analyzer produces reports, timelines, and subscription insights.
4. **Answer questions:** ledger-query retrieves exact transaction details or aggregates on demand.

**Assets:**
1. **Import:** asset-tracker handles scrubbing, extraction, validation, and import of investment statements.
2. **Analyze:** asset-tracker runs allocation, trend, and rebalancing analyzers.
3. **Cross-reference:** Correlate cash positions with spending patterns using spending-analyzer.

Agents can load additional skills as needed (e.g., run analyzer results after import, then return to categorizer if gaps remain). See Anthropic’s skills documentation for general guidance: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview

## LLM Usage Tips
- Reuse saved queries instead of writing SQL when possible; they encode joins against the normalized schema (transactions reference categories/accounts via IDs).
- Validate category names with `fin-query saved categories --limit 200 --format csv` to avoid taxonomy drift.
- Never use Claude Code's file attach `@` syntax for statements; always run them through `fin-scrub` first to prevent leaking raw PII.
- For asset imports, use `fin-query unimported <directory>` before bulk imports to skip already-imported statements.
- Verify schema structure with `fin-query schema --table <table>` before writing ad-hoc SQL for asset tables (instruments, holdings, holding_values, etc.).
