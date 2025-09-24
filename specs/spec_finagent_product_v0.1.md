# Financial CLI Tools Suite - Product Specification (Revised)

## Overview
A suite of composable command-line tools for processing, analyzing, and visualizing personal financial data from bank and credit card statements. Designed to work standalone or orchestrated by AI agents like Claude Code for intelligent financial analysis.

## Core Principles
- **Privacy-first**: All processing happens locally - PDFs never leave your machine
- **Composable**: Each tool does one thing well and can be piped together
- **AI-friendly**: Designed for orchestration by Claude Code or similar agents
- **Data portability**: Import/export in standard formats (CSV, JSON, SQL, Markdown)

## Tool Specifications

### 1. `fin-extract` - Local PDF Parser

**Purpose**: Extract transaction data from bank/credit card PDF statements locally. No data is sent to cloud services.

**Usage**:
```bash
fin-enhance <csv-files...> [options]
  --stdin               Read CSV data from stdin instead of files
  --review-output <file>  Write unresolved transactions to JSON
  --apply-review <file>   Apply categorization decisions from JSON
  --confidence <0-1>      Override auto-categorization confidence threshold
  --skip-llm              Use only rules-based categorization
  --dry-run               Preview import without committing
  --force                 Skip duplicate detection safeguards
  --db <path>             Database path (default: ~/.findata/transactions.db)
  --help                  Show detailed help
```

**Examples**:
```bash
# Basic import (will remind you how many transactions still need review)
$ fin-enhance chase_july.csv

# Import and export unresolved transactions for an agent
$ fin-enhance chase_july.csv --review-output review.json

# Apply review decisions from an agent
$ fin-enhance --apply-review review_decisions.json

# Use stdin and a stricter confidence threshold
$ cat chase_july.csv | fin-enhance --stdin --confidence 0.9 --review-output review.json
```
**Review Workflow**:

Default imports categorize what they can and leave the rest uncategorized. Use `--review-output` to export unresolved transactions for an agent, then apply the agent's decisions with `--apply-review`.

```bash
# Import and export unresolved transactions for an agent
$ fin-enhance transactions.csv --review-output review.json
✓ Auto-categorized 120/127 transactions
✓ Exported 7 unresolved transactions to review.json

# review.json structure
{
  "version": "1.0",
  "generated_at": "2025-09-24T19:05:34Z",
  "review_needed": [
    {
      "type": "transaction_review",
      "id": "tx_045",
      "date": "2025-07-17",
      "merchant": "WHOLEFDS #10234",
      "amount": 127.34,
      "original_description": "WHOLEFDS #10234 BERKELEY",
      "account_id": 1,
      "suggestions": [
        {"category": "Groceries", "subcategory": "Supermarket", "confidence": 0.72},
        {"category": "Shopping", "subcategory": "General", "confidence": 0.26}
      ]
    }
  ],
  "existing_categories": {
    "Food & Dining": ["Restaurants", "Groceries", "Coffee Shops"]
  }
}

# Apply agent or human decisions
$ fin-enhance --apply-review decisions.json
✓ Applied 7 categorization decisions
✓ Updated merchant learning rules
```

Run without `--review-output` to just import; the CLI will remind you how many transactions still need decisions.

---

### 3. `fin-query` - Database Query Tool

**Purpose**: Query the financial database using SQL or pre-built queries

**Usage**:
```bash
fin-query <sql>                     Run SQL query
fin-query --saved <name>            Run saved query
fin-query --list                    List saved queries
fin-query --schema                  Show database schema
fin-query --help                    Show detailed help
```

**Help Output**:
```bash
$ fin-query --help
fin-query - Query financial database with SQL

USAGE:
  fin-query <sql-query>
  fin-query --saved <query-name>
  fin-query [options]

DESCRIPTION:
  Query the financial database using SQL or pre-built queries.
  Results output as formatted tables or TSV for piping.

OPTIONS:
  --saved <name>        Run a pre-built query
  --list                List all saved queries
  --schema              Show database schema
  --format <fmt>        Output format: table|tsv|csv|json (default: table)
  --month <YYYY-MM>     Filter by month (for saved queries)
  --limit <n>           Limit results (for saved queries)
  --db <path>           Database path (default: ~/.findata/transactions.db)
  --help                Show this help

SAVED QUERIES:
  recent                Recent transactions (--limit N)
  summary               Monthly summary (--month YYYY-MM)
  uncategorized         Transactions without categories
  spending-by-category  Total spending by category
  spending-by-day       Daily spending for a month
  merchant-frequency    Most visited merchants
  subscriptions         Recurring transactions
  new-categories        Recently created categories
  category-evolution    How categories changed over time

EXAMPLES:
  # Direct SQL
  $ fin-query "SELECT c.category, c.subcategory, SUM(t.amount) 
               FROM transactions t
               JOIN categories c ON t.category_id = c.id
               GROUP BY c.category, c.subcategory"

  # Recent transactions
  $ fin-query --saved recent --limit 10

  # Monthly summary
  $ fin-query --saved summary --month 2024-11

  # Export for processing
  $ fin-query "SELECT * FROM transactions" --format csv > all_tx.csv

  # Find expensive dining
  $ fin-query "SELECT date, merchant, amount FROM transactions t
               JOIN categories c ON t.category_id = c.id
               WHERE c.category='Dining' AND amount > 50 
               ORDER BY amount DESC"

  # View dynamic categories
  $ fin-query "SELECT * FROM categories WHERE auto_generated = 1"

DATABASE SCHEMA:
  accounts:
    id                 INTEGER PRIMARY KEY
    name               TEXT UNIQUE
    institution        TEXT
    account_type       TEXT
    created_date       TIMESTAMP
    last_import        DATE

  categories:
    id                 INTEGER PRIMARY KEY
    category           TEXT
    subcategory        TEXT
    created_date       TIMESTAMP
    transaction_count  INTEGER
    user_approved      BOOLEAN
    auto_generated     BOOLEAN

  transactions:
    id                 INTEGER PRIMARY KEY
    date               DATE
    merchant           TEXT  
    amount             DECIMAL(10,2)
    category_id        INTEGER
    account_id         INTEGER
    original_description TEXT
    import_date        TIMESTAMP
    categorization_confidence REAL
    categorization_method TEXT

  merchant_patterns:
    pattern            TEXT PRIMARY KEY
    category_id        INTEGER
    confidence         REAL
    learned_date       TIMESTAMP
    usage_count        INTEGER

EXIT CODES:
  0  Success
  1  Query error
  2  Database not found
```

---

### 4. `fin-analyze` - Analysis Engine

**Purpose**: Run complex analyses on transaction data

**Usage**:
```bash
fin-analyze <analysis-type> [options]
  --month YYYY-MM       Analyze specific month
  --period <N>m|w|d     Analyze period (3m = 3 months)
  --format text|json    Output format
  --compare             Compare to previous period
  --help                Show detailed help
```

**Help Output**:
```bash
$ fin-analyze --help
fin-analyze - Run financial analyses

USAGE:
  fin-analyze <analysis-type> [options]

DESCRIPTION:
  Run complex analyses on transaction data.
  Outputs human-readable text or JSON for further processing.

ANALYSIS TYPES:
  spending-trends       Show spending trends over time
  category-breakdown    Breakdown by spending category
  category-evolution    Track how categories evolved
  subscription-detect   Find recurring subscriptions
  unusual-spending      Detect anomalies and outliers
  merchant-frequency    Most frequently visited merchants
  spending-patterns     Analyze patterns (day of week, time of month)
  category-suggestions  Suggest category improvements

COMMON OPTIONS:
  --month YYYY-MM       Specific month (default: current)
  --period <N>m|w|d     Time period: 3m=3 months, 2w=2 weeks, 30d=30 days
  --format text|json    Output format (default: text)
  --compare             Compare to previous period
  --threshold <n>       Min amount/frequency for inclusion
  --db <path>           Database path
  --help                Show this help

ANALYSIS-SPECIFIC OPTIONS:

  spending-trends:
    --period <N>m       Number of months to analyze (default: 3m)
    --show-categories   Break down trend by category
    Example: fin-analyze spending-trends --period 6m --show-categories

  category-breakdown:
    --month YYYY-MM     Month to analyze
    --min-amount <n>    Minimum category amount to show
    --compare           Compare to previous month
    Example: fin-analyze category-breakdown --month 2024-11 --compare

  subscription-detect:
    --all               Include inactive subscriptions
    --min-confidence <n> Minimum detection confidence (0-1)
    Example: fin-analyze subscription-detect --all

  unusual-spending:
    --month YYYY-MM     Month to analyze
    --sensitivity <n>   Detection sensitivity (1-5, default: 3)
    Example: fin-analyze unusual-spending --month 2024-11 --sensitivity 4

  merchant-frequency:
    --month YYYY-MM     Month to analyze  
    --min-visits <n>    Minimum visits to include
    Example: fin-analyze merchant-frequency --month 2024-11 --min-visits 3

  spending-patterns:
    --month YYYY-MM     Month to analyze
    --by day|week|date  Group by day of week, week, or date
    Example: fin-analyze spending-patterns --by day

  category-evolution:
    --period <N>m       Period to analyze category changes
    Example: fin-analyze category-evolution --period 6m

  category-suggestions:
    --min-overlap <n>   Minimum transaction overlap for merge suggestion
    Example: fin-analyze category-suggestions --min-overlap 0.8

EXAMPLES:
  # Recent spending trend
  $ fin-analyze spending-trends --period 3m

  # Current month breakdown
  $ fin-analyze category-breakdown --compare

  # Find subscriptions
  $ fin-analyze subscription-detect

  # Category optimization
  $ fin-analyze category-suggestions

  # JSON output for processing
  $ fin-analyze category-breakdown --format json > breakdown.json

  # Unusual spending with high sensitivity
  $ fin-analyze unusual-spending --sensitivity 5

  # Track category evolution
  $ fin-analyze category-evolution --period 6m

OUTPUT FORMATS:
  text: Human-readable tables and summaries
  json: Structured data for programmatic use

EXIT CODES:
  0  Success
  1  Analysis error
  2  Insufficient data
  3  Database error
```

---

### 5. `fin-export` - Markdown Report Generator

**Purpose**: Export financial data and analyses as readable Markdown reports

**Usage**:
```bash
fin-export markdown [options]
  --month YYYY-MM        Month to export (default: current)
  --output <file>        Output file (default: stdout)
  --sections <list>      Sections to include (default: all)
  --help                 Show detailed help
```

**Examples**:
```bash
# Full monthly report
$ fin-export markdown --month 2024-11 --output november_report.md
✓ Generated November 2024 Financial Report
✓ Sections: summary, categories, subscriptions, patterns, unusual
✓ Included 8 dynamically created categories
✓ Saved to: november_report.md

# Specific sections only
$ fin-export markdown --sections summary,subscriptions > report.md

# Current month to stdout
$ fin-export markdown

# November 2024 Financial Report

## Summary
- **Total Spent**: $7,892.34
- **Transactions**: 127
- **Daily Average**: $263.08
- **vs Last Month**: ↑ 10.8%

## Spending by Category

| Category | Subcategory | Amount | Percentage | vs Oct | Status |
|----------|------------|--------|------------|--------|---------|
| Dining | Restaurants | $1,847.23 | 23.4% | ↑ 12.3% | |
| Groceries | Supermarket | $1,432.56 | 18.1% | ↓ 3.2% | |
| Transportation | Gas | $953.12 | 12.1% | ↑ 8.7% | |
| Shopping | Online | $812.34 | 10.3% | ↑ 45.6% | |
| Entertainment | Streaming | $687.23 | 8.7% | → 0.1% | |
| Home & Garden | Home Improvement | $456.78 | 5.8% | NEW | NEW |

## Active Subscriptions

### Monthly Recurring (Total: $487.23)
- **Netflix**: $15.99 (last: Nov 27)
- **Spotify Family**: $16.99 (last: Nov 1)
- **ChatGPT Plus**: $20.00 (last: Nov 10)
- **Adobe Creative**: $54.99 (last: Nov 3)

### Detected Issues
⚠️ **Price Increase**: YouTube Premium $11.99 → $13.99
✅ **New**: Disney+ started November 2024
❌ **Inactive**: Audible (last charge: August 2024)

## Unusual Spending
- **APPLE STORE**: $1,234.56 - 3.2x higher than usual
- **Dining frequency**: 45% more restaurant visits
- **New merchants**: Tesla Supercharger, Coursera

## Category Evolution
- **New this month**: 
  - Home & Garden > Home Improvement (4 transactions)
  - Health & Wellness > Alternative Medicine (3 transactions)
- **Most active**: Food & Dining (89 transactions)
- **Suggested merge**: "Coffee" → "Coffee Shops" (90% overlap)
```

**Help Output**:
```bash
$ fin-export --help
fin-export - Export financial data as Markdown reports

USAGE:
  fin-export markdown [options]

DESCRIPTION:
  Generate readable Markdown reports from financial data.
  Perfect for monthly reviews, sharing, or documentation.

OPTIONS:
  --month YYYY-MM       Month to export (default: current month)
  --output <file>       Output file (default: stdout)
  --sections <list>     Comma-separated sections to include:
                         summary - Overview and totals
                         categories - Spending by category
                         subscriptions - Recurring charges
                         patterns - Spending patterns
                         unusual - Anomalies and alerts
                         merchants - Top merchants
                         trends - Multi-month trends
                         evolution - Category evolution
                         all - Include everything (default)
  --period <N>m         Include N months of trend data
  --template <file>     Use custom Markdown template
  --db <path>           Database path
  --help                Show this help

SECTIONS EXPLAINED:
  summary:       Total spending, transaction count, daily average
  categories:    Table of spending by category with changes
  subscriptions: Active subscriptions and detected changes
  patterns:      Day-of-week and time-of-month patterns
  unusual:       Anomalies, new merchants, unusual amounts
  merchants:     Most frequently visited merchants
  trends:        Multi-month spending trends (requires --period)
  evolution:     How categories have changed over time

EXAMPLES:
  # Full report for November
  $ fin-export markdown --month 2024-11 --output nov_report.md

  # Just summary and subscriptions
  $ fin-export markdown --sections summary,subscriptions

  # Include 6-month trends
  $ fin-export markdown --period 6m --sections all

  # Pipe to other tools
  $ fin-export markdown | pandoc -o report.pdf

MARKDOWN FORMAT:
  Output uses standard Markdown with:
  - Headers (##) for sections
  - Tables for structured data
  - Lists for items
  - Emoji indicators for alerts (⚠️ ✅ ❌)

INTEGRATION WITH CLAUDE CODE:
  Claude Code can request specific sections and parse the Markdown
  for further analysis or formatting.

EXIT CODES:
  0  Success
  1  Export error
  2  No data for period
  3  Database error
```

---

## Claude Code Integration

### Role of Claude Code

Claude Code acts as the **intelligent orchestrator** that:
1. **Understands intent** from natural language requests
2. **Chains tools** together for complex workflows  
3. **Handles categorization** by processing review JSON and asking user when needed
4. **Generates insights** from analysis results
5. **Creates custom scripts** for repeated workflows

### Example Claude Code Workflows

#### Initial Setup with AI-Driven Categorization
```
User: Set up my financial tracking with these bank statements

Claude: I'll help you set up your financial tracking system. Let me start by extracting 
data from your statements.

$ ls ~/Downloads/*.pdf
Found 3 statement files:
- Chase_Statement_Nov_2024.pdf
- Amex_Statement_Oct_2024.pdf  
- BofA_Statement_Nov_2024.pdf

Let me extract the transactions locally:

$ fin-extract ~/Downloads/Chase_Statement_Nov_2024.pdf --output /tmp/chase_nov.csv
✓ Detected: Chase Freedom (Credit Card)
✓ Created account record: ID 1
✓ Extracted 127 transactions locally

$ fin-extract ~/Downloads/Amex_Statement_Oct_2024.pdf --output /tmp/amex_oct.csv
✓ Detected: American Express Gold (Credit Card)
✓ Created account record: ID 2
✓ Extracted 43 transactions locally

$ fin-extract ~/Downloads/BofA_Statement_Nov_2024.pdf --output /tmp/bofa_nov.csv
✓ Detected: Bank of America Checking
✓ Created account record: ID 3
✓ Extracted 89 transactions locally

Now I'll import them and handle categorization:

$ fin-enhance /tmp/*.csv --review-output /tmp/review.json
✓ Imported 259 transactions
✓ Auto-categorized 245 transactions (94.6%)
✓ Found 3 new category suggestions
✓ 14 transactions need review

Let me look at what needs categorization:

$ cat /tmp/review.json

I can see several items that need attention:

1. New category suggestions that look good:
   - "Home & Garden > Home Improvement" (4 transactions from Home Depot/Lowes)
   - "Health & Wellness > Gym" (3 transactions from Equinox)

2. Ambiguous transactions I need your help with:

For "VENMO *PAYMENT" for $50.00 - This could be:
   - Dining (splitting a restaurant bill)
   - Shopping (paying someone back)
   - Other transfer
   What type of expense was this Venmo payment for?

For "SQ *FARMERS MARKET" for $34.56 - Should this be:
   - Groceries (if you bought produce/food)
   - Shopping (if you bought crafts/goods)
   What did you typically buy at the farmers market?

[After getting user responses...]

$ cat > /tmp/decisions.json << 'EOF'
{
  "decisions": [
    {"id": "tx_001", "category": "Groceries", "subcategory": "Supermarket", "learn": true},
    {"id": "tx_002", "category": "Dining", "subcategory": "Fast Casual", "learn": true},
    {"id": "tx_003", "category": "Subscriptions", "subcategory": "Software", "learn": true},
    {"id": "tx_004", "category": "Dining", "subcategory": "Split Bill", "learn": false},
    {"id": "tx_005", "category": "Groceries", "subcategory": "Farmers Market", "learn": true}
  ]
}
EOF

$ fin-enhance --apply-review /tmp/decisions.json
✓ Applied 14 categorization decisions
✓ Created 3 new categories
✓ Learned 12 new categorization rules
✓ Database updated successfully

Let me generate your first financial report:

$ fin-export markdown --month 2024-11 --output ~/financial_report_nov_2024.md
✓ Generated comprehensive report with 8 dynamic categories

$ head -20 ~/financial_report_nov_2024.md
# November 2024 Financial Report

## Summary
- **Total Spent**: $7,892.34
- **Transactions**: 259  
- **Daily Average**: $263.08
- **Accounts**: Chase Freedom, Amex Gold, BofA Checking

Your financial tracking is now set up! The system has learned from your 
categorizations and will apply them automatically next time.
```

#### Monthly Review with Smart Analysis
```
User: Do my monthly financial review and find ways to save money

Claude: I'll analyze your November spending and identify savings opportunities.

$ fin-analyze spending-trends --period 3m --format json > /tmp/trends.json
$ fin-analyze category-breakdown --month 2024-11 --compare --format json > /tmp/breakdown.json
$ fin-analyze subscription-detect --format json > /tmp/subscriptions.json
$ fin-analyze unusual-spending --month 2024-11 --format json > /tmp/unusual.json
$ fin-analyze category-evolution --period 3m --format json > /tmp/evolution.json

Let me analyze the results:

$ python3 << 'EOF'
import json

with open('/tmp/breakdown.json') as f:
    breakdown = json.load(f)

with open('/tmp/subscriptions.json') as f:
    subs = json.load(f)

with open('/tmp/evolution.json') as f:
    evolution = json.load(f)
    
# Find biggest spending increases
increases = [(cat['name'], cat['amount'], cat['change_pct']) 
             for cat in breakdown['categories'] 
             if cat['change_pct'] > 10]
increases.sort(key=lambda x: x[2], reverse=True)

print("Biggest spending increases:")
for name, amount, change in increases[:3]:
    print(f"  {name}: ${amount:.2f} (+{change:.1f}%)")

# Show new categories
new_cats = evolution.get('new_categories', [])
if new_cats:
    print("\nNew spending categories this month:")
    for cat in new_cats:
        print(f"  {cat['category']} > {cat['subcategory']}: {cat['count']} transactions")

# Find unused subscriptions
unused = [s for s in subs['subscriptions'] 
          if s['status'] == 'inactive' or s['last_charge_days_ago'] > 60]

if unused:
    print("\nPotentially unused subscriptions:")
    total_waste = sum(s['amount'] for s in unused)
    for s in unused:
        print(f"  {s['name']}: ${s['amount']}/mo")
    print(f"  Potential monthly savings: ${total_waste:.2f}")
EOF

Biggest spending increases:
  Shopping: $812.34 (+45.6%)
  Dining: $1847.23 (+12.3%)
  Transportation: $953.12 (+8.7%)

New spending categories this month:
  Home & Garden > Home Improvement: 4 transactions
  Health & Wellness > Alternative Medicine: 3 transactions

Potentially unused subscriptions:
  Audible: $14.95/mo
  Paramount+: $11.99/mo
  Potential monthly savings: $26.94

Let me look deeper into your dining expenses:

$ fin-query "SELECT m.merchant, COUNT(*) as visits, SUM(t.amount) as total 
             FROM transactions t
             JOIN categories c ON t.category_id = c.id
             WHERE c.category='Dining' AND date >= '2024-11-01'
             GROUP BY merchant 
             ORDER BY total DESC 
             LIMIT 5" --format json > /tmp/top_dining.json

$ python3 << 'EOF'
import json

with open('/tmp/top_dining.json') as f:
    dining = json.load(f)
    
total_dining = sum(d['total'] for d in dining)
print("Top dining expenses (accounting for 65% of dining budget):")
for d in dining:
    pct = (d['total'] / 1847.23) * 100
    avg = d['total'] / d['visits']
    print(f"  {d['merchant']}: {d['visits']} visits, ${d['total']:.2f} total (avg ${avg:.2f})")
    
# Calculate savings potential
lunch_places = [d for d in dining if d['merchant'] in ['SWEETGREEN', 'CHIPOTLE']]
lunch_total = sum(d['total'] for d in lunch_places)
print(f"\nWeekday lunch spending: ${lunch_total:.2f}")
print(f"If you brought lunch 3 days/week: save ~${lunch_total * 0.6:.2f}/month")
EOF

Now let me check for category optimization opportunities:

$ fin-analyze category-suggestions --format json > /tmp/suggestions.json

$ python3 << 'EOF'
import json

with open('/tmp/suggestions.json') as f:
    suggestions = json.load(f)
    
if suggestions.get('merge_suggestions'):
    print("Category optimization suggestions:")
    for s in suggestions['merge_suggestions']:
        print(f"  Merge '{s['from']}' → '{s['to']}' ({s['overlap_pct']}% overlap)")
EOF

Category optimization suggestions:
  Merge 'Coffee' → 'Coffee Shops' (92% overlap)

Now let me generate a comprehensive savings plan:

$ fin-export markdown --month 2024-11 --sections all --output /tmp/review.md

$ cat >> /tmp/review.md << 'EOF'

## 💰 Savings Opportunities Identified

### Immediate Actions (Save $326/month)
1. **Cancel unused subscriptions** - $26.94/month
   - Cancel Audible (unused 3 months)
   - Cancel Paramount+ (1 login in November)

2. **Reduce dining out** - ~$250/month
   - Bring lunch 3 days/week (save ~$180)
   - Reduce weekend dining by 1 meal/week (save ~$70)

3. **Shopping awareness** - ~$50/month
   - Shopping up 45.6% month-over-month
   - Set a shopping budget alert at $500

### Category Insights
- You created 2 new spending categories this month
- Consider merging "Coffee" into "Coffee Shops" for cleaner reports
- "Home Improvement" spending is new - is this a one-time project?

### Behavioral Changes
- **Peak spending days**: Fridays and Saturdays (2.1x weekday average)
- **Suggestion**: Plan meals for these days in advance

### Annual Impact
Total potential savings: $326/month = **$3,912/year**
This could fund:
- 6 months of emergency fund additions
- Max out an IRA contribution
- A vacation fund
EOF

$ cp /tmp/review.md ~/Financial_Review_November_2024_With_Savings.md

I've completed your financial review with actionable savings opportunities.
The full report has been saved. 

Key findings:
- You could save $326/month ($3,912/year) with small changes
- Your categories are evolving - 2 new ones created this month
- Dining and shopping are your biggest opportunity areas  
- You have 2 unused subscriptions to cancel

Would you like me to:
1. Set up alerts for unusual spending
2. Create a meal planning template
3. Generate a budget based on these insights
```

### Benefits of This Architecture

1. **Privacy First**: All PDF processing happens locally
2. **Dynamic Categories**: System learns your unique spending patterns
3. **AI Assistance**: Claude Code handles complex categorization intelligently
4. **Human in Loop**: AI can defer to human when uncertain
5. **Learning System**: Gets better over time
6. **Readable Output**: Markdown reports are human and AI friendly
7. **Composable**: Tools can be used standalone or orchestrated
