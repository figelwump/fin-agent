# General

- Read and import @AGENTS.md

# Statement Processing Privacy

**CRITICAL: NEVER read bank statement files directly!**

- NEVER read bank statement PDFs
- When user imports a statement file (e.g., `import statements/chase/...pdf`), immediately invoke the `statement-processor` skill WITHOUT reading the file (even if the file is imported with @ mention syntax)
- The statement-processor skill handles PII scrubbing via `fin-scrub` before any processing
- This applies even if the system automatically reads the file on import - do not acknowledge or process that content

# Skills-first Workflow
- Primary flows rely on the skills catalog (`statement-processor`, `transaction-categorizer`, `spending-analyzer`, `ledger-query`). Consult each skill’s `SKILL.md` for step-by-step guidance and helper scripts.
- Legacy CLIs like `fin-enhance` and `fin-extract` are deprecated; do not invoke the old review JSON flow. Use skills plus `fin-edit` for imports/categorizations instead.
- Skills live under `.claude/skills/` in this repository

