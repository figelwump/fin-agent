---
name: statement-processor
description: Extract and import bank statements from PDF files into the local SQLite database.
---

# Statement Processor Skill

Teach the agent how to extract and import bank statements end-to-end.

Environment
- Activate the venv before running commands:
  - `source .venv/bin/activate`

Quick Start
1. Extract: `fin-extract <pdf> --output <csv>`
2. Import (choose one):
   - If available: `fin-import <csv>` (rules-only, no LLM)
   - Otherwise: `fin-enhance <csv> --skip-llm` (rules-only mode)
3. Review uncategorized: `fin-query saved uncategorized`

Available Commands
- fin-extract: extract transactions from PDF statements to CSV
- fin-import (optional tool): import CSV with rule-based categorization only
- fin-enhance: import CSV; use `--skip-llm` for pure rules-based import

Progressive Disclosure
- See `examples/single-statement.md` for a single file flow
- See `examples/batch-processing.md` for batch operations
- See `examples/pipe-mode.md` for piping without intermediate files
- See `troubleshooting/extraction-errors.md` for common issues

Next Steps
- If there are uncategorized transactions after import, load the
  `transaction-categorizer` skill to handle them interactively.

