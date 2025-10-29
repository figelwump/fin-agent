# Subscription Detection Workflow

## Purpose
Identify recurring subscriptions and charges by analyzing transaction patterns using LLM reasoning over merchant frequency and transaction history.

## Configuration

**Workspace root:** `~/.finagent/skills/spending-analyzer`

**Choose a session slug once at the start** (e.g., `subscription-audit-20251029`) and remember it throughout the workflow.

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

2. Pull recurring merchant context (adjust period as needed, typically 12m for annual subscriptions):
   ```bash
   fin-analyze merchant-frequency --period 12m --min-visits 3 --format json > $WORKDIR/merchant_frequency.json
   ```

3. Fetch detailed transactions for analysis (adjust date range as needed):
   ```bash
   fin-query saved transactions_range --param start_date=2025-01-01 --param end_date=2025-10-29 --param limit=0 --format json > $WORKDIR/transactions.json
   ```

   **If transactions.json is empty or sparse:**
   - Expand the date range (try going back 2-3 years)
   - Check what data exists: `fin-query saved recent_imports --limit 10`
   - Verify which months have data: `fin-query saved transactions_month --param month=YYYY-MM`
   - For custom queries, use `fin-query sql "SELECT ..."` instead of direct sqlite3 commands

4. Optionally, get category breakdown for context:
   ```bash
   fin-analyze category-breakdown --period 12m --format json > $WORKDIR/category_breakdown.json
   ```

## Analysis Steps

1. **Load transaction data**: Read `$WORKDIR/merchant_frequency.json` and `$WORKDIR/transactions.json`

2. **Identify recurring patterns**: The LLM should analyze:
   - Merchants with regular charge intervals (monthly, quarterly, annual)
   - Consistent or predictable amounts
   - Transaction dates that form patterns (e.g., same day each month)
   - Common subscription categories (Entertainment, Utilities, Services, Software)

3. **Validate and categorize**: For each potential subscription:
   - Confirm the cadence (monthly, quarterly, annual)
   - Calculate average amount and note any variance
   - Identify latest charge date
   - Detect cancelled subscriptions (no recent charges)
   - Flag new subscriptions (started recently)

4. **Cross-reference with transaction details**: Use `$WORKDIR/transactions.json` to:
   - Pull exemplar transactions showing charge amounts and dates
   - Verify consistency of amounts over time
   - Note any irregularities or skipped periods

## Output Format

Present findings as a structured report:

**Active Subscriptions:**
- Merchant name
- Cadence (monthly/quarterly/annual)
- Average amount
- Latest charge date
- Category

**Cancelled Subscriptions:**
- Merchant name
- Last charge date
- Previous cadence

**New Subscriptions:**
- Merchant name
- First charge date
- Cadence (if established)

**Summary:**
- Total estimated monthly spend
- Total estimated annual spend
- Number of active subscriptions by category

## Example Output

```
Active Subscriptions:

Entertainment:
- Netflix — $15.49/mo (last charge 2025-10-15)
- Disney Plus — $19.32/mo (last charge 2025-10-24)
- YouTube Premium — $11.99/mo (last charge 2025-10-20)

Utilities:
- PG&E — Variable $17–64/mo (utility bill, last charge 2025-10-14)
- AT&T — $228.00/mo (last charge 2025-10-14)

Software & Services:
- GitHub — $4.00/mo (last charge 2025-10-01)

Cancelled Subscriptions:
- Hulu — Last seen 2025-04-20 ($14.99/mo)

New Subscriptions:
- Crunchyroll — Started 2025-09-15 ($7.99/mo)

Summary:
- Active subscriptions: 6
- Total monthly spend: ~$297
- Total annual spend: ~$3,564
```

## Cleanup

After completing the analysis, the workspace can be cleaned up:
```bash
rm -rf $WORKDIR
```

Or keep for reference if you want to retain the data files.
