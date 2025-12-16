# Rebalance Analysis Workflow

## Purpose
Compare current portfolio allocations to target weights and get actionable rebalance suggestions.

## Prerequisites
- Holdings imported via the asset-tracker import workflow
- Target allocations set via `portfolio_targets` table or `--target` flags
- `fin-analyze` on your PATH

## Quick Commands

### With Inline Targets
```bash
fin-analyze rebalance-suggestions \
  --target equities/US:40 \
  --target equities/intl:20 \
  --target bonds/treasury:25 \
  --target cash/sweep:15 \
  --format csv
```

### Using Database Targets
```bash
fin-analyze rebalance-suggestions --format csv
```

### For Specific Account
```bash
fin-analyze rebalance-suggestions --account-id 1 --format csv
```

## Setting Target Allocations

### Option 1: Inline Targets
Pass `--target main_class/sub_class:weight` for each bucket:

```bash
fin-analyze rebalance-suggestions \
  --target equities=60 \
  --target bonds=30 \
  --target cash=10 \
  --format csv
```

For more granular control, include sub-classes:
```bash
--target equities/US:40 --target equities/intl:20
```

### Option 2: Database Targets
Insert rows into `portfolio_targets` table:

```sql
-- Portfolio-wide targets
INSERT INTO portfolio_targets (scope, scope_id, asset_class_id, target_weight, as_of_date)
SELECT 'portfolio', NULL, id, 40.0, '2025-12-01'
FROM asset_classes WHERE main_class = 'equities' AND sub_class = 'US';
```

Or use the preference capture workflow to set targets interactively.

## Understanding the Output

**Columns:**
- main_class, sub_class: Asset class bucket
- target_pct: Target allocation percentage
- current_pct: Current allocation percentage
- delta_pct: Difference (target - current)
- delta_value: Dollar amount to buy (positive) or sell (negative)

## Analysis Patterns

### Identify Largest Gaps
Sort by `delta_value` to find the biggest rebalancing needs:
- Positive delta: Underweight, consider buying
- Negative delta: Overweight, consider selling

### Tax-Aware Rebalancing
Review holdings by account type before rebalancing:
```bash
fin-query saved allocation_by_account --format table
```

Consider:
- Sell overweight positions in tax-advantaged accounts first
- Add to underweight positions with new contributions
- Use dividends/interest to rebalance naturally

### Check Specific Holdings to Trade
```bash
fin-query saved portfolio_snapshot --format table
```

Identify specific securities in over/underweight classes.

## Common Target Frameworks

### Conservative (60/40)
```bash
--target equities=60 --target bonds=40
```

### Moderate Growth
```bash
--target equities=70 --target bonds=20 --target alternatives=10
```

### Aggressive
```bash
--target equities=85 --target bonds=10 --target cash=5
```

### Income Focus
```bash
--target bonds=50 --target equities/dividend=30 --target cash=20
```

## Cross-Skill Transitions

- **View current allocation**: `fin-analyze allocation-snapshot --format csv`
- **Check concentration**: `fin-analyze concentration-risk --format csv`
- **Set preferences**: Follow the preference capture workflow
