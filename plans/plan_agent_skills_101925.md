# Agent Skills for fin-agent - Implementation Plan v2

**Created:** 2025-10-19
**Updated:** 2025-10-19 (simplified architecture)
**Status:** Planning
**Framework:** Anthropic Agent Skills (Oct 2025)
**Docs:** https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills

## Overview

Create Agent Skills that teach Claude **how** to use the fin-agent CLI tools effectively for financial management workflows. Skills are directory-based packages containing instructions, examples, and resources that Claude loads dynamically using progressive disclosure.

## Simplified Architecture

### Core Philosophy

**CLI tools should be simple, focused, and composable.**
**Claude (via Agent Skills) handles orchestration, LLM-powered categorization, and report generation.**

### CLI Tool Strategy

**Existing CLI tools (keep all, unchanged):**
- `fin-extract` - PDF → CSV extraction
- `fin-enhance` - Import + categorization with LLM/review workflow
- `fin-query` - Database queries (saved + ad-hoc SQL)
- `fin-analyze` - Individual analysis types
- `fin-export` - Multi-analyzer report generation

**New CLI tool (optional, to create):**
- `fin-import` - CSV → SQLite with rule-based categorization only
  - Simpler alternative to fin-enhance for import-only use cases
  - NO LLM calls (just pattern matching)
  - Fast, deterministic, automatable

**Which tools do Agent Skills use?**

Skills will teach Claude to use:
- ✅ `fin-extract` - For PDF extraction
- ✅ `fin-import` (new) or `fin-enhance --skip-llm` - For simple imports
- ✅ `fin-query` - For database queries and direct SQL
- ✅ `fin-analyze` - For individual analyses

Skills will NOT typically use (though they remain available for CLI users/automation):
- ⚠️ `fin-enhance` (full mode) - Skills handle categorization interactively instead of via LLM API + JSON files
- ⚠️ `fin-export` - Skills orchestrate fin-analyze directly for more flexible custom reports

**Important:** We're not removing or deprecating fin-enhance or fin-export. They remain fully supported for:
- Automated/batch processing
- Existing scripts and workflows
- Users who prefer the current workflow
- MCP tools that depend on them

### Why This Approach

1. **No breaking changes** - All existing tools remain functional
2. **Skills use simpler patterns** - Direct DB access, orchestration, conversation
3. **Best of both worlds** - Automation via CLI, interactivity via skills
4. **No duplicate LLM calls** - Claude handles categorization, not separate OpenAI API
5. **Progressive enhancement** - fin-import adds simpler option without removing fin-enhance

## fin-import Specification

### Purpose
Import CSV transactions into SQLite and apply learned merchant patterns (rules-based only).

### Usage

```bash
# Basic import
fin-import transactions.csv

# What it does:
# 1. Parse CSV (8 columns from fin-extract)
# 2. Deduplicate against existing transactions
# 3. Apply merchant_patterns from database
# 4. Insert into transactions table
# 5. Report stats: inserted, duplicates, auto-categorized, uncategorized
```

### Key Flags

- `--stdin` / `--stdout` - Pipe mode compatibility
- `--force` - Skip deduplication
- `--dry-run` - Preview without writing to DB

### Output Example

```
Import summary:
  Transactions processed: 45
  Inserted: 42
  Duplicates skipped: 3
  Auto-categorized (rules): 35
  Uncategorized: 7

Run `fin-query saved uncategorized` to review uncategorized transactions.
```

### What It Does NOT Do

- Make LLM API calls
- Generate review JSON files
- Handle decisions JSON

**Note:** fin-enhance still handles these for automation/batch scenarios. fin-import is just a simpler alternative for skills and scripting.

## Agent Skills Directory Structure

Based on Anthropic's recommendations, each skill is self-contained with metadata-driven discovery:

```
skills/
├── statement-processor/
│   ├── SKILL.md                     # Metadata + main instructions
│   ├── examples/
│   │   ├── single-statement.md     # Basic workflow
│   │   ├── batch-processing.md     # Multiple PDFs
│   │   └── pipe-mode.md            # Advanced piping
│   └── troubleshooting/
│       └── extraction-errors.md     # Common issues
├── transaction-categorizer/
│   ├── SKILL.md                     # Metadata + main instructions
│   ├── examples/
│   │   ├── interactive-review.md   # Conversational categorization
│   │   └── pattern-learning.md     # Teaching patterns
│   └── reference/
│       └── common-categories.md     # Standard category taxonomy
└── spending-analyzer/
    ├── SKILL.md                     # Metadata + main instructions
    ├── examples/
    │   ├── common-queries.md        # Typical analyses
    │   ├── custom-reports.md        # Multi-analyzer reports
    │   └── insights.md              # Proactive patterns
    └── reference/
        └── all-analyzers.md         # Complete analyzer docs
```

### How Claude Discovers Skills

Each `SKILL.md` starts with YAML frontmatter:

```yaml
---
name: statement-processor
description: Extract and import bank statements from PDFs. Use when user wants to process financial statements or PDFs.
---
```

Claude pre-loads all skill names/descriptions at startup and automatically loads the right skills based on the user's task. No parent skill or README needed - skills reference each other naturally in their instructions.

## Skill 1: Statement Processor

**Directory:** `skills/statement-processor/`

### `SKILL.md` (Main Instructions)

```markdown
---
name: statement-processor
description: Extract and import bank statements from PDF files into SQLite database. Use when user wants to process financial statements, bank PDFs, or import transaction data.
---

# Statement Processor Skill

Teach Claude how to extract and import bank statements end-to-end.

> Environment: before running any `fin-*` commands, activate the project virtualenv:
>
> ```bash
> source .venv/bin/activate
> ```

## Quick Start

1. Extract: `fin-extract <pdf> --output <csv>`
2. Import: `fin-import <csv>`
3. Categorize uncategorized: [See transaction-categorizer skill]

## Available Commands

### fin-extract

Extract transactions from PDF bank statements.

Basic usage:
```bash
fin-extract statement.pdf --output transactions.csv
```

[Progressive disclosure: Link to examples/single-statement.md for details]

### fin-import

Import CSV into database with rule-based categorization.

Basic usage:
```bash
fin-import transactions.csv
```

[Progressive disclosure: Link to examples/single-statement.md for details]

## Common Workflows

- [Single statement](examples/single-statement.md) - Extract + import one PDF
- [Batch processing](examples/batch-processing.md) - Process multiple PDFs
- [Pipe mode](examples/pipe-mode.md) - No intermediate files

## Troubleshooting

[Link to troubleshooting/extraction-errors.md when errors occur]

## Next Steps

After import, if there are uncategorized transactions, Claude will automatically load the `transaction-categorizer` skill to handle them interactively (based on its description metadata).
```

### `examples/single-statement.md`

```markdown
# Single Statement Processing

## Step 1: Extract

```bash
fin-extract ~/Downloads/chase-sept-2025.pdf --output ~/fin-data/chase-sept.csv
```

Output: CSV with 8 columns (date, merchant, amount, original_description, account_name, institution, account_type, account_key)

## Step 2: Import

```bash
fin-import ~/fin-data/chase-sept.csv
```

Output:
- Inserts new transactions
- Skips duplicates
- Applies known merchant patterns
- Reports how many need categorization

## Step 3: Check Results

```bash
# View recent imports
fin-query saved recent_transactions --limit 10

# Check uncategorized
fin-query saved uncategorized
```

## Next: Categorize

If there are uncategorized transactions, load the `transaction-categorizer` skill to handle them interactively.
```

### `examples/batch-processing.md`

```markdown
# Batch Processing

## Extract All PDFs

```bash
for pdf in ~/Downloads/statements/*.pdf; do
    basename=$(basename "$pdf" .pdf)
    fin-extract "$pdf" --output "~/fin-data/$basename.csv"
done
```

## Import All CSVs

```bash
fin-import ~/fin-data/*.csv
```

fin-import handles multiple files and provides combined stats.

## Pipe Mode (No Intermediate Files)

```bash
for pdf in ~/Downloads/statements/*.pdf; do
    fin-extract "$pdf" --stdout
done | fin-import --stdin
```

This streams extraction directly into import.
```

### `troubleshooting/extraction-errors.md`

```markdown
# Extraction Troubleshooting

## "No transactions extracted"

**Cause:** Unsupported bank or PDF format

**Solutions:**
1. Check supported banks: `fin-extract dev list-plugins`
2. Try different engine: `fin-extract <pdf> --engine pdfplumber`
3. Check if PDF is scanned image (not supported)

## "CSV format invalid"

**Cause:** Manually edited CSV or old extractor version

**Solution:** Re-extract from original PDF

## Database Locked

**Cause:** Another fin-cli process using DB

**Solution:** Wait or kill stuck process with `lsof ~/.finagent/data.db`
```

## Skill 2: Transaction Categorizer

**Directory:** `skills/transaction-categorizer/`

### `SKILL.md` (Main Instructions)

```markdown
---
name: transaction-categorizer
description: Interactively categorize uncategorized transactions by conversing with user about categories and updating database. Use after importing statements when transactions need categorization or when user asks to categorize or review transactions.
---

# Transaction Categorizer Skill

Teach Claude how to interactively categorize transactions using conversation instead of JSON files.

## Overview

After running `fin-import`, some transactions may be uncategorized. Your job is to:
1. Load existing category taxonomy from database
2. Query uncategorized transactions
3. Suggest categories from existing taxonomy (to prevent bloat)
4. Ask user for categorization (conversationally)
5. Update database directly
6. Learn patterns for future automation

## Critical: Taxonomy Consistency

**ALWAYS load existing categories first** to prevent taxonomy bloat (e.g., creating both "Food & Dining" and "Dining Out" or "Food and Dining").

```bash
# Load existing taxonomy
fin-query saved categories --format json
```

This gives you the canonical list of categories and subcategories. Use these when suggesting categorizations.

## Step-by-Step Workflow

> Environment: activate the venv before commands: `source .venv/bin/activate`.

Note: `fin-query` is intentionally read-only (see fin_cli/fin_query/executor.py) and is perfect for discovery and review. For write operations (updating a transaction's category, learning a merchant pattern), prefer the `fin-edit` CLI (default is dry-run, use `--apply` to write). As a fallback, you can use the `sqlite3` CLI against the user's database (default: `~/.finagent/data.db`).

### 0. Load Existing Taxonomy (REQUIRED FIRST STEP)

```bash
fin-query saved categories --format json
```

Parse this to understand:
- What categories already exist
- What subcategories are under each category
- Usage counts (prefer commonly-used categories)

### 1. Find Uncategorized Transactions

```bash
fin-query saved uncategorized --format json
```

### 2. Present to User (Conversationally)

For each transaction:
- Show: date, merchant, amount, description
- Suggest categories **from existing taxonomy** based on merchant patterns
- Only suggest creating new categories if truly necessary

Example:
```
Transaction from Sept 15:
- Merchant: STARBUCKS #1234
- Amount: $5.50
- Description: STARBUCKS STORE #1234

Based on your existing categories, this looks like:
  Food & Dining > Coffee

You already have 87 transactions in this category.
Should I use this category?
```

**Important:** Frame suggestions using existing categories to maintain consistency.

### 3. Update Database (Preferred: fin-edit)

Once user confirms, set the category using `fin-edit` (defaults to dry-run). Only write when the user approves by adding `--apply`.

```bash
# Preview (no writes)
fin-edit --db ~/.finagent/data.db \
  set-category \
  --transaction-id <id> \
  --category "Food & Dining" \
  --subcategory "Coffee" \
  --confidence 1.0 \
  --method claude:interactive

# Apply changes
fin-edit --db ~/.finagent/data.db --apply \
  set-category \
  --transaction-id <id> \
  --category "Food & Dining" \
  --subcategory "Coffee"
```

If the category does not exist, add `--create-if-missing` to create it.

Fallback with sqlite3 (if needed): see the sqlite3 examples in the appendix of this skill.

### 4. Learn the Pattern (Optional)

If the user says "remember this for future Starbucks charges", upsert a pattern with `fin-edit`:

```bash
# Preview
fin-edit --db ~/.finagent/data.db \
  add-merchant-pattern \
  --pattern 'STARBUCKS%' \
  --category "Food & Dining" \
  --subcategory "Coffee" \
  --confidence 0.95

# Apply
fin-edit --db ~/.finagent/data.db --apply \
  add-merchant-pattern \
  --pattern 'STARBUCKS%' \
  --category "Food & Dining" \
  --subcategory "Coffee" \
  --confidence 0.95
```

Next time `fin-import` runs, it will auto-categorize Starbucks transactions.

## Common Patterns

[Link to examples/interactive-review.md]
[Link to examples/pattern-learning.md]

## Category Taxonomy

[Link to reference/common-categories.md]
```

### `examples/interactive-review.md`

```markdown
# Interactive Review Workflow

## Full Example Session

```bash
# 0. FIRST: Load existing categories
$ fin-query saved categories --format json
```

Claude receives existing taxonomy:
```json
[
  {"category": "Food & Dining", "subcategory": "Coffee", "count": 87},
  {"category": "Food & Dining", "subcategory": "Restaurants", "count": 234},
  {"category": "Shopping", "subcategory": "Online", "count": 156},
  ...
]
```

Claude now knows the canonical taxonomy.

```bash
# 1. Get uncategorized
$ fin-query saved uncategorized --format json
```

Claude receives:
```json
[
  {"id": 123, "date": "2025-09-15", "merchant": "AMZN MKTP US", "amount": 45.67},
  {"id": 124, "date": "2025-09-16", "merchant": "STARBUCKS #1234", "amount": 5.50}
]
```

Claude presents to user (using existing taxonomy):
```
I found 2 uncategorized transactions. Let's review:

Transaction 1:
- Date: Sept 15, 2025
- Merchant: AMZN MKTP US (Amazon Marketplace)
- Amount: $45.67

Suggested category: Shopping > Online
Is this correct?
```

User: "Yes"

Claude updates:
```bash
$ fin-query sql "UPDATE transactions SET category='Shopping', subcategory='Online', categorization_confidence=1.0, categorization_method='claude:interactive' WHERE id=123"
```

Claude continues:
```
✓ Updated.

Transaction 2:
- Date: Sept 16, 2025
- Merchant: STARBUCKS #1234
- Amount: $5.50

Suggested category: Food & Dining > Coffee
Should I remember this pattern for all Starbucks transactions?
```

User: "Yes, always categorize Starbucks as coffee"

Claude updates transaction AND learns pattern:
```bash
# Update transaction
$ fin-query sql "UPDATE transactions SET category='Food & Dining', subcategory='Coffee', categorization_confidence=1.0, categorization_method='claude:interactive' WHERE id=124"

# Learn pattern
$ fin-query sql "INSERT INTO merchant_patterns (pattern, category, subcategory, confidence, method, created_at) VALUES ('STARBUCKS%', 'Food & Dining', 'Coffee', 0.95, 'user_trained', datetime('now'))"
```

Claude confirms:
```
✓ Updated transaction and learned pattern.
Future Starbucks charges will automatically categorize as Food & Dining > Coffee.

All transactions categorized! 🎉
```
```

### `reference/common-categories.md`

```markdown
# Category Taxonomy Guidelines

## Loading User's Taxonomy

**ALWAYS query the user's existing categories first:**

```bash
fin-query saved categories --format json
```

This is the source of truth for what categories exist in their database.

## Common/Suggested Categories (Fallback Only)

Use these as suggestions ONLY if the user's database is empty or a truly new category is needed:

### Food & Dining
- Restaurants
- Fast Food
- Coffee Shops
- Groceries
- Bars & Nightlife

### Shopping
- Online (Amazon, etc.)
- Clothing
- Electronics
- Home & Garden
- Sporting Goods

### Transportation
- Gas & Fuel
- Public Transportation
- Parking
- Ride Share
- Auto Maintenance

### Bills & Utilities
- Phone
- Internet
- Electric
- Water
- Trash/Recycling

### Entertainment
- Movies & Streaming
- Music
- Sports
- Hobbies
- Books

### Healthcare
- Doctor
- Dentist
- Pharmacy
- Vision

### Financial
- Bank Fees
- Interest Charges
- ATM Fees
- Service Charges

### Income
- Salary/Paycheck
- Reimbursement
- Refund

## Preventing Taxonomy Bloat

**Critical:** Always prefer existing categories over creating new ones.

When user suggests a category not in their database:
1. Check if it's semantically similar to existing category
2. Suggest the existing alternative first
3. Only create new if user insists or it's truly distinct

Example:
```
User: "This should be 'Coffee & Pastries'"
Claude: "I see you already have 'Food & Dining > Coffee' with 87 transactions.
Would you like to:
1. Use the existing 'Food & Dining > Coffee' (recommended)
2. Create a new category 'Coffee & Pastries'
3. Rename the existing category to 'Coffee & Pastries'"
```

## Finding Similar Categories

When suggesting categories, use fuzzy matching:
- "Dining" matches "Food & Dining"
- "Coffee" could be under "Food & Dining > Coffee" OR "Food & Dining > Coffee Shops"
- "Gas" could be "Transportation > Gas & Fuel"

Always show the user what they already have before creating new.
```

## Skill 3: Spending Analyzer

**Directory:** `skills/spending-analyzer/`

### `SKILL.md` (Main Instructions)

```markdown
---
name: spending-analyzer
description: Analyze spending patterns, generate insights, and create custom financial reports by orchestrating fin-analyze commands. Use when user asks about spending, wants reports, needs insights, or asks analytical questions about their finances.
---

# Spending Analyzer Skill

Teach Claude how to analyze spending using fin-analyze and assemble custom reports.

> Environment: activate the venv before commands: `source .venv/bin/activate`.

## Overview

fin-analyze provides individual analysis types. Your job is to:
1. Understand what the user wants to know
2. Run the appropriate analyzer(s)
3. Assemble results into a clear narrative
4. Offer follow-up questions

## Available Analyzers

Use `--format json` for all analyzers to get structured data you can parse.

### spending-trends
Overall spending over time.
```bash
fin-analyze spending-trends --month 2025-09 --format json
```

### category-breakdown
Total spend by category.
```bash
fin-analyze category-breakdown --month 2025-09 --format json
```

### merchant-frequency
Most-visited merchants.
```bash
fin-analyze merchant-frequency --month 2025-09 --min-visits 2 --format json
```

### subscription-detect
Find recurring charges.
```bash
fin-analyze subscription-detect --period 12m --format json
```

### unusual-spending
Detect anomalies.
```bash
fin-analyze unusual-spending --month 2025-09 --sensitivity 3 --format json
```

### category-timeline
Category spending over time.
```bash
fin-analyze category-timeline --period 6m --category "Food & Dining" --format json
```

[See reference/all-analyzers.md for complete list]

## Report Assembly

When user asks for a "report", run multiple analyzers and assemble narrative.

[See examples/custom-reports.md]

## Common Queries

[See examples/common-queries.md]
```

### `examples/custom-reports.md`

```markdown
# Custom Report Assembly

## Example: Monthly Summary Report

User asks: "Give me a report for September"

Claude runs:
```bash
# 1. Get overall trends
fin-analyze spending-trends --month 2025-09 --compare --format json

# 2. Category breakdown
fin-analyze category-breakdown --month 2025-09 --compare --format json

# 3. Top merchants
fin-analyze merchant-frequency --month 2025-09 --min-visits 2 --format json

# 4. Check for unusual spending
fin-analyze unusual-spending --month 2025-09 --sensitivity 3 --format json

# 5. Active subscriptions
fin-analyze subscription-detect --month 2025-09 --format json
```

Claude assembles narrative:
```
# September 2025 Financial Report

## Summary
Total spent: $3,245.67 (↑ 12% vs August)
Transactions: 87

## Spending by Category
1. Food & Dining: $987.50 (30%)
   - Restaurants: $654.20
   - Groceries: $245.30
   - Coffee: $88.00

2. Shopping: $765.00 (24%)
   - Online: $543.00
   - Clothing: $222.00

3. Transportation: $345.00 (11%)
   ...

## Notable Patterns
⚠️ Unusual: Restaurant spending up 45% vs August
   - Spent $234.50 at "The French Place" on Sept 12
   - 3 new restaurants visited

## Active Subscriptions (8 total, $147.20/mo)
- Netflix: $15.99
- Spotify: $10.99
- Amazon Prime: $14.99
...

## Top Merchants This Month
1. Whole Foods (8 visits, $245.30)
2. Starbucks (12 visits, $88.00)
3. Shell Gas (4 visits, $156.00)
```

No need for fin-export - Claude assembles a custom report based on the data.
```

### `examples/common-queries.md`

```markdown
# Common Spending Queries

## "How much did I spend last month?"

```bash
fin-analyze spending-trends --month 2025-09 --format json
```

Parse JSON, extract total, present to user.

## "Show my spending by category this month"

```bash
fin-analyze category-breakdown --month 2025-10 --format json
```

## "Find all my subscriptions"

```bash
fin-analyze subscription-detect --period 12m --all --format json
```

## "What restaurants did I visit most in September?"

```bash
fin-analyze merchant-frequency --month 2025-09 --category "Food & Dining" --subcategory "Restaurants" --format json
```

## "Has my spending changed compared to last month?"

```bash
fin-analyze category-breakdown --month 2025-10 --compare --format json
```

Parse comparison data, highlight significant changes.

## "Show my dining spending over the last 6 months"

```bash
fin-analyze category-timeline --period 6m --category "Food & Dining" --interval month --format json
```

## "Any unusual charges this month?"

```bash
fin-analyze unusual-spending --month 2025-10 --sensitivity 3 --format json
```

## Multi-Analyzer Insights

User: "Give me insights on my spending"

Claude runs:
1. subscription-detect (find recurring charges)
2. unusual-spending (detect anomalies)
3. category-evolution (spot new spending patterns)
4. spending-patterns (identify habits by day/week)

Assembles into conversational insights:
```
Here are some interesting patterns:

💡 Subscription Update
You have 8 active subscriptions ($147.20/mo).
Two of them haven't been used in 3 months:
- Hulu ($14.99/mo)
- Premium Gym Membership ($89/mo)

⚠️ Unusual Spending
Your restaurant spending is up 45% this month.
Largest driver: "The French Place" ($234.50 on Sept 12).

📊 Weekly Pattern
You spend 3x more on weekends than weekdays.
Saturday average: $145
Weekday average: $48
```
```

### `reference/all-analyzers.md`

```markdown
# Complete Analyzer Reference

## spending-trends

Show spending trends over time.

**Flags:**
- `--show-categories` - Include top category breakdown

**Usage:**
```bash
fin-analyze spending-trends --month 2025-09 --compare --format json
```

## category-breakdown

Total spending per category.

**Flags:**
- `--min-amount <float>` - Filter out small totals

**Usage:**
```bash
fin-analyze category-breakdown --period 3m --format json
```

## merchant-frequency

Most frequently visited merchants.

**Flags:**
- `--min-visits <int>` - Minimum visit count
- `--category <name>` - Filter by category
- `--subcategory <name>` - Filter by subcategory

**Usage:**
```bash
fin-analyze merchant-frequency --month 2025-09 --category "Food & Dining" --format json
```

## category-timeline

Track category spending across time intervals.

**Flags:**
- `--interval month|quarter|year` - Rollup period
- `--category <name>` - Filter to category
- `--subcategory <name>` - Filter to subcategory
- `--top-n <int>` - Limit to recent N periods
- `--include-merchants` - Show contributing merchants

**Usage:**
```bash
fin-analyze category-timeline --period 6m --category "Food & Dining" --interval month --format json
```

## subscription-detect

Identify recurring charges.

**Flags:**
- `--all` - Include inactive subscriptions
- `--min-confidence <float>` - Confidence threshold

**Usage:**
```bash
fin-analyze subscription-detect --period 12m --all --format json
```

## unusual-spending

Detect spending anomalies.

**Flags:**
- `--sensitivity 1-5` - Detection sensitivity (1=strict, 5=loose)

**Usage:**
```bash
fin-analyze unusual-spending --month 2025-09 --sensitivity 3 --format json
```

## spending-patterns

Analyze by time patterns.

**Flags:**
- `--by day|week|date` - Grouping dimension

**Usage:**
```bash
fin-analyze spending-patterns --period 3m --by day --format json
```

## category-suggestions

Suggest category consolidations.

**Flags:**
- `--min-overlap <float>` - Minimum merchant overlap

**Usage:**
```bash
fin-analyze category-suggestions --period 6m --format json
```

## category-evolution

Track category usage changes.

**Usage:**
```bash
fin-analyze category-evolution --period 12m --compare --format json
```
```

## Implementation Strategy

### Phase 1: Create fin-import (Optional)
- [ ] Create `fin-import` CLI (simpler import without LLM coupling)
- [ ] Test with existing data (multi-file + stdin)
- [ ] Document as alternative to fin-enhance
- [ ] Note: alternatively use `fin-enhance --skip-llm` in skills

### Phase 2: Statement Processor Skill
- [ ] Create directory structure
- [ ] Write SKILL.md with progressive disclosure
- [ ] Create examples (single, batch, pipe mode)
- [ ] Add troubleshooting guide
- [ ] Test with real statements

### Phase 3: Transaction Categorizer Skill
- [ ] Write SKILL.md for interactive categorization
- [ ] Create interactive review examples
- [ ] Document pattern learning
- [ ] Build category taxonomy reference
- [ ] Test categorization workflow

### Phase 4: Spending Analyzer Skill
- [ ] Document analyzer types + flags
- [ ] Create custom report examples
- [ ] Show common query patterns
- [ ] Build insights template
- [ ] Test report assembly

### Phase 5: Integration & Polish
- [ ] Cross-link skills (statement-processor → categorizer → analyzer)
- [ ] Add skills/README.md overview
- [ ] User acceptance testing
- [ ] Documentation cleanup

### Phase 6: Write Helper (Optional but Recommended)
- [x] Decide on long-term approach for writes from skills:
  - Option A: keep using `sqlite3` for writes (simple, explicit),
  - Option B: add a tiny `fin-edit` CLI with safe subcommands, e.g.:
    - `fin-edit set-category --transaction-id <id> --category "Food & Dining" --subcategory "Coffee" --method claude:interactive --confidence 1.0`
    - `fin-edit add-merchant-pattern --pattern 'STARBUCKS%' --category "Food & Dining" --subcategory "Coffee" --confidence 0.95`
- [x] If Option B is chosen, implement and document in the skill.

## Success Criteria

- [ ] User can process statement end-to-end conversationally
- [ ] No JSON file editing required for categorization (Agent can still choose to use fin-enhance review flow when appropriate)
- [ ] Claude generates custom reports without fin-export
- [ ] Skills load progressively (not all at once)
- [ ] Each CLI tool has single clear purpose
- [ ] Workflows feel natural and conversational

## Benefits of Agent Skills Approach

1. **No duplicate LLM calls** - Claude handles categorization directly (no separate OpenAI API)
2. **Better UX** - Conversational review vs JSON file editing
3. **Flexible reports** - Custom assembly vs rigid fin-export templates
4. **Progressive disclosure** - Claude loads only needed information
5. **Composable** - Skills orchestrate existing tools in new ways
6. **Non-breaking** - All existing CLI tools remain functional and available

## Next Steps

1. ✅ Review this plan
2. (Optional) Create fin-import CLI as simpler alternative to fin-enhance
3. Implement Phase 2: statement-processor skill
4. Implement Phase 3: transaction-categorizer skill
5. Implement Phase 4: spending-analyzer skill
6. Test end-to-end workflows
7. Document and iterate

## Related Files

- Current tools: `fin_cli/*/main.py` (all remain unchanged and available)
- README: `README.md`
- To be created: `skills/` directory, optionally `fin_cli/fin_import/`
- Existing tools kept: `fin_cli/fin_enhance/`, `fin_cli/fin_export/` (remain for users/automation)
- New: `fin_cli/fin_edit/` with `set-category` and `add-merchant-pattern` (dry-run by default; use `--apply`)

## Progress Log

- 2025-10-19: Introduced `fin-edit` CLI for safe writes; added tests and wired console entry. Updated skills to prefer `fin-edit` and added venv activation note.
