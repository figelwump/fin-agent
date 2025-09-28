"""Mercury business checking statement extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Iterable

from ..parsers.pdf_loader import PdfDocument
from ..types import ExtractionResult, ExtractedTransaction, StatementMetadata
from .base import StatementExtractor


@dataclass(slots=True)
class _ColumnMapping:
    date_index: int
    description_index: int
    amount_index: int | None = None
    money_in_index: int | None = None
    money_out_index: int | None = None


@dataclass(slots=True)
class _StatementPeriod:
    start_date: date | None
    end_date: date | None

    def infer_year(self, month: int) -> int:
        if self.start_date and self.end_date:
            if self.start_date.month <= self.end_date.month:
                if self.start_date.month <= month <= self.end_date.month:
                    return self.start_date.year
                return self.end_date.year
            if month >= self.start_date.month:
                return self.start_date.year
            return self.end_date.year
        if self.end_date:
            return self.end_date.year
        if self.start_date:
            return self.start_date.year
        return datetime.today().year


_PERIOD_RE = re.compile(
    r"Statement Period[:\s]+([A-Za-z]+\s+\d{1,2},?\s*\d{4})\s*(?:-|to)\s*([A-Za-z]+\s+\d{1,2},?\s*\d{4})",
    re.IGNORECASE,
)

_PERIOD_NUMERIC_RE = re.compile(
    r"Statement Period[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|to)\s*(\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

_SUMMARY_KEYWORDS = {"total", "balance", "summary"}


class MercuryExtractor(StatementExtractor):
    name = "mercury"

    def supports(self, document: PdfDocument) -> bool:
        text = document.text.lower()
        if "mercury" not in text:
            return False
        return any(self._find_column_mapping(table.headers) for table in document.tables)

    def extract(self, document: PdfDocument) -> ExtractionResult:
        period = _parse_statement_period(document.text)
        transactions: list[ExtractedTransaction] = []
        last_transaction: ExtractedTransaction | None = None
        account_name = _infer_account_name(document.text)

        for table in document.tables:
            mapping = self._find_column_mapping(table.headers)
            if not mapping:
                continue
            for row in table.rows:
                txn = self._parse_row(row, mapping, period, last_transaction)
                if txn is None:
                    continue
                transactions.append(txn)
                last_transaction = txn

        metadata = StatementMetadata(
            institution="Mercury",
            account_name=account_name,
            account_type="checking",
            start_date=period.start_date,
            end_date=period.end_date,
        )
        return ExtractionResult(metadata=metadata, transactions=transactions)

    def _find_column_mapping(self, headers: Iterable[str]) -> _ColumnMapping | None:
        normalized = [" ".join(header.lower().split()) for header in headers]
        date_idx = _find_index(normalized, {"date", "transaction date"})
        desc_idx = _find_index(normalized, {"description", "transaction description", "details"})
        if date_idx is None or desc_idx is None:
            return None
        amount_idx = _find_index(normalized, {"amount", "transaction amount"})
        money_in_idx = _find_index(normalized, {"money in", "credit", "amount in"})
        money_out_idx = _find_index(normalized, {"money out", "debit", "amount out"})
        return _ColumnMapping(
            date_index=date_idx,
            description_index=desc_idx,
            amount_index=amount_idx,
            money_in_index=money_in_idx,
            money_out_index=money_out_idx,
        )

    def _parse_row(
        self,
        row: Iterable[str],
        mapping: _ColumnMapping,
        period: _StatementPeriod,
        last_transaction: ExtractedTransaction | None,
    ) -> ExtractedTransaction | None:
        cells = [cell.strip() for cell in row]
        if len(cells) <= max(mapping.date_index, mapping.description_index):
            return None

        date_value = cells[mapping.date_index]
        description = cells[mapping.description_index]

        if not date_value and description and last_transaction:
            combined_desc = f"{last_transaction.merchant} {description}".strip()
            last_transaction.merchant = combined_desc
            last_transaction.original_description = f"{last_transaction.original_description} {description}".strip()
            return None

        if not date_value or not description:
            return None

        normalized_desc = description.lower()
        if any(keyword in normalized_desc for keyword in _SUMMARY_KEYWORDS):
            return None

        try:
            txn_date = _parse_mercury_date(date_value, period)
        except ValueError:
            return None

        amount = _resolve_amount(cells, mapping)
        if amount is None:
            return None

        return ExtractedTransaction(
            date=txn_date,
            merchant=description.strip(),
            amount=amount,
            original_description=description.strip(),
        )


def _parse_statement_period(text: str) -> _StatementPeriod:
    match = _PERIOD_RE.search(text)
    if match:
        start = datetime.strptime(match.group(1).replace(",", ""), "%B %d %Y").date()
        end = datetime.strptime(match.group(2).replace(",", ""), "%B %d %Y").date()
        return _StatementPeriod(start, end)
    match = _PERIOD_NUMERIC_RE.search(text)
    if match:
        start = _parse_date_with_format(match.group(1))
        end = _parse_date_with_format(match.group(2))
        return _StatementPeriod(start, end)
    return _StatementPeriod(start_date=None, end_date=None)


def _parse_date_with_format(value: str) -> date:
    cleaned = value.strip()
    if len(cleaned.split("/")) == 3 and len(cleaned.split("/")[-1]) == 2:
        return datetime.strptime(cleaned, "%m/%d/%y").date()
    return datetime.strptime(cleaned, "%m/%d/%Y").date()


def _infer_account_name(text: str) -> str:
    match = re.search(
        r"Account(?:\s+(?:Number|No\.?|Ending))?[^\d]{0,6}(\d{3,4})",
        text,
        re.IGNORECASE,
    )
    if match:
        return f"Mercury Checking ****{match.group(1)}"
    return "Mercury Business Checking"


def _parse_mercury_date(value: str, period: _StatementPeriod) -> date:
    cleaned = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    if "/" in cleaned:
        month_str, day_str = cleaned.split("/", 1)
        month = int(month_str)
        day = int(day_str)
        year = period.infer_year(month)
        return date(year, month, day)
    raise ValueError(f"Unrecognized date format: {value}")


def _resolve_amount(cells: list[str], mapping: _ColumnMapping) -> float | None:
    if mapping.amount_index is not None and mapping.amount_index < len(cells):
        raw = cells[mapping.amount_index]
        if raw:
            return _parse_amount(raw)
    if mapping.money_out_index is not None and mapping.money_out_index < len(cells):
        raw = cells[mapping.money_out_index]
        if raw:
            return abs(_parse_amount(raw))
    if mapping.money_in_index is not None and mapping.money_in_index < len(cells):
        raw = cells[mapping.money_in_index]
        if raw:
            return -abs(_parse_amount(raw))
    return None


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


def _find_index(headers: list[str], targets: set[str]) -> int | None:
    for idx, header in enumerate(headers):
        normalized = header.lower()
        if normalized in targets:
            return idx
        for target in targets:
            if target in normalized:
                return idx
    return None
