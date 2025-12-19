# Portfolio Trend Workflow

## Purpose
Analyze portfolio market value over time to understand growth, drawdowns, and valuation history.

## Prerequisites
- Multiple statement imports over time (ideally monthly statements)
- `fin-analyze` on your PATH

## Quick Commands

### Basic Trend Analysis
```bash
fin-analyze portfolio-trend --period 6m --format csv
```

### Full History
```bash
fin-analyze portfolio-trend --period all --format csv
```

### Filter by Account
```bash
fin-analyze portfolio-trend --account-id 1 --period 12m --format csv
```

### With Comparison Window
```bash
fin-analyze portfolio-trend --period 6m --compare --format csv
```

## Understanding the Output

The analyzer returns a time series of portfolio values:

**Columns:**
- as_of_date: Valuation date
- total_value: Total portfolio market value
- change_pct: Percentage change from previous period (if available)

## Analysis Patterns

### Track Portfolio Growth
```bash
fin-analyze portfolio-trend --period 12m --format csv
```

Review the trend for:
- Overall growth trajectory
- Significant dips or gains
- Correlation with market events

### Compare Account Performance
```bash
# Account 1 (e.g., brokerage)
fin-analyze portfolio-trend --account-id 1 --period 6m --format csv > account1_trend.csv

# Account 2 (e.g., retirement)
fin-analyze portfolio-trend --account-id 2 --period 6m --format csv > account2_trend.csv
```

### Identify Missing Data Points
If the trend shows gaps, you may need to import additional statements:
```bash
# Check what documents have been imported
fin-query saved documents --format table
```

## Data Quality Notes

- Trend accuracy depends on consistent statement imports
- Private funds with NAV lag may show stale values (check metadata for `valuation_lag_months`)
- Missing months in the trend indicate no valuation data for that period

## Cross-Skill Transitions

- **Current allocation**: `fin-query saved allocation_by_class --format csv` (and `allocation_by_account`)
- **Concentration check**: `fin-query saved portfolio_snapshot --format csv`, sort by `market_value`, and compute weights client-side
- **Import more statements**: Follow the asset-tracker import workflow
