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
- **Example prompt:** “Import the September 2025 Chase statement I uploaded.” The agent loops through scrub → prompt → LLM CSV → post-process → import.
- **Outputs:** Clean CSVs with `account_key`/`fingerprint`, imported transactions, and learned merchant patterns.

### transaction-categorizer
- **Purpose:** Clear uncategorized transactions via LLM bulk categorization plus interactive follow-up for low-confidence leftovers.
- **Key actions:** `fin-query saved uncategorized`, `python scripts/build_prompt.py`, `fin-edit set-category`, `fin-edit add-merchant-pattern`, `fin-edit delete-transactions` for rollbacks.
- **Example prompt:** “Categorize any uncategorized transactions and show me anything under 0.75 confidence.”
- **Outputs:** Updated category assignments, new merchant patterns, and a summary of items requiring manual confirmation.

### spending-analyzer
- **Purpose:** Run analyzers (spending trends, category breakdowns, subscriptions, unusual activity) and assemble narrative summaries.
- **Key actions:** `fin-analyze spending-trends|category-breakdown|merchant-frequency|subscription-detect`, optional `fin-query` lookups for supplemental context.
- **Example prompt:** “Give me a September 2025 spending report with subscriptions and notable changes.”
- **Outputs:** CSV/JSON analyzer tables plus natural-language insights for the user.

### ledger-query
- **Purpose:** Answer targeted questions with saved queries or guarded SQL.
- **Key actions:** `fin-query saved merchant_search`, `fin-query saved category_transactions`, `fin-query sql "SELECT ..."` (single SELECT/WITH, implicit LIMIT), `fin-query schema` for structure.
- **Example prompt:** “How much did we spend at Costco in Q3 2025?”
- **Outputs:** Focused CSV tables and explanation of totals, merchants, or time ranges found.

## Cross-Skill Workflow
1. **Import:** statement-processor handles scrubbing, extraction, enrichment, and import.
2. **Categorize:** transaction-categorizer bulk assigns categories and captures confidence.
3. **Analyze:** spending-analyzer produces reports, timelines, and subscription insights.
4. **Answer questions:** ledger-query retrieves exact transaction details or aggregates on demand.

Agents can load additional skills as needed (e.g., run analyzer results after import, then return to categorizer if gaps remain). See Anthropic’s skills documentation for general guidance: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview

## LLM Usage Tips
- Reuse saved queries instead of writing SQL when possible; they encode joins against the normalized schema (transactions reference categories/accounts via IDs).
- Validate category names with `fin-query saved categories --limit 200 --format csv` to avoid taxonomy drift.
- Never use Claude Code’s file attach `@` syntax for statements; always run them through `fin-scrub` first to prevent leaking raw PII.
