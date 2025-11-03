# General

- Write comments in the code if it will help a future LLM understand details or nuance about how the code works.
- When addressing a CLI/runtime error, rerun the user-reported command locally to confirm the fix before reporting back.
- Install `fin-cli` (pip install/pipx) so `fin-scrub`, `fin-edit`, `fin-query`, and `fin-analyze` resolve on `PATH`; repository virtualenv activation is optional when the CLI is installed globally.
- Read README.md
- Run `pytest` regularly to catch regressions early and keep the test suite green.

## Schema & Query Tips
- Core transaction columns: `date`, `merchant`, `original_description`, `amount`, `account_id`, `category_id`, `metadata`. There is no generic `description` field.
- Prefer `fin-query schema --table transactions --format table` (or other `fin-query` commands) instead of invoking `sqlite3` directly when you need to inspect structure or run ad-hoc SQL.
- Use saved queries where possible; `merchant_search` covers LIKE-based merchant lookups and `category_transactions` pulls category/subcategory slices.

# How to write implementation plans
- Prefix the plan name with "plan_" and suffix with a date like "_092325"
- After you create a new plan, pause to ask the user to review and verify before continuing. Show the user the plan in your output when you ask them to verify.
- Read the specs carefully (or consider the user's instructions carefully) to understand the requirements and the overall architecture.
- Use markdown to write plans.
- Use checkboxes to track progress on todo items.
- Todo items should be specific and actionable. 
- Todo items should be organized into logical phases.
- Add notes on architecture, schema changes, relevant files, technical decisions, choices made, etc as needed.
- The plan is meant for an LLM to work on it.
- Persist the plan to the plans/ directory
  - When work continues on an existing effort, update the existing plan file instead of spinning up a new mini-plan; keep everything consolidated in the main plan document.
  - Exception: for small/medium, low-risk changes you can work without creating a persisted plan; large efforts should continue using plan files.

# How to work on plans

You may be given an implementation plan to work through. If so, here are guidelines on how to work with them:

- Pause after each phase so I can test/review. Give me a good summary of changes made, things I need to do manually, tradeoffs/choices you made, and anything else you think needs to be brought to my attention to review the changes well. 
- Update the checkboxes next to todo items in the plan as you complete them. Also add notes on your changes to the plan as you go: relevant files, architecture or other technical decisions, choices made, etc -- these will be helpful for a future LLM to continue work if we get interrupted.
- Ask any questions needed as we go.

# Tooling conventions

- When you need to inspect the local SQLite database, prefer the `fin-query` CLI (`fin-query saved …`, `fin-query schema …`) for read-only exploration; fall back to the `sqlite3` CLI only when functionality is missing.
- Prefer `fin-query` for read-only access and `fin-edit` for writes—preview first, then add `--apply` to commit changes.
- Avoid direct `sqlite3` mutations; rely on `fin-cli` commands unless no alternative exists.
- Validate category names with `fin-query saved categories --limit 200 --format csv` to keep taxonomy consistent.
- Reuse saved queries instead of writing ad-hoc SQL when possible; they already join against the normalized schema (`transactions` references `categories`/`accounts` by ID).
- Never use Claude Code’s file attach `@` syntax for statements; always run PDFs through `fin-scrub` first to prevent raw PII leakage.
- Skills overview and usage guidance: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview
- Repository skill catalog lives in `.claude/skills/`; load only the skills required for the current workflow.

## Code Search with ast-grep

Use `ast-grep` (sg) for semantic code searches across the codebase. It's more powerful than text-based grep for finding code patterns.

### Common ast-grep patterns for this Python codebase:

Find all function definitions:
```bash
sg --pattern 'def $FUNC($$$):' --lang python
```

Find specific function calls:
```bash
sg --pattern '$OBJ.enhance($$$)' --lang python
sg --pattern 'categorize($$$)' --lang python
```

Find all class definitions:
```bash
sg --pattern 'class $CLASS($$$):' --lang python
```

Find database queries:
```bash
sg --pattern 'execute($SQL)' --lang python
sg --pattern 'executemany($$$)' --lang python
```

Find imports:
```bash
sg --pattern 'from $MODULE import $$$' --lang python
sg --pattern 'import $MODULE' --lang python
```

Find decorated functions (e.g., CLI commands):
```bash
sg --pattern '@click.command()
def $FUNC($$$):' --lang python
```

Find specific method calls on objects:
```bash
sg --pattern '$VAR.apply_decisions($$$)' --lang python
```

Find exception handling:
```bash
sg --pattern 'try:
    $$$
except $EXCEPTION:
    $$$' --lang python
```

### Tips:
- Use `$VAR` for single identifiers
- Use `$$$` for any sequence of code (wildcards)
- Add `--json` for machine-readable output
- Add `-A 3 -B 3` to show context lines
- Combine with standard Unix tools: `sg --pattern 'def $FUNC($$$):' --lang python | grep enhance`
