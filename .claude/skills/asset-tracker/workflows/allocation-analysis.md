# Allocation Analysis Workflow

## Purpose
View and analyze current portfolio allocation by asset class and account.

## Prerequisites
- Holdings imported via the asset-tracker import workflow
- `fin-analyze` on your PATH

## Quick Commands

### Basic Allocation Snapshot
```bash
fin-analyze allocation-snapshot --format csv
```

### With Comparison to Previous Period
```bash
fin-analyze allocation-snapshot --period 6m --compare --format csv
```

### Specific As-Of Date
```bash
fin-analyze allocation-snapshot --as-of-date 2025-11-30 --format csv
```

### Filter by Account
```bash
fin-analyze allocation-snapshot --account-id 1 --format csv
```

## Understanding the Output

The analyzer returns two tables:

**Allocation by Class:**
- main_class: Asset class (equities, bonds, alternatives, cash, other)
- sub_class: Sub-classification (US equity, intl equity, treasury, etc.)
- holding_count: Number of positions in this bucket
- instrument_count: Number of unique securities
- total_value: Market value in USD
- allocation_pct: Percentage of total portfolio

**Allocation by Account:**
- account_id, account_name, institution
- total_value: Market value held at this account
- allocation_pct: Percentage of total portfolio

## Analysis Patterns

### Compare Allocations Over Time
```bash
# Current
fin-analyze allocation-snapshot --as-of-date 2025-12-01 --format csv > allocation_current.csv

# 3 months ago
fin-analyze allocation-snapshot --as-of-date 2025-09-01 --format csv > allocation_prior.csv
```

### Check for Unclassified Holdings
Look for `main_class=unclassified` in the output. These instruments need classification mapping.

```bash
fin-query saved holdings_missing_classification --format table
```

### Verify Stale Holdings
Check if any holdings haven't been updated recently:
```bash
fin-query saved stale_holdings --format table
```

## Cross-Skill Transitions

- **View detailed holdings**: `fin-query saved portfolio_snapshot --format table`
- **Concentration risk**: Continue with `fin-analyze concentration-risk --top-n 10`
- **Rebalance suggestions**: Use `fin-analyze rebalance-suggestions --target equities=60 --target bonds=30`
