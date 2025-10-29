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

2. Fetch all transactions for analysis (adjust date range as needed, or use a large range like 2-3 years if not specified):
   ```bash
   fin-query saved transactions_range --param start_date=2023-01-01 --param end_date=2025-10-29 --param limit=0 --format json > $WORKDIR/transactions.json
   ```

   **Tips:**
   - For focused analysis, specify a narrower range (e.g., last 3-6 months)
   - For comprehensive baseline, use 2+ years of data
   - If the file is empty, check what data exists: `fin-query saved recent_imports --limit 10`
   - Verify which months have data: `fin-query saved transactions_month --param month=YYYY-MM`
   - For custom queries, use `fin-query sql "SELECT ..."` instead of direct sqlite3 commands

## Analysis Steps

1. **Load transaction data**: Read all transactions from `$WORKDIR/transactions.json`

2. **Analyze spending patterns**: The LLM should examine the transaction history to identify:
   - **Recent spending spikes**: Merchants or categories with unusually high charges in recent periods
   - **New merchants**: First-time charges that haven't appeared before
   - **Unusual amounts**: Merchants with charges significantly higher than their historical average
   - **Missing recurring charges**: Regular merchants (subscriptions, utilities) with no recent charges
   - **Frequency anomalies**: Merchants with unusual changes in transaction frequency
   - **Large one-time charges**: Significant transactions that stand out from normal patterns

3. **Establish baselines**: For each merchant/category:
   - Calculate historical average spend and transaction frequency
   - Identify typical charge amounts and billing cycles
   - Note seasonal patterns (e.g., utilities, holiday spending)

4. **Categorize findings**: Group anomalies by priority:
   - **High-priority**: Large dollar amounts, unknown merchants, suspicious patterns, fraud indicators
   - **Medium-priority**: Seasonal variations, expected spikes (utilities, annual fees), moderate increases
   - **Low-priority**: Small variances within normal ranges, minor timing differences

5. **Provide context**: For each anomaly:
   - Calculate dollar and percentage changes from historical baseline
   - Show specific transaction examples with dates and amounts
   - Suggest likely explanations (one-time purchase, seasonal, billing cycle change, error, fraud)
   - Recommend actions (verify charge, dispute, budget adjustment, investigate further, cancel subscription)

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

1. Tuition Management — $63,581
   - New merchant (no previous charges)
   - Single transaction on 2025-10-15
   - Category: Education
   - Likely explanation: Annual tuition payment
   - Action: Verify charge is legitimate

2. Accountant — $12,631 (+100% vs avg $6,315)
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
1. Verify Tuition Management charge
2. Review accountant invoice
3. Investigate Apple subscription
4. Continue monitoring PG&E for seasonal patterns
```

## Cleanup

After completing the analysis, the workspace can be cleaned up:
```bash
rm -rf $WORKDIR
```

Or keep for reference if you want to retain the data files.