# General

- Write comments in the code if it will help a future LLM understand details or nuance about how the code works.

# How to write implementation plans
- Read the specs carefully to understand the requirements and the overall architecture.
- Use markdown to write plans.
- Use checkboxes to track progress on todo items.
- Todo items should be specific and actionable. 
- Todo items should be organized into logical phases.
- Add notes on architecture, relevant files, technical decisions, choices made, etc as needed.
- The plan is meant for an LLM to work on it.
- Persist the plan to the plans/ directory

# How to work on plans

You may be given an implementation plan to work through. If so, here are guidelines on how to work with them:

- Pause after each phase so i can test/review. Give me a good summary of changes made, things i need to do manually, tradeoffs/choices you made, and anything else you think needs to be brought to my attention to review the changes well. 
- Update the checkboxes next to todo items in the plan as you complete them. also add notes on your changes to the plan as you go: relevant files, architecture or other technical decisions, choices made, etc -- these will be helpful for a future LLM to continue work if we get interrupted. ask any questions needed as we go.

# Tooling conventions

- When you need to inspect the local SQLite database, use the `sqlite3` CLI rather than ad-hoc Python scripts. Example: `sqlite3 ~/.finagent/data.db`. From there you can run commands like `.tables` or `SELECT COUNT(*) FROM transactions;`.

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

# fin-enhance Review Process

## Review JSON Output
When running `fin-enhance transactions.csv --review-output review.json`, the unresolved transactions are written in this format:
```json
{
  "version": "1.0",
  "generated_at": "ISO-8601 timestamp",
  "review_needed": [
    {
      "type": "transaction_review",
      "id": "unique transaction hash",
      "date": "YYYY-MM-DD",
      "merchant": "merchant name",
      "amount": decimal,
      "original_description": "original transaction description",
      "account_id": integer
    }
  ]
}
```

## Decisions JSON Format
To apply review decisions, create a decisions JSON file with this format:
```json
{
  "version": "1.0",
  "decisions": [
    {
      "id": "transaction hash matching review.json",
      "category": "required category name",
      "subcategory": "required subcategory name",
      "learn": true,  // optional, default true - whether to learn from this pattern
      "confidence": 0.95,  // optional, default 1.0 - confidence level (0-1)
      "method": "review:manual",  // optional, default "review:manual"
      "notes": "optional notes about the decision"
    }
  ]
}
```

Required fields:
- `id`: Transaction fingerprint/hash from review.json
- `category`: Main category (e.g., "Shopping", "Food & Dining")
- `subcategory`: Specific subcategory (e.g., "Online", "Groceries")

Optional fields:
- `learn`: Whether to learn from this merchant pattern for future auto-categorization
- `confidence`: Confidence level from 0 to 1
- `method`: How the decision was made (typically "review:manual")
- `notes`: Any additional notes (not used by the system)

Apply decisions using: `fin-enhance --apply-review decisions.json`
