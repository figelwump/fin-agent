# Custom Report Assembly

Example: Monthly Summary Report for September 2025

## Step 1: Run Analyzers

```bash
fin-analyze spending-trends --month 2025-09 --compare --format json
fin-analyze category-breakdown --month 2025-09 --compare --format json
fin-analyze merchant-frequency --month 2025-09 --min-visits 2 --format json
fin-analyze category-timeline --month 2025-09 --compare --category "Food & Dining" --format json
# For subscriptions and unusual spending, follow the LLM-based workflows:
#   $SKILL_ROOT/workflows/subscription-detection.md
#   $SKILL_ROOT/workflows/unusual-spending-detection.md
```

## Step 2: Interpret JSON Output

### spending-trends Output Example
```json
{
  "period": "2025-09",
  "total_spending": 2847.53,
  "transaction_count": 87,
  "average_transaction": 32.73,
  "comparison": {
    "previous_period": "2025-08",
    "total_change": 245.30,
    "total_change_pct": 9.4,
    "transaction_count_change": 5
  }
}
```

**Interpretation**: Total spending increased 9.4% ($245) compared to last month, with 5 more transactions.

### category-breakdown Output Example
```json
{
  "period": "2025-09",
  "categories": [
    {
      "category": "Food & Dining",
      "subcategory": "Restaurants",
      "total": 842.50,
      "count": 23,
      "percent_of_total": 29.6,
      "comparison": {"change_pct": 15.2}
    },
    {
      "category": "Shopping",
      "subcategory": "Online",
      "total": 567.89,
      "count": 12,
      "percent_of_total": 19.9,
      "comparison": {"change_pct": -5.3}
    }
  ]
}
```

**Interpretation**: Food & Dining is the largest category at 29.6% of spending, up 15.2% from last month. Shopping decreased by 5.3%.

### merchant-frequency Output Example
```json
{
  "period": "2025-09",
  "merchants": [
    {
      "merchant": "Starbucks",
      "visit_count": 12,
      "total_spent": 67.40,
      "average_per_visit": 5.62
    },
    {
      "merchant": "Amazon",
      "visit_count": 8,
      "total_spent": 423.56,
      "average_per_visit": 52.95
    }
  ]
}
```

**Interpretation**: Most frequent merchants are Starbucks (12 visits) and Amazon (8 visits).

See the workflow guides for subscription detection and unusual spending analysis (they provide step-by-step LLM-based analysis instructions and example outputs).

## Step 3: Assemble Narrative Report

Based on the JSON outputs above, create a summary like:

---

**September 2025 Spending Summary**

Total spending: $2,847.53 (↑9.4% vs August)
Transactions: 87 (↑5 vs August)

**Top Categories:**
- Food & Dining: $842.50 (29.6%, ↑15.2%)
- Shopping: $567.89 (19.9%, ↓5.3%)

**Frequent Merchants:**
- Starbucks: 12 visits, $67.40 total
- Amazon: 8 visits, $423.56 total

**Notable Items:**
- Unusual purchase: $1,249.99 at Best Buy on Sept 15
- Active subscriptions: Netflix ($15.49), YouTube Premium ($11.99)

**Analysis:**
Spending increased primarily due to higher restaurant spending (up 15%). The Best Buy purchase was a one-time electronics purchase. Subscriptions remain stable.

---
