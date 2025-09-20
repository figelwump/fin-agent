"""CSV transaction importer for fin-enhance."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from dateutil import parser as date_parser


@dataclass(slots=True)
class ImportedTransaction:
    date: date
    merchant: str
    amount: float
    original_description: str
    account_id: int | None


SUPPORTED_HEADERS = {
    "date",
    "merchant",
    "amount",
    "original_description",
    "account_id",
}


class CSVImportError(Exception):
    """Raised when the CSV cannot be parsed."""


def load_csv_transactions(path: str | Path) -> list[ImportedTransaction]:
    file_path = Path(path)
    if not file_path.exists():
        raise CSVImportError(f"CSV file not found: {file_path}")

    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise CSVImportError("CSV file must include headers.")
        missing = set(reader.fieldnames) - SUPPORTED_HEADERS
        if missing:
            raise CSVImportError(
                "Unsupported columns in CSV: " + ", ".join(sorted(missing))
            )
        transactions: list[ImportedTransaction] = []
        for idx, row in enumerate(reader, start=1):
            try:
                txn = _parse_row(row)
            except ValueError as exc:
                raise CSVImportError(f"Row {idx}: {exc}") from exc
            transactions.append(txn)
    return transactions


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

    account_raw = (row.get("account_id") or "").strip()
    account_id = int(account_raw) if account_raw else None

    return ImportedTransaction(
        date=dt,
        merchant=merchant,
        amount=amount,
        original_description=original_description,
        account_id=account_id,
    )
