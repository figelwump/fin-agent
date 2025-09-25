# fin-analyze JSON Schema Overview

All analyzers return a canonical JSON envelope when invoked with `--format json`.
The payload has three top-level fields:

- `title` *(string)* – Human-readable name of the analysis.
- `summary` *(array of strings)* – Narrative bullet points produced by the analyzer.
- `tables` *(array)* – Structured tabular data suitable for rendering.
- `payload` *(object)* – Analyzer-specific data, matching the schemas below.

Each entry in `tables` contains:

```json
{
  "name": "table identifier",
  "columns": ["column name", "..."],
  "rows": [["row value", 1.23], ["..."], ...],
  "metadata": {"unit": "USD"}
}
```

## Analyzer Payloads

### Spending Trends
```json
{
  "window": {"label": "month_2025_08", "start": "2025-08-01", "end": "2025-09-01"},
  "total_spend": 1234.56,
  "monthly": [
    {"month": "2025-06", "spend": 987.65, "change_pct": null},
    {"month": "2025-07", "spend": 1100.10, "change_pct": 0.1145}
  ],
  "comparison": {
    "total_spend": 987.65,
    "change_pct": 0.249,
    "window_label": "preceding_month_2025_08"
  },
  "options": {"show_categories": true},
  "threshold": 0.1,
  "trend_slope": 45.67,
  "category_breakdown": [
    {"category": "Shopping", "subcategory": "Online", "spend": 456.78, "pct_of_total": 0.37}
  ]
}
```

### Category Breakdown
```json
{
  "window": {...},
  "threshold": 0.1,
  "total_spend": 789.01,
  "categories": [
    {
      "category": "Food & Dining",
      "subcategory": "Restaurants",
      "spend": 321.45,
      "income": 0.0,
      "transaction_count": 12,
      "pct_of_total": 0.41,
      "change_pct": 0.121
    }
  ],
  "comparison": {"total_spend": 654.32}
}
```

### Category Evolution
```json
{
  "window": {...},
  "new_categories": [{"category": "Coffee", "subcategory": "Specialty", "transactions": 4, "spend": 48.0}],
  "dormant_categories": [{"category": "Travel", "subcategory": "Flights", "transactions": 2, "spend": 420.0}],
  "changes": [
    {
      "category": "Food & Dining",
      "subcategory": "Restaurants",
      "transactions_current": 15,
      "transactions_previous": 9,
      "spend_current": 350.0,
      "spend_previous": 210.0,
      "spend_change_pct": 0.6667,
      "transaction_change_pct": 0.6667
    }
  ],
  "threshold": 0.1
}
```

### Subscription Detection
```json
{
  "window": {...},
  "threshold": 0.05,
  "subscriptions": [
    {
      "merchant": "NETFLIX",
      "average_amount": 19.99,
      "total_amount": 19.99,
      "occurrences": 1,
      "cadence_days": 30.0,
      "status": "active",
      "confidence": 0.92,
      "change_pct": 0.25,
      "notes": "price +25.0%"
    }
  ],
  "new_merchants": [{"merchant": "DISNEY+", "average_amount": 13.99, "occurrences": 1}],
  "price_increases": [{"merchant": "NETFLIX", "change_pct": 0.25, "previous_average": 15.99, "current_average": 19.99}],
  "cancelled": [{"merchant": "HULU", "last_seen": "2025-07-10", "average_amount": 11.99}]
}
```

### Unusual Spending
```json
{
  "window": {...},
  "threshold_pct": 0.15,
  "sensitivity": 3,
  "anomalies": [
    {
      "merchant": "AMAZON",
      "spend": 325.0,
      "baseline_spend": 110.0,
      "spend_change_pct": 1.9545,
      "visits": 3,
      "baseline_visits": 2,
      "visit_change_pct": 0.5,
      "notes": "spend +195.5%"
    }
  ],
  "new_merchants": ["TESLA SUPERCHARGER"]
}
```

### Merchant Frequency
```json
{
  "window": {...},
  "min_visits": 2,
  "filter": {"category": "Shopping", "subcategory": null},
  "merchants": [
    {
      "canonical": "AMAZON",
      "merchant": "Amazon",
      "visits": 3,
      "total_spend": 325.0,
      "average_spend": 108.33,
      "previous_visits": 2,
      "previous_spend": 80.0,
      "change_pct": 1.0625,
      "notes": "spend +106.3%"
    }
  ],
  "new_merchants": ["TESLA SUPERCHARGER"],
  "dropped_merchants": ["TARGET"]
}
```

### Category Timeline
```json
{
  "window": {...},
  "interval": "month",
  "filter": {"category": "Shopping", "subcategory": null},
  "intervals": [
    {
      "interval": "2025-06",
      "start": "2025-06-01",
      "end": "2025-07-01",
      "spend": 420.0,
      "income": 0.0,
      "net": -420.0,
      "transaction_count": 5,
      "cumulative_spend": 1140.0
    }
  ],
  "totals": {
    "spend": 1560.0,
    "income": 0.0,
    "net": -1560.0,
    "intervals": 4
  },
  "metadata": {"top_n": 3, "table_intervals": 3},
  "comparison": {
    "spend": 1200.0,
    "intervals": 4,
    "change_pct": 0.3
  },
  "merchants": {
    "canonical": ["AMAZON", "TARGET"],
    "display": ["Amazon", "Target"]
  }
}
```

### Spending Patterns
```json
{
  "window": {...},
  "group_by": "day",
  "patterns": [
    {"label": "Monday", "spend": 120.0, "visits": 2, "comparison_spend": 40.0, "comparison_visits": 1},
    {"label": "Tuesday", "spend": 95.0, "visits": 1, "comparison_spend": 55.0, "comparison_visits": 1}
  ]
}
```

### Category Suggestions
```json
{
  "window": {...},
  "min_overlap": 0.8,
  "suggestions": [
    {
      "from": "Coffee > General",
      "to": "Coffee Shops > Specialty",
      "overlap_pct": 90.0,
      "shared_merchants": 3,
      "from_spend": 62.5,
      "to_spend": 65.0
    }
  ]
}
```

> All numeric percentages are expressed as decimals in the payload (e.g., `0.25` equals 25%). Table rows retain raw values for downstream formatting.
