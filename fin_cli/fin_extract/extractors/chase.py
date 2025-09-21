"""Chase-specific statement extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Iterable

from ..parsers.pdf_loader import PdfDocument
from ..types import ExtractionResult, ExtractedTransaction, StatementMetadata
from .base import StatementExtractor


# PDF table extraction can surface section header labels as standalone rows; skip known headers here.
_SECTION_HEADER_DESCRIPTIONS = {
    "PAYMENTS AND OTHER CREDITS",
}

_CREDIT_TYPE_KEYWORDS = {
    "payment",
    "credit",
    "adjustment",
    "refund",
}

_CREDIT_DESCRIPTION_PREFIXES = (
    "automatic payment",
    "payment",
    "other credit",
    "credit balance",
)


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
        if any(self._find_column_mapping(table.headers) for table in document.tables):
            return True
        # Fallback: check for textual markers if tables were not detected
        return "account activity" in text or "account activity (continued)" in text

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

        if not transactions:
            transactions = self._extract_from_text(document.text)
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
        if description.upper() in _SECTION_HEADER_DESCRIPTIONS:
            return None
        type_value = (
            cells[mapping.type_index].strip().lower()
            if mapping.type_index is not None and mapping.type_index < len(cells)
            else ""
        )
        if _is_credit_entry(description, type_value):
            return None
        amount = _apply_charge_sign(amount, description, type_value)
        return ExtractedTransaction(
            date=txn_date,
            merchant=description,
            amount=amount,
            original_description=description,
        )

    def _extract_from_text(self, text: str) -> list[ExtractedTransaction]:
        year = _infer_statement_year(text)
        current_section: str | None = None
        transactions: list[ExtractedTransaction] = []
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            upper_line = line.upper()
            if "PAYMENTS AND OTHER CREDITS" in upper_line:
                current_section = "credit"
                continue
            if "PURCHASE" in upper_line or "PURCHASES" in upper_line:
                current_section = "purchase"
                continue
            match = _STATEMENT_LINE_RE.match(line)
            if not match:
                continue
            month, day, description, amount_str = match.groups()
            description = description.strip()
            if description.upper() in _SECTION_HEADER_DESCRIPTIONS:
                continue
            if current_section == "credit":
                continue
            if _is_credit_entry(description, current_section or ""):
                continue
            try:
                txn_date = _resolve_date(month, day, year)
                amount = _parse_amount(amount_str)
            except ValueError:
                continue
            if current_section == "purchase" and amount > 0:
                amount = -abs(amount)
            elif current_section == "credit" and amount > 0:
                amount = abs(amount)
            else:
                amount = _apply_charge_sign(amount, description, current_section or "")
            transactions.append(
                ExtractedTransaction(
                    date=txn_date,
                    merchant=description,
                    amount=amount,
                    original_description=description,
                )
            )
        return transactions


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


def _is_credit_entry(description: str, type_value: str) -> bool:
    normalized_type = (type_value or "").lower()
    if normalized_type and any(keyword in normalized_type for keyword in _CREDIT_TYPE_KEYWORDS):
        return True
    normalized_desc = description.lower()
    return any(normalized_desc.startswith(prefix) for prefix in _CREDIT_DESCRIPTION_PREFIXES)


_STATEMENT_LINE_RE = re.compile(
    r"^(\d{2})/(\d{2})\s+(.+?)\s+([-\$\(\)\d,\.]+)$"
)


def _infer_statement_year(text: str) -> int:
    month_year_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
        text,
        re.IGNORECASE,
    )
    if month_year_match:
        return int(month_year_match.group(2))
    two_digit_year = re.search(r"\b(\d{2})/(\d{2})/(\d{2})\b", text)
    if two_digit_year:
        year = int(two_digit_year.group(3))
        return 2000 + year
    return datetime.today().year


def _resolve_date(month: str, day: str, year: int) -> date:
    month_i = int(month)
    day_i = int(day)
    # Handle statements that cross year boundary (e.g., Jan statement with Dec transactions)
    if month_i == 12 and datetime.today().month == 1:
        year -= 1
    return date(year, month_i, day_i)
