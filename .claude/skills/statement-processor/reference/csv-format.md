# Enriched CSV Format

This reference describes the CSV schema produced after running `scripts/postprocess.py` on an LLM extraction result. The enriched CSV preserves the LLM-provided account metadata (including `last_4_digits`) and appends stable keys for idempotent imports.

## Required Columns

| Column | Type | Description | Example |
| --- | --- | --- | --- |
| `date` | `YYYY-MM-DD` | Transaction posting date. Source extracted by LLM. | `2025-09-15` |
| `merchant` | string | Normalised merchant display name. LLM should emit concise, human friendly labels. | `Amazon` |
| `amount` | decimal (positive) | Debit amount with two decimal places. Credits/refunds should be omitted upstream. | `45.67` |
| `original_description` | string | Verbatim line item from the statement. | `AMZN Mktp US*7X51S5QT3` |
| `account_name` | string | Human readable account label from the statement header. | `Chase Prime Visa` |
| `institution` | string | Issuer/bank name that owns the account. | `Chase` |
| `account_type` | enum | One of `credit`, `checking`, `savings`. | `credit` |
| `last_4_digits` | string (4 digits) | Required last four digits of the account/card number from the statement header or footer. Do not include these digits in `account_name`. | `6033` |
| `category` | string | High level category chosen from taxonomy. | `Shopping` |
| `subcategory` | string | Specific subcategory from taxonomy. | `Online Retail` |
| `confidence` | float 0–1 | LLM confidence in the classification. Keep ≤0.7 when unsure. | `0.95` |
| `account_key` | string (hash) | Stable account key derived by postprocess. Uses v2 key `compute_account_key_v2(institution, account_type, last_4_digits)`. | `a462f0d4…` |
| `fingerprint` | string (hash) | Transaction dedupe hash derived from `date`, `merchant`, `amount`, and `account_key`. Generated via `compute_transaction_fingerprint` (prefers v2 key). | `713ec84c…` |
| `source` | string | Indicates how the row was categorized: `llm_extraction`, `pattern_match`, or empty when uncategorized. | `llm_extraction` |

The LLM is responsible for the first eleven columns up to `confidence` (including `last_4_digits`). The post-processing helper appends `account_key`, `fingerprint`, and `source` to enforce idempotent imports and describe how categorization occurred.

## Optional Columns

| Column | Type | Description |
| --- | --- | --- |
| `pattern_key` | string | Deterministic lookup key used to store learned merchant patterns. Defaults to `merchant_pattern_key(merchant)` if omitted. |
| `pattern_display` | string | Human-friendly merchant display name used when storing learned patterns. Defaults to the `merchant` field. |
| `merchant_metadata` | JSON/string | Optional enrichment payload (e.g., `{ "platform": "DoorDash" }`). Parsed as JSON when valid, otherwise stored as a raw string. |

When present, these columns allow `fin-edit import-transactions --learn-patterns` to persist rules with enriched metadata. They are blank-safe: if the LLM omits them, the importer computes sensible defaults.

## Account Identification Guidance

- Preserve `account_name`, `institution`, and `account_type` exactly as shown in the statement header (minus PII masked by `fin-scrub`).
- `last_4_digits` is REQUIRED and must be exactly 4 digits (e.g., `6033`). Do not include these digits in `account_name`.
- When multiple accounts share a statement, ensure each row reflects the correct account metadata so the downstream hash is unique.
- If the LLM cannot confidently determine the account, pause and ask the user before importing.

## Derived Fields

`account_key`, `fingerprint`, and `source` are generated after the LLM step. Post-processing uses the shared helpers in `fin_cli.shared.models` to ensure parity with the existing `fin-enhance` workflow (v2 key):

```python
from fin_cli.shared import models
account_key = models.compute_account_key_v2(
    institution=institution,
    account_type=account_type,
    last_4_digits=last_4_digits,
)
fingerprint = models.compute_transaction_fingerprint(
    txn_date,
    amount,
    merchant,
    account_id=None,
    account_key=account_key,
)
```

- `account_key` encodes `(institution, account_type, last_4_digits)` to avoid drift from display-name changes.
- `fingerprint` is a SHA-256 hexdigest; Pandas/SQLite store the full string even if only a prefix is displayed in logs.
- `source` is derived from post-processing: `llm_extraction` when the LLM supplied the category, `pattern_match` when an existing merchant rule applied, or blank when uncategorized.

## Sample Row

```csv
date,merchant,amount,original_description,account_name,institution,account_type,last_4_digits,category,subcategory,confidence,account_key,fingerprint,pattern_key,pattern_display,merchant_metadata,source
2025-09-15,Amazon,45.67,"AMZN Mktp US*7X51S5QT3",Chase Prime Visa,Chase,credit,6033,Shopping,Online Retail,0.95,a462f0d49b7e83ee3f65c5c61c1f21943c4d59e94c56b2b9a7d38cfad5fb8f61,713ec84c0a6ac0040b3d3fbefd9b7f324f4bca329dd9336e1f42d9fd2826ebd6,AMAZON,Amazon,"{\"platform\":\"Online\"}",llm_extraction
```

## Quality Checklist

- Verify amounts are positive and formatted with two decimals.
- Double check that transfers, payments to the same card, and refunds are excluded.
- Ensure low-confidence rows (`confidence < 0.7`) are reviewed before import or captured in the agent conversation.
- Run `fin-edit import-transactions` only on enriched CSVs containing `last_4_digits`, `account_key`, `fingerprint`, and `source` columns; the command previews changes by default, so add `--apply` when you are satisfied. Use `--default-confidence` to fill blank confidence cells or `--no-create-categories` to abort when taxonomy entries are missing.
