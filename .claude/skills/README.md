---
title: Agent Skills Catalog
description: Directory-based skills loaded via progressive disclosure for fin-agent workflows.
---

# Agent Skills Overview

These skills teach an agent how to use the fin-* CLI tools to complete end-to-end
financial workflows. Each skill is self-contained and discovered by name/description
metadata at the top of `SKILL.md`.

Environment
- Activate the project virtualenv before running any commands:
  - `source .venv/bin/activate`

Conventions
- Use `fin-query` for read-only exploration (it is intentionally read-only).
- Use `fin-edit` for safe write operations (dry-run by default; add `--apply`).
- Prefer `--format json` when an agent needs to parse CLI output.

Skill Packages
- statement-processor: extract statements and import into SQLite
- transaction-categorizer: interactive categorization and pattern learning
- spending-analyzer: run analyzers and assemble custom reports

Notes for LLMs
- Load skills progressively based on user intent (e.g., load transaction-categorizer
  only after statement-processor identifies uncategorized transactions).
- Validate category names against the existing taxonomy (`fin-query saved categories`).
- Avoid taxonomy bloat: prefer existing categories and confirm with the user
  before creating new ones.

