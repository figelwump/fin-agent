# Preference Capture Workflow

## Purpose
Capture user's target allocations, risk tolerance, and investment preferences for personalized rebalance suggestions.

## Configuration

**Preferences file:** `~/.finagent/preferences.json`

This file is gitignored and stores user preferences locally.

## Workflow

### Step 1: Ask About Investment Goals

Prompt the user to understand their situation:

```
I'd like to capture your investment preferences to provide better rebalance suggestions.

1. **Investment Horizon**: How many years until you'll need this money?
   - Short-term (0-3 years)
   - Medium-term (3-10 years)
   - Long-term (10+ years)

2. **Risk Tolerance**: How would you react to a 20% portfolio drop?
   - Sell everything (low tolerance)
   - Sell some, hold some (moderate)
   - Hold and wait (moderate-high)
   - Buy more (high tolerance)

3. **Income Needs**: Do you need income from investments?
   - Yes, living off portfolio
   - Partial, supplement other income
   - No, reinvesting everything
```

### Step 2: Suggest Target Allocation

Based on responses, suggest a target allocation framework:

**Conservative (Risk-averse, short horizon, needs income):**
```json
{
  "equities": 30,
  "bonds": 50,
  "alternatives": 5,
  "cash": 15
}
```

**Moderate (Balanced risk, medium horizon):**
```json
{
  "equities": 60,
  "bonds": 30,
  "alternatives": 5,
  "cash": 5
}
```

**Aggressive (High risk tolerance, long horizon):**
```json
{
  "equities": 80,
  "bonds": 10,
  "alternatives": 8,
  "cash": 2
}
```

**Growth (Long horizon, reinvesting):**
```json
{
  "equities": 90,
  "bonds": 5,
  "alternatives": 5,
  "cash": 0
}
```

### Step 3: Refine Sub-Class Targets

Ask about geographic and style preferences:

```
For your equity allocation, how would you like to split it?

1. **US vs International**:
   - All US (100% domestic)
   - Mostly US (70/30)
   - Balanced (60/40)
   - Global (50/50 or more international)

2. **Style Preference**:
   - Growth stocks
   - Value stocks
   - Dividend/income
   - Blend/total market

3. **Bond Preferences**:
   - Government only (treasuries)
   - Investment grade corporate
   - Mix of government and corporate
   - Include high yield
```

### Step 4: Save Preferences

Once confirmed, save to `~/.finagent/preferences.json`:

```json
{
  "version": 1,
  "updated_at": "2025-12-16T10:30:00Z",
  "profile": {
    "horizon": "long",
    "risk_tolerance": "moderate-high",
    "income_needs": "none"
  },
  "targets": {
    "portfolio": [
      {"main_class": "equities", "sub_class": "US", "weight": 45},
      {"main_class": "equities", "sub_class": "intl", "weight": 15},
      {"main_class": "bonds", "sub_class": "treasury", "weight": 20},
      {"main_class": "bonds", "sub_class": "corp IG", "weight": 10},
      {"main_class": "alternatives", "sub_class": "real estate", "weight": 5},
      {"main_class": "cash", "sub_class": "sweep", "weight": 5}
    ]
  }
}
```

### Step 5: Persist to Database

Insert targets into `portfolio_targets` table for use by `rebalance-suggestions` analyzer:

```bash
python -c "
from fin_cli.shared.database import connect
from fin_cli.shared.config import load_app_config
import json
from datetime import date

config = load_app_config()
prefs = json.load(open('$HOME/.finagent/preferences.json'))

with connect(config) as conn:
    for t in prefs['targets']['portfolio']:
        # Find asset_class_id
        row = conn.execute('''
            SELECT id FROM asset_classes
            WHERE main_class = ? AND sub_class = ?
        ''', (t['main_class'], t['sub_class'])).fetchone()

        if row:
            conn.execute('''
                INSERT OR REPLACE INTO portfolio_targets
                (scope, scope_id, asset_class_id, target_weight, as_of_date)
                VALUES ('portfolio', NULL, ?, ?, ?)
            ''', (row[0], t['weight'], date.today().isoformat()))
    conn.commit()
"
```

## Updating Preferences

To update preferences later:

1. Read current preferences from `~/.finagent/preferences.json`
2. Ask which aspects to change
3. Update the file and database
4. Verify with `fin-analyze rebalance-suggestions --format csv`

## Using Preferences

Once set, rebalance suggestions automatically use database targets:

```bash
fin-analyze rebalance-suggestions --format csv
```

To override temporarily without changing saved preferences:

```bash
fin-analyze rebalance-suggestions --target equities=70 --target bonds=20 --format csv
```

## Preferences Schema

```json
{
  "version": 1,
  "updated_at": "ISO-8601 timestamp",
  "profile": {
    "horizon": "short|medium|long",
    "risk_tolerance": "low|moderate|moderate-high|high",
    "income_needs": "living|partial|none"
  },
  "targets": {
    "portfolio": [
      {"main_class": "...", "sub_class": "...", "weight": N}
    ],
    "accounts": {
      "<account_id>": [
        {"main_class": "...", "sub_class": "...", "weight": N}
      ]
    }
  },
  "preferences": {
    "cash_cushion_months": 6,
    "rebalance_threshold_pct": 5,
    "tax_aware": true
  }
}
```
