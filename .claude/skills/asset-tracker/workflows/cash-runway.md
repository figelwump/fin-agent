# Cash Runway Workflow

## Purpose
Analyze cash vs non-cash allocation and calculate spending runway based on current cash holdings and historical spending patterns.

## Prerequisites
- Asset holdings imported via the asset-tracker import workflow
- Transaction history imported via statement-processor (for spending context)
- `fin-analyze` on your PATH

## Quick Commands

### Basic Cash Analysis
```bash
fin-analyze cash-mix --format csv
```

### Specific Date
```bash
fin-analyze cash-mix --as-of-date 2025-11-30 --format csv
```

## Understanding the Output

**Cash Mix Table:**
- bucket: "cash" or "non_cash"
- value: Market value in USD
- pct: Percentage of total portfolio

**Cash Holdings Table:**
- symbol: Cash instrument (e.g., SIOXX, UBS-FDIC-SWEEP)
- account: Account holding the cash
- value: Market value

**Summary Metrics:**
- Cash & equivalents total
- Cash percentage of portfolio
- Average monthly spend (from transaction history)
- Cash runway in months

## Analysis Patterns

### Evaluate Cash Cushion
The analyzer provides guidance based on cash percentage:
- **<5%**: Cash cushion is thin; consider building reserves
- **5-30%**: Normal range depending on risk tolerance
- **>30%**: Cash overweight; consider deploying to targets

### Calculate Custom Runway Scenarios
If your spending varies, manually compute runway:

```
Runway (months) = Cash Total / Expected Monthly Spend
```

For major expenses coming up, adjust the denominator accordingly.

### Check Cash Sources
Review which accounts hold cash:
```bash
fin-query sql "
  SELECT a.name, i.symbol, hv.market_value
  FROM holding_values hv
  JOIN holdings h ON h.id = hv.holding_id
  JOIN instruments i ON i.id = h.instrument_id
  JOIN accounts a ON a.id = h.account_id
  WHERE i.vehicle_type IN ('MMF', 'cash')
  ORDER BY hv.market_value DESC
" --format table
```

### Compare to Spending Trends
Cross-reference with spending analysis:
```bash
fin-analyze spending-trends --period 6m --format csv
```

This helps validate if the trailing spend used for runway is representative.

## Cash vs Emergency Fund

**Cash in portfolio** (tracked here):
- Money market funds (MMF)
- Cash sweeps (FDIC deposits)
- Treasury bills (if classified as cash)

**Emergency fund** (may be separate):
- High-yield savings accounts (usually not in brokerage statements)
- Consider tracking separately or ensuring they're imported

## Alerts and Thresholds

The analyzer flags:
- **Thin cushion (<5%)**: Risk of forced selling during downturns
- **Overweight (>30%)**: Drag on returns if markets rise

Customize thresholds based on:
- Income stability
- Upcoming major expenses
- Market outlook
- Risk tolerance

## Cross-Skill Transitions

- **Spending analysis**: `fin-analyze spending-trends --period 6m --format csv`
- **Rebalance to target cash**: `fin-analyze rebalance-suggestions --target cash=15 --format csv`
- **View all holdings**: `fin-query saved portfolio_snapshot --format table`
