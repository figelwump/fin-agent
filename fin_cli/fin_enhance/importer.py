"""CSV transaction importer for fin-enhance."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, TextIO

from dateutil import parser as date_parser

from fin_cli.shared.models import compute_account_key


@dataclass(slots=True)
class ImportedTransaction:
    date: date
    merchant: str
    amount: float
    original_description: str
    account_name: str
    institution: str
    account_type: str
    account_key: str
    account_id: int | None = None


REQUIRED_HEADERS = {
    "date",
    "merchant",
    "amount",
    "original_description",
    "account_name",
    "institution",
    "account_type",
}

OPTIONAL_HEADERS = {
    "account_key",
    "account_id",
}


class CSVImportError(Exception):
    """Raised when the CSV cannot be parsed."""


def load_csv_transactions_from_stream(stream: TextIO, source_name: str = "stdin") -> list[ImportedTransaction]:
    """Load transactions from a file-like object (e.g., sys.stdin).

    Args:
        stream: File-like object to read CSV from
        source_name: Name for error reporting (e.g., "stdin" or filename)

    Returns:
        List of imported transactions
    """
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise CSVImportError(f"{source_name}: CSV must include headers.")
    headers = set(reader.fieldnames)
    unsupported = headers - (REQUIRED_HEADERS | OPTIONAL_HEADERS)
    if unsupported:
        raise CSVImportError(
            f"{source_name}: Unsupported columns in CSV: " + ", ".join(sorted(unsupported))
        )
    missing_required = REQUIRED_HEADERS - headers
    if missing_required:
        raise CSVImportError(
            f"{source_name}: Missing required columns in CSV: " + ", ".join(sorted(missing_required))
        )
    transactions: list[ImportedTransaction] = []
    for idx, row in enumerate(reader, start=1):
        try:
            txn = _parse_row(row)
        except ValueError as exc:
            raise CSVImportError(f"{source_name} row {idx}: {exc}") from exc
        transactions.append(txn)
    return transactions


def load_csv_transactions(path: str | Path | None = None) -> list[ImportedTransaction]:
    """Load CSV transactions from a file or stdin.

    Args:
        path: File path, '-' for stdin, or None for stdin

    Returns:
        List of imported transactions
    """
    if path is None or path == '-':
        # Read from stdin
        return load_csv_transactions_from_stream(sys.stdin, "stdin")

    file_path = Path(path)
    if not file_path.exists():
        raise CSVImportError(f"CSV file not found: {file_path}")

    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return load_csv_transactions_from_stream(handle, str(file_path))


def _parse_row(row: dict[str, str | None]) -> ImportedTransaction:
    try:
        raw_date = (row.get("date") or "").strip()
        dt = date_parser.parse(raw_date).date()
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid date value: {row.get('date')}") from exc

    raw_amount = (row.get("amount") or "").strip()
    if not raw_amount:
        raise ValueError("Missing amount")
    amount = float(raw_amount)

    merchant = (row.get("merchant") or "").strip()
    if not merchant:
        raise ValueError("Missing merchant")

    original_description = (row.get("original_description") or merchant).strip()

    account_name = (row.get("account_name") or "").strip()
    institution = (row.get("institution") or "").strip()
    account_type = (row.get("account_type") or "").strip()
    if not account_name or not institution or not account_type:
        raise ValueError("Missing account metadata (account_name, institution, account_type)")

    account_key_value = (row.get("account_key") or "").strip()
    account_key = account_key_value or compute_account_key(account_name, institution, account_type)

    account_raw = (row.get("account_id") or "").strip()
    account_id = int(account_raw) if account_raw else None

    return ImportedTransaction(
        date=dt,
        merchant=merchant,
        amount=amount,
        original_description=original_description,
        account_name=account_name,
        institution=institution,
        account_type=account_type,
        account_key=account_key,
        account_id=account_id,
    )
