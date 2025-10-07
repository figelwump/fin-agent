# Declarative Extractor Schema

This document defines the YAML schema for declarative bank statement extractors. Declarative extractors allow you to define extraction rules without writing Python code, making it easier to add support for new banks and maintain existing extractors.

## Overview

A declarative extractor is a YAML file that describes:
- How to identify the bank/institution
- How to find relevant columns in PDF tables
- How to parse dates and amounts
- How to classify transactions as spend vs. credit/payment/transfer
- How to filter and clean transaction data

## Full Schema Reference

```yaml
# ============================================================================
# BASIC METADATA (Required)
# ============================================================================

name: chase                # Unique identifier for this extractor
institution: Chase         # Display name for the institution
account_type: credit       # Account type: credit, debit, checking, savings

# ============================================================================
# COLUMN MAPPING (Required)
# ============================================================================

# Define how to find required columns in PDF tables using aliases
# Matching is case-insensitive and supports partial matching
columns:
  date:
    aliases: ["transaction date", "date", "post date", "posting date"]

  description:
    aliases: ["merchant name", "description", "transaction description", "details"]

  # Simple case: single amount column
  amount:
    aliases: ["amount", "transaction amount", "total", "purchase amount"]

  # Alternative: separate debit/credit columns (BofA/Mercury pattern)
  debit:  # money out / withdrawals
    aliases:
      - "withdrawals"
      - "withdrawals and other debits"
      - "withdrawals/debits"
      - "debits"
      - "charges"
      - "money out"
      - "amount out"

  credit:  # money in / deposits
    aliases:
      - "deposits"
      - "deposits and other credits"
      - "deposits/credits"
      - "credits"
      - "money in"
      - "amount in"

  type:  # optional transaction type column
    aliases: ["type", "transaction type"]

# ============================================================================
# AMOUNT RESOLUTION (Optional)
# ============================================================================

# Only needed if you have debit/credit columns instead of a single amount column
amount_resolution:
  # Try these in order until we find a non-empty value
  priority: ["amount", "debit", "credit"]
  # Always convert to absolute value before sign classification
  take_absolute: true

# ============================================================================
# STATEMENT PERIOD EXTRACTION (Optional but recommended)
# ============================================================================

# Extract statement start/end dates for metadata and year inference
statement_period:
  patterns:
    # Pattern 1: Numeric dates (MM/DD/YYYY format)
    - regex: 'Statement Period[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|to)\s*(\d{1,2}/\d{1,2}/\d{2,4})'
      start_group: 1    # Regex capture group for start date
      end_group: 2      # Regex capture group for end date
      format: "%m/%d/%Y"  # strptime format (handles both %Y and %y)

    # Pattern 2: Long-form dates (Month DD, YYYY)
    - regex: 'Statement Period[:\s]+([A-Za-z]+\s+\d{1,2},?\s*\d{4})\s*(?:-|to)\s*([A-Za-z]+\s+\d{1,2},?\s*\d{4})'
      start_group: 1
      end_group: 2
      format: "%B %d, %Y"  # e.g., "January 15, 2024"

# ============================================================================
# DATE PARSING (Required)
# ============================================================================

dates:
  # Date formats to try in order (uses Python strptime format codes)
  formats:
    - "%m/%d/%Y"    # 01/15/2024
    - "%m/%d/%y"    # 01/15/24
    - "%Y-%m-%d"    # 2024-01-15

  # For dates without year (MM/DD), infer year from context
  infer_year:
    enabled: true
    # Source: "statement_period" or "statement_text"
    source: "statement_period"
    # If using "statement_text", provide regex to extract year
    text_pattern: "(January|February|March|April|May|June|July|August|September|October|November|December)\\s+(20\\d{2})"

  # Handle statements spanning year boundary (e.g., Dec 2024 - Jan 2025)
  year_boundary:
    enabled: true
    # If transaction month > statement month by more than this, assume prior year
    month_threshold: 1

# ============================================================================
# SIGN CLASSIFICATION (Required)
# ============================================================================

# Determine if transaction is spend (positive) or credit/payment/transfer (negative/filtered)
sign_classification:
  # Method: "keywords" | "columns" | "hybrid"
  # - keywords: use description text matching (Chase pattern)
  # - columns: use presence in debit vs credit column (if available)
  # - hybrid: try columns first, fall back to keywords (BofA/Mercury pattern)
  method: "keywords"

  # Keyword-based classification rules
  charge_keywords:
    - "sale"
    - "purchase"
    - "debit"
    - "withdrawal"
    - "ach pull"

  credit_keywords:
    - "payment"
    - "credit"
    - "adjustment"
    - "refund"
    - "deposit"
    - "ach in"
    - "transfer in"

  transfer_keywords:
    - "transfer"
    - "atm withdrawal"
    - "mercuryach"
    - "cash sending apps"

  interest_keywords:
    - "interest"

  card_payment_keywords:
    - "payment"
    - "credit card"
    - "credit crd"
    - "card services"
    - "applecard"
    - "bank of america"

  # Column-based rules (for BofA/Mercury with separate debit/credit columns)
  # If true: amount from "debit" column = positive (spend)
  #          amount from "credit" column = negative (not spend, filtered out)
  column_determines_sign: false

# ============================================================================
# TABLE-LEVEL FILTERING (Optional)
# ============================================================================

# Skip entire tables based on header content (e.g., BofA deposit-only tables)
table_filters:
  # Skip tables where ALL these conditions are true
  skip_if_all:
    - contains: ["deposit", "other additions"]
      not_contains: ["withdraw", "debit"]

# ============================================================================
# ROW-LEVEL FILTERING (Optional)
# ============================================================================

row_filters:
  # Skip rows where description exactly matches (case-insensitive)
  skip_descriptions_exact:
    - "PAYMENTS AND OTHER CREDITS"
    - "total"
    - "balance"
    - "summary"
    - "fees"
    - "transactions"
    - "transactions continued"
    - "charges and purchases"
    - "purchases and adjustments"

  # Skip rows matching these regex patterns (case-insensitive)
  skip_descriptions_pattern:
    - "^total.*"
    - ".*for this period$"
    - ".*continued on next page.*"
    - ".*continued from previous page.*"
    - "interest charged"
    - "late fee"

  # Only include spend transactions (positive after sign classification)
  # Transactions classified as credit/payment/transfer are excluded
  spend_only: true

# ============================================================================
# MULTI-LINE TRANSACTION HANDLING (Optional)
# ============================================================================

# When a row has date/description but no amount, append description to previous transaction
multiline:
  enabled: true
  append_to: "previous"  # Append to previous transaction's merchant and original_description
  # Skip appending if description matches summary/header patterns
  skip_append_if_summary: true

# ============================================================================
# MERCHANT TEXT CLEANUP (Optional)
# ============================================================================

# Remove unwanted text from merchant names
merchant_cleanup:
  remove_patterns:
    - "continued on next page"
    - "continued from previous page"
  trim: true  # Trim whitespace after cleanup

# ============================================================================
# ACCOUNT NAME INFERENCE (Optional)
# ============================================================================

# Extract specific account name from PDF text
account_name_inference:
  patterns:
    # Pattern 1: Keyword matching
    - keywords: ["amazon", "prime visa"]
      name: "Amazon Prime Visa"

    # Pattern 2: Regex matching
    - regex: 'advantage\s+banking'
      name: "BofA Advantage Checking"
      account_type: "checking"  # Can override account_type

    # Pattern 3: Regex with capture groups (for account numbers)
    - regex: '••(\d{3,4})'  # Mercury's bullet pattern
      name_template: "Mercury Checking ****{1}"  # {1} = regex group 1

  # Default name if no patterns match
  default: "Chase Account"

# ============================================================================
# DETECTION RULES (Optional)
# ============================================================================

# Rules for supports() method - determines if extractor handles this PDF
detection:
  # Must contain ALL these keywords in PDF text
  keywords_all: ["chase"]

  # Must contain at least ONE of these keywords (optional)
  keywords_any: ["account activity"]

  # Must find at least one table with mapped columns
  table_required: true

  # Table header requirements - at least one table must have these
  header_requires:
    - "date"
    - "description"
    - "amount"  # OR at least one of: amount, debit, credit
```

## Minimal Example (Chase)

Here's a minimal Chase extractor that uses most defaults:

```yaml
name: chase
institution: Chase
account_type: credit

columns:
  date:
    aliases: ["transaction date", "date", "post date"]
  description:
    aliases: ["merchant name", "description", "transaction description"]
  amount:
    aliases: ["amount", "transaction amount", "total"]
  type:
    aliases: ["type", "transaction type"]

dates:
  formats: ["%m/%d/%Y", "%m/%d/%y"]
  infer_year:
    enabled: true
    source: "statement_text"
    text_pattern: "(January|February|March|April|May|June|July|August|September|October|November|December)\\s+(20\\d{2})"
  year_boundary:
    enabled: true
    month_threshold: 1

amount_resolution:
  take_absolute: true

sign_classification:
  method: "keywords"
  charge_keywords: ["sale", "purchase", "debit"]
  credit_keywords: ["payment", "credit", "adjustment", "refund"]
  transfer_keywords: ["transfer"]
  interest_keywords: ["interest"]
  card_payment_keywords: ["payment"]

row_filters:
  skip_descriptions_exact: ["PAYMENTS AND OTHER CREDITS"]
  spend_only: true

multiline:
  enabled: true
  append_to: "previous"

detection:
  keywords_all: ["chase"]
  keywords_any: ["account activity"]
  table_required: true
```

## Implementation Notes

### Required vs. Optional Sections

**Required:**
- `name`, `institution`, `account_type`
- `columns.date`, `columns.description`, `columns.amount` (or `debit`/`credit`)
- `dates.formats`
- `sign_classification` (at minimum: `method` and appropriate keywords/rules)

**Optional but recommended:**
- `statement_period` - enables better year inference
- `row_filters.spend_only` - ensures only spend transactions are returned
- `detection` - without this, defaults to name keyword + table column matching

**Optional:**
- All other sections have sensible defaults

### Column Matching Strategy

Column aliases are matched:
1. Case-insensitively
2. With partial matching (e.g., alias "date" matches header "Transaction Date")
3. In order - first match wins

### Sign Classification Logic

The classifier determines transaction sign:
- Positive amount = spend (included in output)
- Zero or negative = credit/payment/transfer/interest (excluded when `spend_only: true`)

Classification process (method="keywords"):
1. Normalize description text
2. Check for matches in keyword sets (charge, credit, transfer, interest, card_payment)
3. Apply priority rules to determine final classification
4. Return signed amount

### Multi-line Transactions

Some PDFs split long merchant names across multiple rows:
```
Row 1: 01/15  AMAZON.COM                    45.99
Row 2:        MARKETPLACE PURCHASE
```

With `multiline.enabled: true`, Row 2 is appended to Row 1's merchant name.

### Year Inference

For dates without years (MM/DD):
1. Extract statement period if available
2. Use statement year as base
3. Apply year boundary logic for Dec-Jan transitions
4. Fall back to sequential date comparison

## Next Steps

After documenting the schema:
1. Implement `fin_cli/fin_extract/declarative.py` - runtime that reads and executes YAML specs
2. Add CLI integration for testing declarative extractors
3. Write `chase.yaml` using this schema
4. Validate against sample PDFs
