# Unusual Spending Detection Workflow

## Purpose
Identify spending anomalies, new merchants, and unusual patterns by having the LLM compare spending across time periods and analyze transaction data for irregularities.

## Configuration

**Workspace root:** `~/.finagent/skills/spending-analyzer`

**Choose a session slug once at the start** (e.g., `anomaly-check-20251029`) and remember it throughout the workflow.

Throughout this workflow, **`$WORKDIR`** refers to: `~/.finagent/skills/spending-analyzer/<slug>`

When executing commands, replace `$WORKDIR` with the full path using your chosen slug.

**Before starting, create the workspace directory once:**
```bash
mkdir -p $WORKDIR
```

## Data Collection

1. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```

2. Gather spending trends with comparison (analyze current vs previous period):
   ```bash
   fin-analyze spending-trends --month 2025-10 --compare --format json > $WORKDIR/spending_trends.json
   ```

3. Get category breakdown with comparison:
   ```bash
   fin-analyze category-breakdown --month 2025-10 --compare --format json > $WORKDIR/category_breakdown.json
   ```

4. Pull merchant frequency for the analysis period:
   ```bash
   fin-analyze merchant-frequency --month 2025-10 --min-visits 1 --format json > $WORKDIR/merchant_frequency.json
   ```

5. Also get merchant frequency for the comparison period (previous month):
   ```bash
   fin-analyze merchant-frequency --month 2025-09 --min-visits 1 --format json > $WORKDIR/merchant_frequency_prev.json
   ```

6. Fetch detailed transactions for both periods:
   ```bash
   fin-query saved transactions_range --param start_date=2025-10-01 --param end_date=2025-11-01 --param limit=0 --format json > $WORKDIR/transactions_current.json

   fin-query saved transactions_range --param start_date=2025-09-01 --param end_date=2025-10-01 --param limit=0 --format json > $WORKDIR/transactions_previous.json
   ```

   **If transaction files are empty or sparse:**
   - Expand the date range (try going back 2-3 years for better baseline)
   - Check what data exists: `fin-query saved recent_imports --limit 10`
   - Verify which months have data: `fin-query saved transactions_month --param month=YYYY-MM`

## Analysis Steps

1. **Load comparison data**: Read spending trends and category breakdowns from `$WORKDIR/spending_trends.json` and `$WORKDIR/category_breakdown.json`

2. **Identify anomalies**: The LLM should analyze:
   - **Spending spikes**: Categories or merchants with significant increases vs previous period
   - **New merchants**: First-time charges (appear in current but not previous period)
   - **Unusual amounts**: Merchants with charges significantly higher than their historical average
   - **Missing merchants**: Regular merchants with no charges this period (potential cancellations)
   - **Frequency changes**: Merchants with unusual visit count changes

3. **Categorize findings**: Group anomalies by type:
   - **High-priority**: Large dollar amounts, unknown merchants, suspicious patterns
   - **Medium-priority**: Seasonal variations, expected spikes (utilities, annual fees)
   - **Low-priority**: Small variances within normal ranges

4. **Provide context**: For each anomaly:
   - Calculate the dollar and percentage change
   - Show exemplar transactions from both periods
   - Suggest likely explanations (one-time purchase, seasonal, billing cycle, error)
   - Recommend actions (verify charge, dispute, budget adjustment, investigate)

5. **Cross-reference merchants**: Compare `$WORKDIR/merchant_frequency.json` with `$WORKDIR/merchant_frequency_prev.json` to identify:
   - New merchants (appear only in current)
   - Disappeared merchants (appear only in previous)
   - Frequency changes (visit count differences)

## Output Format

Present findings as a structured report:

**High-Priority Anomalies:**
- Merchant/Category
- Current spend vs Previous spend ($ and %)
- Transaction details
- Recommended action

**New Merchants:**
- Merchant name
- Amount spent
- Number of transactions
- Category

**Significant Spending Changes:**
- Category/Merchant
- Current vs Previous ($ and %)
- Likely explanation
- Action needed

**Summary:**
- Total spending change ($ and %)
- Number of anomalies by severity
- Number of new merchants
- Recommended follow-ups

## Example Output

```
High-Priority Anomalies:

1. BB Tuition Management — $63,581
   - New merchant (no previous charges)
   - Single transaction on 2025-10-15
   - Category: Education
   - Likely explanation: Annual tuition payment
   - Action: Verify charge is legitimate

2. Altum PR — $12,631 (+100% vs avg $6,315)
   - Previous: $6,315 (Sep), Current: $12,631 (Oct)
   - Increase: $6,316 (+100%)
   - Action: Confirm contract terms or invoice

Medium-Priority Changes:

3. PG&E — $231 (+45% vs Sep $159)
   - Seasonal utility spike (October heat wave)
   - Expected variation for this time of year
   - Action: Monitor next month

4. Amazon — $751 (+79% vs Sep $420)
   - Visit count: 8 (same as previous)
   - Higher average per transaction
   - Likely: Holiday shopping starting early
   - Action: Review for unnecessary purchases

New Merchants (5 total):

- Apple.com/bill — $99 (likely new subscription)
- Local Coffee Roasters — $47 (new cafe, 3 visits)
- Best Buy — $1,249 (one-time electronics purchase)

Summary:

- Total spending: $89,432 vs $25,801 prev month (+247%)
- Change driven primarily by tuition payment ($63,581)
- 12 anomalies detected (3 high-priority, 4 medium, 5 low)
- 5 new merchants
- 2 regular merchants missing this month (Costco, Target)

Recommended Actions:
1. Verify BB Tuition Management charge
2. Review Altum PR invoice
3. Investigate Apple subscription
4. Continue monitoring PG&E for seasonal patterns
```

## Cleanup

After completing the analysis, the workspace can be cleaned up:
```bash
rm -rf $WORKDIR
```

Or keep for reference if you want to retain the data files.
