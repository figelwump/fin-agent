"""Chase-specific statement extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from ..parsers.pdf_loader import PdfDocument
from ..types import ExtractionResult, ExtractedTransaction, StatementMetadata
from .base import StatementExtractor


@dataclass(slots=True)
class _ColumnMapping:
    date_index: int
    description_index: int
    amount_index: int
    type_index: int | None = None


class ChaseExtractor(StatementExtractor):
    name = "chase"

    def supports(self, document: PdfDocument) -> bool:
        text = document.text.lower()
        if "chase" not in text:
            return False
        # Look for tables with header containing description + amount
        return any(self._find_column_mapping(table.headers) for table in document.tables)

    def extract(self, document: PdfDocument) -> ExtractionResult:
        transactions: list[ExtractedTransaction] = []
        for table in document.tables:
            mapping = self._find_column_mapping(table.headers)
            if not mapping:
                continue
            for row in table.rows:
                txn = self._parse_row(row, mapping)
                if txn:
                    transactions.append(txn)
        metadata = StatementMetadata(
            institution="Chase",
            account_name="Chase Account",
            account_type="credit",
            start_date=None,
            end_date=None,
        )
        return ExtractionResult(metadata=metadata, transactions=transactions)

    def _find_column_mapping(self, headers: Iterable[str]) -> _ColumnMapping | None:
        normalized = [header.strip().lower() for header in headers]
        date_idx = self._find_index(normalized, {"transaction date", "date", "post date"})
        desc_idx = self._find_index(normalized, {"merchant name", "description", "transaction description"})
        amount_idx = self._find_index(normalized, {"amount", "transaction amount", "total"})
        type_idx = self._find_index(normalized, {"type", "transaction type"})
        if date_idx is None or desc_idx is None or amount_idx is None:
            return None
        return _ColumnMapping(
            date_index=date_idx,
            description_index=desc_idx,
            amount_index=amount_idx,
            type_index=type_idx,
        )

    def _find_index(self, headers: list[str], targets: set[str]) -> int | None:
        for idx, header in enumerate(headers):
            if not header:
                continue
            if header in targets:
                return idx
            for target in targets:
                if target in header:
                    return idx
        return None

    def _parse_row(self, row: Iterable[str], mapping: _ColumnMapping) -> ExtractedTransaction | None:
        cells = list(row)
        try:
            date_str = cells[mapping.date_index]
            description = cells[mapping.description_index]
            amount_str = cells[mapping.amount_index]
        except IndexError:
            return None
        if not date_str or not description or not amount_str:
            return None
        try:
            txn_date = _parse_chase_date(date_str)
            amount = _parse_amount(amount_str)
        except ValueError:
            return None
        description = description.strip()
        if not description:
            return None
        type_value = (
            cells[mapping.type_index].strip().lower()
            if mapping.type_index is not None and mapping.type_index < len(cells)
            else ""
        )
        amount = _apply_charge_sign(amount, description, type_value)
        return ExtractedTransaction(
            date=txn_date,
            merchant=description,
            amount=amount,
            original_description=description,
        )


def _parse_chase_date(value: str) -> datetime.date:
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {value}")


def _parse_amount(value: str) -> float:
    cleaned = value.strip().replace(",", "")
    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    if cleaned.startswith("$"):
        cleaned = cleaned[1:]
    if not cleaned:
        raise ValueError("Empty amount")
    amount = float(cleaned)
    return -amount if negative else amount


def _apply_charge_sign(amount: float, description: str, type_value: str) -> float:
    """Convert positive amounts into expenses when appropriate."""
    normalized_desc = description.lower()
    if type_value:
        if any(keyword in type_value for keyword in {"payment", "credit"}):
            return abs(amount)
        if any(keyword in type_value for keyword in {"sale", "purchase", "debit"}):
            return -abs(amount)
    if "payment" in normalized_desc or "credit" in normalized_desc:
        return abs(amount)
    return -abs(amount)
