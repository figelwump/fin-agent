---
name: transaction-categorizer
description: Categorize uncategorized transactions using LLM-first approach, then interactive review for leftovers.
allowed-tools: Bash, Read, Grep, Glob
---

# Transaction Categorizer Skill

Teach the agent how to categorize uncategorized transactions using a two-phase approach:
1. **LLM bulk categorization** using the configured model for ALL uncategorized transactions
2. **Interactive manual review** for low-confidence or failed categorizations, using LLM suggestions as starting points

The skill validates against the existing taxonomy and learns merchant patterns for future auto-categorization.

Environment
- `source .venv/bin/activate`

Database Path
- Omit `--db` to use the default location (`~/.finagent/data.db`)
- Only specify `--db <path>` when the user explicitly provides an alternate database

Working Directory
- Use `.claude/skills/transaction-categorizer/scripts/bootstrap.sh` to create a workspace for the categorization session (it reuses `SESSION_SLUG` exported by the statement-processor skill, or accept `--session` when starting standalone): `eval "$(.claude/skills/transaction-categorizer/scripts/bootstrap.sh)"`. This exports:
  - `FIN_CATEGORIZER_WORKDIR` - root working directory
  - `FIN_CATEGORIZER_QUERIES_DIR` - for saved query results (uncategorized.json)
  - `FIN_CATEGORIZER_PROMPTS_DIR` - for generated LLM prompts
  - `FIN_CATEGORIZER_LLM_DIR` - for LLM CSV responses
- The workspace keeps all artifacts organized and makes cleanup easy after categorization is complete

Principles
- Always load the existing taxonomy first to prevent bloat
- Use `fin-edit` for writes (dry-run by default; add `--apply`)
- Prefer existing categories when possible; however, feel free to create new ones as needed
- **LLM-First Approach**: Always try LLM categorization first for ALL uncategorized transactions, then fall back to manual review only for leftovers
- We want to minimize how many transactions a user has to manually review, so think hard to categorize as many transactions as you can.
- **Confidence Threshold**:
  - ≥0.75: High confidence - apply categorization and learn merchant pattern
  - <0.75: Low confidence - save as suggestion for manual review, present to user with LLM's proposed category

## Recommended Workflow

**Step 0: Initialize workspace**

**IMPORTANT**: Set `SESSION_SLUG` before bootstrapping to ensure all commands use the same workspace directory.

**If running after statement-processor**: The `SESSION_SLUG` will already be exported - just run bootstrap:
```bash
eval "$(.claude/skills/transaction-categorizer/scripts/bootstrap.sh)"
```

**If running standalone**: Export a session slug first, then bootstrap:
```bash
export SESSION_SLUG="categorize-$(date +%Y%m%d-%H%M%S)"
eval "$(.claude/skills/transaction-categorizer/scripts/bootstrap.sh)"
```

All subsequent commands in the session **must** maintain this `SESSION_SLUG` to use the same workspace. Either:
- Run all commands in a single bash session (preferred), OR
- Export `SESSION_SLUG` at the start of each command chain

**Step 1: Query and save uncategorized transactions**

**Best Practice**: Chain all commands together in a single bash invocation to maintain the workspace context:
```bash
source .venv/bin/activate && \
export SESSION_SLUG="categorize-$(date +%Y%m%d-%H%M%S)" && \
eval "$(.claude/skills/transaction-categorizer/scripts/bootstrap.sh)" && \
fin-query saved uncategorized --format json > "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized.json" && \
jq 'length' "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized.json"
```

Alternatively, if running commands separately, ensure `SESSION_SLUG` is exported in each command:
```bash
export SESSION_SLUG="categorize-$(date +%Y%m%d-%H%M%S)"
eval "$(.claude/skills/transaction-categorizer/scripts/bootstrap.sh)"
fin-query saved uncategorized --format json > "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized.json"
jq 'length' "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized.json"
```

If no uncategorized transactions found (count is 0), you're done!

**Step 2: Generate LLM categorization prompt**
```bash
python .claude/skills/transaction-categorizer/scripts/build_prompt.py \
  --input "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized.json" \
  --output "$FIN_CATEGORIZER_PROMPTS_DIR/categorization-prompt.txt"

cat "$FIN_CATEGORIZER_PROMPTS_DIR/categorization-prompt.txt"
```

**Step 3: Send prompt to your categorization LLM**
- Copy the generated prompt and send it to your configured categorization model
- The LLM will return a CSV with columns: `transaction_id,canonical_merchant,category,subcategory,confidence,notes`
- Save the LLM's CSV response to `$FIN_CATEGORIZER_LLM_DIR/categorizations.csv`

**Step 4: Review and apply LLM categorization results**

Read the LLM's CSV response from `$FIN_CATEGORIZER_LLM_DIR/categorizations.csv`.

a) **Separate high-confidence from low-confidence results:**
   - High confidence: ≥0.75 - Apply these categorizations and learn patterns
   - Low confidence: <0.75 - Save these as suggestions for manual review

b) **For high-confidence categorizations (≥0.75):**

Preview the categorization:
```bash
fin-edit set-category --transaction-id <id> \
  --category "<category>" --subcategory "<subcategory>" \
  --confidence <confidence> --method llm:auto
```

After reviewing the preview, apply and learn the pattern:
```bash
fin-edit --apply set-category --transaction-id <id> \
  --category "<category>" --subcategory "<subcategory>" \
  --confidence <confidence> --method llm:auto

# Learn the pattern for future auto-categorization
fin-edit --apply add-merchant-pattern --pattern '<pattern_key>' \
  --category "<category>" --subcategory "<subcategory>" --confidence <confidence>
```

c) **For low-confidence categorizations (<0.75):**

Save these to a suggestions file for manual review:
```bash
# Extract low-confidence rows (confidence < 0.75) from LLM CSV, keeping the header
head -n1 "$FIN_CATEGORIZER_LLM_DIR/categorizations.csv" \
  > "$FIN_CATEGORIZER_LLM_DIR/low-confidence-suggestions.csv"
awk -F',' 'NR>1 && $5 < 0.75 {print}' "$FIN_CATEGORIZER_LLM_DIR/categorizations.csv" \
  >> "$FIN_CATEGORIZER_LLM_DIR/low-confidence-suggestions.csv"
```

These low-confidence suggestions will be presented to the user during interactive review as starting points.

**Step 5: Check for remaining uncategorized**
```bash
# Re-query to get current state after applying LLM categorizations
fin-query saved uncategorized --format json > "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized-remaining.json"

# Check count
jq 'length' "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized-remaining.json"
```

If any remain after LLM categorization, proceed to Interactive Manual Review below.

## Interactive Manual Review (only for leftovers after LLM categorization)

Use this workflow only for transactions that the LLM had low confidence on (<0.75) or couldn't categorize.

**1) Load existing taxonomy and LLM suggestions**
```bash
# Load taxonomy
fin-query saved categories --format json > "$FIN_CATEGORIZER_QUERIES_DIR/categories.json"

# Low-confidence LLM suggestions (<0.75) are already saved from Step 4c
# (in $FIN_CATEGORIZER_LLM_DIR/low-confidence-suggestions.csv)
```

**2) Review remaining uncategorized**
```bash
# Use the saved file from Step 5
cat "$FIN_CATEGORIZER_QUERIES_DIR/uncategorized-remaining.json"
```

**3) For each transaction:**
- Show date, merchant, amount, description to the user
- **Check if LLM provided a low-confidence suggestion** (<0.75) for this transaction_id (lookup in low-confidence-suggestions.csv)
- If yes, present it as: `Suggested: Category > Subcategory (confidence: 0.85, from LLM)`
- If no LLM suggestion, suggest categories from existing taxonomy based on merchant similarity
- Ask the user to confirm, modify, or choose a different category

**Example presentation:**
```
Transaction 1:
- Date: Sept 15, 2025
- Merchant: COFFEE BEAN #1234
- Amount: $8.50
- Description: COFFEE BEAN #1234 LOS ANGELES CA

Suggested: Food & Dining > Coffee (confidence: 0.85, from LLM)
Use this category? [y/n or provide alternative]
```

**4) Apply user's categorization**
```bash
# Preview (no writes)
fin-edit set-category --transaction-id <id> \
  --category "Food & Dining" --subcategory "Coffee" \
  --confidence 1.0 --method claude:interactive

# Apply after user confirms
fin-edit --apply set-category --transaction-id <id> \
  --category "Food & Dining" --subcategory "Coffee" \
  --confidence 1.0 --method claude:interactive
```

**5) Learn the pattern**
```bash
# Preview
fin-edit add-merchant-pattern --pattern '<pattern_key>' \
  --category "Food & Dining" --subcategory "Coffee" --confidence 0.95

# Apply when confirmed
fin-edit --apply add-merchant-pattern --pattern '<pattern_key>' \
  --category "Food & Dining" --subcategory "Coffee" --confidence 0.95
```

## Available Commands

- `.claude/skills/transaction-categorizer/scripts/bootstrap.sh`: Initialize a categorization workspace and export environment variables (use via `eval "$(...)"`).
- `python .claude/skills/transaction-categorizer/scripts/build_prompt.py`: Generate LLM categorization prompt from uncategorized transactions JSON.
- `fin-query saved uncategorized`: Query uncategorized transactions from the database.
- `fin-query saved categories`: Query existing category taxonomy.
- `fin-edit set-category`: Apply categorization to a transaction (dry-run by default; add `--apply` to write).
- `fin-edit add-merchant-pattern`: Learn merchant patterns for future auto-categorization (dry-run by default; add `--apply` to write).

## Tips for Efficient Categorization

**When handling multiple transactions from the same merchant:**
- Group by merchant pattern to identify common merchants
- Prioritize high-frequency merchants first to maximize impact
- After categorizing one transaction, immediately add a merchant pattern so future transactions auto-categorize
- Use `fin-edit --apply add-merchant-pattern` aggressively to build up the pattern database

**Progress tracking:**
- Process transactions in batches and show progress ("Categorized 45 of 120 remaining")
- After each batch, validate with `fin-query saved uncategorized` to see remaining count

**Workspace cleanup:**
- Keep the workspace for debugging if categorizations need to be reviewed or reverted

Common Errors
- **Transaction not found**: Verify the transaction ID is correct. Use `fin-query saved uncategorized` or `fin-query saved recent_transactions` to find the correct ID.
- **Category already set**: Transaction is already categorized. Use `fin-edit set-category` to update it (overwrites existing category).
- **Pattern already exists**: Merchant pattern is already learned. Use `fin-edit set-merchant-pattern` to update the existing pattern or choose a more specific pattern key.
- **Duplicate fingerprint**: Transaction may already exist in database from a previous import. Check with `fin-query saved recent_transactions`.

Validation After Categorization
After categorizing transactions, verify the changes:
```bash
# Verify the transaction was updated
fin-query saved recent_transactions --limit 5 --format table

# Check remaining uncategorized count
fin-query saved uncategorized --format json | jq 'length'

# Verify merchant pattern was learned (if applicable)
fin-query saved merchant_patterns --param pattern='PATTERN%' --limit 5
```

Cross-Skill Transitions
- **From statement-processor**: After importing transactions (including uncategorized ones), use this skill to categorize remaining transactions. Always try the automated LLM pass first, then manual review for leftovers.
- **To explore similar transactions**: Use `ledger-query` skill with `merchant_search` or `category_transactions` saved queries to see historical patterns
- **After categorization is complete**: Use `spending-analyzer` skill to analyze spending patterns across the newly categorized transactions

When to Use This Skill vs Statement-Processor
- **Use statement-processor** for initial extraction and categorization from PDF statements (handles LLM extraction, pattern matching, and import)
- **Use transaction-categorizer** after import to handle remaining uncategorized transactions (handles LLM bulk categorization for ALL uncategorized, then manual review for leftovers only)

References
- .claude/skills/transaction-categorizer/examples/interactive-review.md
- .claude/skills/transaction-categorizer/examples/pattern-learning.md
- .claude/skills/transaction-categorizer/reference/common-categories.md
