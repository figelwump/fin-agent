# Allocation Analysis Workflow

## Purpose
View and analyze current portfolio allocation by asset class and account.

## Prerequisites
- Holdings imported via the asset-tracker import workflow
- `fin-query` on your PATH

## Quick Commands

### Basic Allocation Snapshot
```bash
fin-query saved allocation_by_class --format csv
fin-query saved allocation_by_account --format csv
```

### Specific As-Of Date
```bash
fin-query saved allocation_by_class --param as_of_date=2025-11-30 --format csv
fin-query saved allocation_by_account --param as_of_date=2025-11-30 --format csv
```

### Filter by Account
```bash
fin-query saved allocation_by_class --param account_id=1 --format csv
fin-query saved allocation_by_account --format csv
```

## Understanding the Output

The saved queries return two tables:

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
fin-query saved allocation_by_class --param as_of_date=2025-12-01 --format csv > allocation_by_class_current.csv
fin-query saved allocation_by_account --param as_of_date=2025-12-01 --format csv > allocation_by_account_current.csv

# 3 months ago
fin-query saved allocation_by_class --param as_of_date=2025-09-01 --format csv > allocation_by_class_prior.csv
fin-query saved allocation_by_account --param as_of_date=2025-09-01 --format csv > allocation_by_account_prior.csv
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
- **Concentration check**: Use `fin-query saved portfolio_snapshot --format csv`, sort by `market_value`, and compute `weight_pct = market_value / total_market_value`.
- **Rebalance suggestions**: Use `fin-analyze rebalance-suggestions --target equities=60 --target bonds=30`
