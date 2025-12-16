# Asset Analyzer Reference

## Portfolio Analyzers

### allocation-snapshot
Current allocation by asset class and account.

```bash
fin-analyze allocation-snapshot --format csv
fin-analyze allocation-snapshot --as-of-date 2025-11-30 --format csv
fin-analyze allocation-snapshot --account-id 1 --format csv
fin-analyze allocation-snapshot --period 6m --compare --format csv
```

Options:
- `--as-of-date YYYY-MM-DD`: Use a specific date instead of window end
- `--account-id N`: Filter to a single account

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

### concentration-risk
Top holdings by weight with optional fee flagging.

```bash
fin-analyze concentration-risk --format csv
fin-analyze concentration-risk --top-n 10 --format csv
fin-analyze concentration-risk --highlight-fees --format csv
fin-analyze concentration-risk --as-of-date 2025-11-30 --format csv
```

Options:
- `--top-n N`: Number of holdings to show (default: 5)
- `--highlight-fees`: Flag holdings with fees > 0
- `--as-of-date YYYY-MM-DD`: Use a specific date

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
