# Single Statement Processing

Environment
- `source .venv/bin/activate`

Step 1: Extract
```bash
fin-extract ~/Downloads/chase-sept-2025.pdf --output ~/fin-data/chase-sept.csv
```

Output: CSV with 8 columns
`date,merchant,amount,original_description,account_name,institution,account_type,account_key`

Step 2: Import (choose one)
```bash
# Option A: rules-only import (if fin-import is available)
fin-import ~/fin-data/chase-sept.csv

# Option B: rules-only import with fin-enhance
fin-enhance ~/fin-data/chase-sept.csv --skip-llm
```

Step 3: Check Results
```bash
fin-query saved recent_transactions --limit 10
fin-query saved uncategorized
```

Next: Categorize
- If there are uncategorized transactions, load the `transaction-categorizer` skill.

