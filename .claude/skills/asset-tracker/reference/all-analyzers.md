# Asset Analyzer Reference

## Portfolio Analyzers

### Allocation (via `fin-query`)
Current allocation by asset class and account.

```bash
fin-query saved allocation_by_class --format csv
fin-query saved allocation_by_account --format csv

fin-query saved allocation_by_class --param as_of_date=2025-11-30 --format csv
fin-query saved allocation_by_account --param as_of_date=2025-11-30 --format csv

fin-query saved allocation_by_class --param account_id=1 --format csv
```

Notes:
- `allocation_by_class` supports `--param as_of_date=YYYY-MM-DD` and `--param account_id=N`
- `allocation_by_account` supports `--param as_of_date=YYYY-MM-DD`

---

### portfolio-trend (aliases: asset-trend, trend)
Time-series of portfolio market value.

```bash
fin-analyze portfolio-trend --period 6m --format csv
fin-analyze portfolio-trend --period all --format csv
fin-analyze portfolio-trend --account-id 1 --format csv
```

Options:
- `--account-id N`: Filter to a single account

---

### Concentration (via `fin-query`)
Top holdings by weight (compute weights client-side).

```bash
fin-query saved portfolio_snapshot --format csv
fin-query saved portfolio_snapshot --param as_of_date=2025-11-30 --format csv
```

Recipe:
- Sort by `market_value` descending, take top N
- Compute `weight_pct = market_value / total_market_value * 100`
- Optional concentration metric: `HHI = sum((weight_pct/100)^2) * 10000`

---

### cash-mix
Cash vs non-cash split with spending runway context.

```bash
fin-analyze cash-mix --format csv
fin-analyze cash-mix --as-of-date 2025-11-30 --format csv
```

Options:
- `--as-of-date YYYY-MM-DD`: Use a specific date

---

### rebalance-suggestions
Compare allocations to targets and suggest shifts.

```bash
fin-analyze rebalance-suggestions --format csv
fin-analyze rebalance-suggestions --target equities=60 --target bonds=30 --format csv
fin-analyze rebalance-suggestions --account-id 1 --format csv
```

Options:
- `--target main/sub:pct`: Override targets inline (can be repeated)
- `--as-of-date YYYY-MM-DD`: Use a specific date
- `--account-id N`: Scope targets to a specific account

---

## Saved Queries

Asset-related saved queries for `fin-query saved`:

```bash
# Core portfolio views
fin-query saved portfolio_snapshot --format table
fin-query saved holding_latest_values --format table
fin-query saved allocation_by_class --format table
fin-query saved allocation_by_account --format table

# Data quality
fin-query saved stale_holdings --format table
fin-query saved holdings_missing_classification --format table

# Lookups
fin-query saved instruments --format table
fin-query saved asset_classes --format table
fin-query saved holding_history --format table
fin-query saved documents --format table
fin-query saved accounts --format table
```

---

## Common Flags

All analyzers support:
- `--period Nm|Nq|Ny|all`: Time window (e.g., `6m`, `1y`, `all`)
- `--month YYYY-MM`: Specific month
- `--compare`: Add comparison to previous period
- `--format csv|json|table`: Output format (prefer csv for skills)
