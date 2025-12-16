---
name: asset-tracker
description: Extract and import investment/brokerage statement holdings into the asset tracking database. Use when asked to import asset statements, track portfolio holdings, extract positions from PDF statements, view allocations, analyze portfolio trends, get rebalance suggestions, or assess cash runway.
allowed-tools: Bash, Read, Grep, Glob
---

# Asset Tracker Skill

Extract holdings from investment statements (UBS, Schwab, Fidelity, etc.) and import them into the asset tracking database.

## Configuration

**Resource root (do not `cd` here):** `$SKILL_ROOT` = `.claude/skills/asset-tracker`

**Workspace root:** `~/.finagent/skills/asset-tracker`

**Choose a session slug once at the start** (e.g., `ubs-nov-2025`) and remember it throughout the workflow.

Throughout this workflow, **`$WORKDIR`** refers to: `~/.finagent/skills/asset-tracker/<slug>`

Prerequisites:
- Install the `fin-cli` package so `fin-scrub`, `fin-edit`, `fin-query` commands are on your `PATH`.
- Scripts must be run with the project venv Python (`.venv/bin/python`) or ensure `fin-cli` is installed in your active environment.

## Workflow (Sequential Loop)

Process statements one at a time. For each PDF, run the full loop before touching the next file.

**Before starting, create the workspace directory once:**
```bash
mkdir -p $WORKDIR
```

### Steps

0. **Ensure the account exists** (if importing to a new account):
```bash
# Check existing accounts
fin-query saved accounts --format table

# If needed, create the account manually via SQL or let statement-processor create it
# The account_key in the JSON must match an existing account name
```

1. **Scrub sensitive data into the workspace:**
```bash
fin-scrub statement.pdf --output-dir $WORKDIR
```

   > **Note:** If `fin-scrub` errors or returns garbled text, check if it's a scanned PDF (may need OCR) or contact user for a different format.

2. **Build the extraction prompt:**
```bash
python $SKILL_ROOT/scripts/preprocess.py \
  --workdir $WORKDIR \
  --input $WORKDIR/<file>-scrubbed.txt
```

   This generates a prompt with:
   - Asset class taxonomy from the database
   - Existing instruments for symbol matching
   - The scrubbed statement text

3. **Send the prompt to your LLM** and save the JSON response to `$WORKDIR/<filename>-raw.json`.

   The LLM should output JSON matching this structure:
   ```json
   {
     "document": {"broker": "UBS", "as_of_date": "2025-11-28"},
     "instruments": [...],
     "holdings": [...],
     "holding_values": [...]
   }
   ```

4. **Validate and enrich the extracted data:**
```bash
python $SKILL_ROOT/scripts/postprocess.py \
  --workdir $WORKDIR \
  --document-path $WORKDIR/<file>-scrubbed.txt \
  --auto-classify --verbose
```

   This:
   - Validates the JSON structure against the asset contract
   - Computes document_hash for idempotent imports
   - Auto-classifies instruments (equities, bonds, alternatives, cash)
   - Writes enriched JSON to `$WORKDIR/<filename>-enriched.json`

5. **Import validated data** (preview first, then apply):
```bash
# Preview
fin-edit asset-import --from $WORKDIR/<file>-enriched.json

# Apply
fin-edit --apply asset-import --from $WORKDIR/<file>-enriched.json
```

6. **Verify the import:**
```bash
# Check holdings and values were created
fin-query saved portfolio_snapshot --limit 20 --format table

# Check latest values only
fin-query saved holding_latest_values --limit 20 --format table

# Check allocation breakdown
fin-query saved allocation_by_class --format table
```

7. **If any command fails**, resolve the issue before moving to the next statement.

## JSON Contract (LLM Output)

The LLM must output JSON with these exact keys:

### document
```json
{
  "broker": "UBS",
  "as_of_date": "2025-11-28"
}
```

### instruments (one per unique security)
```json
{
  "name": "Salesforce, Inc.",
  "symbol": "CRM",
  "currency": "USD",
  "vehicle_type": "stock",
  "identifiers": {"cusip": "79466L302"},
  "metadata": {}
}
```

Vehicle types: `stock`, `ETF`, `MMF`, `bond`, `fund_LP`, `note`, `option`, `crypto`

### holdings (one per account+instrument)
```json
{
  "account_key": "UBS-Y7-01487-28",
  "symbol": "CRM",
  "status": "active",
  "position_side": "long",
  "cost_basis_total": 61195.77,
  "metadata": {}
}
```

### holding_values (one per holding per statement date)
```json
{
  "account_key": "UBS-Y7-01487-28",
  "symbol": "CRM",
  "as_of_date": "2025-11-28",
  "quantity": 6260.0,
  "price": 230.54,
  "market_value": 1443180.40,
  "source": "statement",
  "metadata": {"unrealized_gain_loss": 1381984.63}
}
```

## Working Directory

- All files (scrubbed statements, prompts, raw JSON, enriched JSON) stored flat in `$WORKDIR`
- Clean up the workspace once import is committed

## Common Security Types

| Type | vehicle_type | Examples |
|------|--------------|----------|
| Individual stocks | `stock` | AAPL, CRM, MSFT |
| ETFs | `ETF` | ACWI, VIG, SPY |
| Money market funds | `MMF` | SIOXX, SWVXX |
| Cash/sweep/FDIC | `MMF` | FDIC deposits, sweep accounts |
| Private equity | `fund_LP` | Canyon, SL Partners, iCapital funds |
| BDCs | `fund_LP` | Apollo Debt Solutions, Carlyle |
| Non-traded REITs | `fund_LP` | BREIT, Blackstone REIT |
| Gold/commodities | `note` | Gold bullion |
| Options | `option` | Calls, puts |
| Bonds | `bond` | Treasuries, corporates |

## Special Cases

### Private Funds with NAV Lag
Many private funds report quarterly NAV with 1-6 month lag. Include in metadata:
```json
"metadata": {
  "valuation_lag_months": 5,
  "nav_as_of": "2025-06-30",
  "valuation_type": "issuer_estimate"
}
```

### Short Positions (Written Options)
Use `position_side: "short"` with positive quantity:
```json
{
  "symbol": "CRM-C-360-2026-01-16",
  "position_side": "short",
  "quantity": 13.0,
  "price": 18.0,
  "market_value": 234.0
}
```

### Fractional Shares
Preserve full precision (6+ decimals):
```json
"quantity": 126278.077
```

### Synthetic Symbols
For securities without standard tickers:
- Private funds: `CANYON-DOF-III`, `K5-ICAPITAL`
- Cash sweeps: `UBS-FDIC-SWEEP`
- Options: `CRM-C-360-2026-01-16` (underlying-type-strike-expiry)
- Gold: `GOLD-UBS-OZ`

## Handling Transfers

When assets move between custodians (e.g., transferring shares from UBS to Schwab), the system can detect and handle this.

### Automatic Detection

During postprocess (step 4), the system checks if any instruments in the payload already have active holdings at different accounts. If detected, you'll see:

```
⚠️  Potential transfers detected:

  CRM (Salesforce, Inc.)
    Currently active at: UBS-Y7-01487-28
    Now appearing at: Schwab-1234

    Suggested command:
      fin-edit --apply holdings-transfer --symbol CRM --from "UBS-Y7-01487-28" --to "Schwab-1234" --carry-cost-basis
```

### Manual Transfer Command

To transfer a holding between accounts:

```bash
# Preview the transfer
fin-edit holdings-transfer \
  --symbol CRM \
  --from "UBS-Y7-01487-28" \
  --to "Schwab-1234" \
  --transfer-date 2025-12-01 \
  --carry-cost-basis

# Execute the transfer
fin-edit --apply holdings-transfer \
  --symbol CRM \
  --from "UBS-Y7-01487-28" \
  --to "Schwab-1234" \
  --transfer-date 2025-12-01 \
  --carry-cost-basis
```

This:
1. Closes the source holding (`status='closed'`, `closed_at=transfer_date`)
2. Creates a new holding at the destination (`status='active'`, `opened_at=transfer_date`)
3. Optionally carries cost basis from source to destination (`--carry-cost-basis`)

### Viewing Closed Holdings

By default, queries only show active holdings. To see closed holdings:

```bash
# Show only closed holdings
fin-query saved holding_latest_values -p status=closed --format table

# Show all holdings (active and closed)
fin-query saved holding_latest_values -p status=null --format table
```

## Database Commands

```bash
# Import assets from JSON
fin-edit --apply asset-import --from <file.json>

# Query holdings
fin-query saved portfolio_snapshot --limit 50 --format table
fin-query saved holding_latest_values --format csv
fin-query saved allocation_by_class --format table
fin-query saved stale_holdings --format table

# Check instruments
fin-query saved instruments --limit 50 --format table
```

## Rollback/Cleanup

To remove a bad import:
```bash
# Delete by document hash
fin-edit documents delete --hash <sha256>
```

This cascades to remove associated holding_values.

## Analysis Workflows

After importing statements, use these workflows to analyze your portfolio.

### Running Analysis in Parallel

**When asked to analyze assets or provide a portfolio overview**, run these commands in parallel using multiple Bash tool calls in a single response (not sequentially):

```
# Run ALL of these in parallel (single response with multiple tool calls):
fin-analyze allocation-snapshot --format csv
fin-analyze concentration-risk --top-n 10 --format csv
fin-analyze cash-mix --format csv
fin-analyze portfolio-trend --period 6m --format csv
fin-query saved portfolio_snapshot --limit 30 --format table
fin-query saved stale_holdings --format table
```

These commands are independent and can execute concurrently. Running them in parallel significantly reduces response time.

### Individual Analysis Commands

#### View Allocation
See current allocation by asset class and account:
```bash
fin-analyze allocation-snapshot --format csv
```
Detailed workflow: `$SKILL_ROOT/workflows/allocation-analysis.md`

#### Portfolio Trend
Track portfolio value over time:
```bash
fin-analyze portfolio-trend --period 6m --format csv
```
Detailed workflow: `$SKILL_ROOT/workflows/portfolio-trend.md`

#### Rebalance Suggestions
Compare allocations to targets:
```bash
fin-analyze rebalance-suggestions --target equities=60 --target bonds=30 --format csv
```
Detailed workflow: `$SKILL_ROOT/workflows/rebalance-analysis.md`

#### Cash Runway
Analyze cash vs non-cash split with spending context:
```bash
fin-analyze cash-mix --format csv
```
Detailed workflow: `$SKILL_ROOT/workflows/cash-runway.md`

#### Concentration Risk
Identify top holdings and fee drag:
```bash
fin-analyze concentration-risk --top-n 10 --format csv
```

### Set Investment Preferences
Capture target allocations and risk profile:
Detailed workflow: `$SKILL_ROOT/workflows/preference-capture.md`

Preferences are stored in `~/.finagent/preferences.json` and persisted to the `portfolio_targets` database table for use by `rebalance-suggestions`.

## Reference

- All asset analyzers: `$SKILL_ROOT/reference/all-analyzers.md`

## Cross-Skill Transitions

- **After import**: Use `spending-analyzer` to correlate cash positions with spending patterns
- **For transactions**: Use `statement-processor` skill for bank/credit card statements
- **For queries**: Use `ledger-query` skill for transaction lookups

## Available Commands

- `fin-scrub`: Sanitize PDFs to redact PII
- `python $SKILL_ROOT/scripts/preprocess.py`: Build extraction prompts with taxonomy context
- `python $SKILL_ROOT/scripts/postprocess.py`: Validate/enrich LLM output, auto-classify instruments, detect transfers
- `fin-edit asset-import --from <file.json>`: Validate and import asset JSON payloads
- `fin-edit holdings-transfer`: Transfer holdings between accounts (closes source, creates destination)
- `fin-query saved <query>`: Query asset data (use `portfolio_snapshot`, `holding_latest_values`, `allocation_by_class`, etc.)

## Common Errors

- **Invalid JSON structure**: Use `--validate-only` flag in postprocess.py to check structure
- **Missing required fields**: Ensure all instruments have `name`, `currency`; all holdings have `account_key`, `symbol`
- **Document hash collision**: Statement already imported (idempotent protection)
- **Unknown vehicle_type**: Use one of: stock, ETF, MMF, bond, fund_LP, note, option, crypto
- **Quantity/price/market_value mismatch**: Ensure market_value ≈ quantity × price (with tolerance)
