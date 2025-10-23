"""CSV parsing helpers shared across CLIs."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, TextIO

from fin_cli.shared import models


class CSVImportError(Exception):
    """Raised when the CSV cannot be parsed."""


_REQUIRED_ENRICHED_COLUMNS = {
    "date",
    "merchant",
    "amount",
    "original_description",
    "account_name",
    "institution",
    "account_type",
    "category",
    "subcategory",
}

_OPTIONAL_ENRICHED_COLUMNS = {
    "confidence",
    "account_key",
    "account_id",
    "fingerprint",
    "method",
    "categorization_method",
    "pattern_key",
    "pattern_display",
    "merchant_metadata",
}


@dataclass(slots=True)
class EnrichedCSVTransaction:
    date: date
    merchant: str
    amount: float
    original_description: str
    account_name: str
    institution: str
    account_type: str
    category: str
    subcategory: str
    confidence: float
    account_key: str
    fingerprint: str
    account_id: int | None = None
    method: str | None = None
    pattern_key: str | None = None
    pattern_display: str | None = None
    merchant_metadata: Mapping[str, Any] | str | None = None


def _normalise_whitespace(text: str) -> str:
    return " ".join(text.strip().split())


def _parse_float(value: str, *, field: str) -> float:
    try:
        amount = float(value)
    except ValueError as exc:
        raise CSVImportError(f"Invalid {field} value '{value}'") from exc
    if field == "confidence":
        if amount < 0:
            return 0.0
        if amount > 1:
            return 1.0
    return amount


def _parse_enriched_row(
    row: dict[str, str | None],
    *,
    source_name: str,
    default_confidence: float,
) -> EnrichedCSVTransaction:
    missing = [col for col in _REQUIRED_ENRICHED_COLUMNS if col not in row or (row[col] is None)]
    if missing:
        raise CSVImportError(
            f"{source_name}: Missing required column(s): {', '.join(sorted(missing))}"
        )

    try:
        txn_date = date.fromisoformat((row["date"] or "").strip())
    except Exception as exc:
        raise CSVImportError(f"{source_name}: Invalid date '{row.get('date')}'") from exc

    merchant = _normalise_whitespace(row["merchant"] or "")
    if not merchant:
        raise CSVImportError(f"{source_name}: Merchant is required")

    try:
        amount = float((row["amount"] or "").strip())
    except Exception as exc:
        raise CSVImportError(f"{source_name}: Invalid amount '{row.get('amount')}'") from exc
    if amount < 0:
        amount = -amount

    original_description = (row.get("original_description") or merchant).strip()
    account_name = (row.get("account_name") or "").strip()
    institution = (row.get("institution") or "").strip()
    account_type = (row.get("account_type") or "").strip().lower()
    category = (row.get("category") or "").strip()
    subcategory = (row.get("subcategory") or "").strip()

    # Account fields are required, but category/subcategory can be empty (uncategorized transactions)
    if not all([account_name, institution, account_type]):
        raise CSVImportError(
            f"{source_name}: Missing required account fields for merchant '{merchant}'"
        )

    raw_conf = (row.get("confidence") or "").strip()
    confidence = (
        _parse_float(raw_conf, field="confidence")
        if raw_conf
        else max(0.0, min(1.0, default_confidence))
    )

    account_key = (row.get("account_key") or "").strip()
    if not account_key:
        account_key = models.compute_account_key(account_name, institution, account_type)

    fingerprint = (row.get("fingerprint") or "").strip()
    if not fingerprint:
        fingerprint = models.compute_transaction_fingerprint(
            txn_date,
            amount,
            merchant,
            None,
            account_key,
        )

    account_id_value = (row.get("account_id") or "").strip()
    account_id = int(account_id_value) if account_id_value else None

    method = (row.get("categorization_method") or row.get("method") or "").strip() or None

    pattern_key = (row.get("pattern_key") or "").strip() or None
    pattern_display = (row.get("pattern_display") or "").strip() or None

    merchant_metadata: Mapping[str, Any] | str | None = None
    metadata_raw = row.get("merchant_metadata")
    if metadata_raw is not None:
        metadata_text = (metadata_raw or "").strip()
        if metadata_text:
            try:
                merchant_metadata = json.loads(metadata_text)
            except json.JSONDecodeError:
                merchant_metadata = metadata_text

    return EnrichedCSVTransaction(
        date=txn_date,
        merchant=merchant,
        amount=amount,
        original_description=original_description,
        account_name=account_name,
        institution=institution,
        account_type=account_type,
        category=category,
        subcategory=subcategory,
        confidence=confidence,
        account_key=account_key,
        fingerprint=fingerprint,
        account_id=account_id,
        method=method,
        pattern_key=pattern_key,
        pattern_display=pattern_display,
        merchant_metadata=merchant_metadata,
    )


def load_enriched_transactions_from_stream(
    stream: TextIO,
    *,
    source_name: str,
    default_confidence: float = 1.0,
) -> list[EnrichedCSVTransaction]:
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise CSVImportError(f"{source_name}: CSV must include headers.")

    headers = {header.strip() for header in reader.fieldnames if header is not None}
    missing_columns = _REQUIRED_ENRICHED_COLUMNS - headers
    if missing_columns:
        raise CSVImportError(
            f"{source_name}: Missing required column(s): {', '.join(sorted(missing_columns))}"
        )

    unsupported = headers - (_REQUIRED_ENRICHED_COLUMNS | _OPTIONAL_ENRICHED_COLUMNS)
    if unsupported:
        raise CSVImportError(
            f"{source_name}: Unsupported column(s): {', '.join(sorted(unsupported))}"
        )

    transactions: list[EnrichedCSVTransaction] = []
    for index, row in enumerate(reader, start=2):
        transactions.append(
            _parse_enriched_row(
                row,
                source_name=f"{source_name} row {index}",
                default_confidence=default_confidence,
            )
        )
    return transactions


def load_enriched_transactions(
    path: str | Path,
    *,
    default_confidence: float = 1.0,
) -> list[EnrichedCSVTransaction]:
    if str(path) == "-":
        import sys

        return load_enriched_transactions_from_stream(
            sys.stdin,
            source_name="stdin",
            default_confidence=default_confidence,
        )

    csv_path = Path(path)
    if not csv_path.exists():
        raise CSVImportError(f"CSV file not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return load_enriched_transactions_from_stream(
            handle,
            source_name=str(csv_path),
            default_confidence=default_confidence,
        )


__all__ = [
    "CSVImportError",
    "EnrichedCSVTransaction",
    "load_enriched_transactions",
    "load_enriched_transactions_from_stream",
]
