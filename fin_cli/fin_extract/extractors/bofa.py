"""Bank of America statement extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from itertools import zip_longest
from typing import Iterable, Sequence

from ..parsers.pdf_loader import PdfDocument
from ..types import ExtractionResult, ExtractedTransaction, StatementMetadata
from .base import StatementExtractor


@dataclass(slots=True)
class _ColumnMapping:
    date_index: int
    description_index: int
    amount_index: int | None = None
    deposits_index: int | None = None
    withdrawals_index: int | None = None


@dataclass(slots=True)
class _StatementPeriod:
    start_date: date | None
    end_date: date | None

    def infer_year(self, month: int) -> int:
        """Infer the transaction year using the statement period when possible."""

        if self.start_date and self.end_date:
            if self.start_date.month <= self.end_date.month:
                # Simple case: period contained within a single calendar year.
                if self.start_date.month <= month <= self.end_date.month:
                    return self.start_date.year
                return self.end_date.year
            # Statement crosses the year boundary (e.g., Dec -> Jan).
            if month >= self.start_date.month:
                return self.start_date.year
            return self.end_date.year
        if self.end_date:
            return self.end_date.year
        if self.start_date:
            return self.start_date.year
        return datetime.today().year


_PERIOD_NUMERIC_RE = re.compile(
    r"Statement Period[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|to)\s*(\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

_PERIOD_LONG_RE = re.compile(
    r"Statement Period[:\s]+([A-Za-z]+\s+\d{1,2},\s*\d{4})\s*(?:-|to)\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})",
    re.IGNORECASE,
)

_ACCOUNT_NAME_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"advantage\s+banking", re.IGNORECASE), "BofA Advantage Checking", "checking"),
    (re.compile(r"advantage\s+relationship", re.IGNORECASE), "BofA Advantage Relationship", "checking"),
    (re.compile(r"travel\s+rewards", re.IGNORECASE), "BofA Travel Rewards", "credit"),
    (re.compile(r"customized\s+cash\s+rewards", re.IGNORECASE), "BofA Customized Cash Rewards", "credit"),
]

_SUMMARY_ROW_KEYWORDS = {
    "total",
    "balance",
    "summary",
    "fees",
    "transactions",
    "transactions continued",
    "payments and other credits",
    "charges and purchases",
    "purchases and adjustments",
}

_HEADER_KEYWORDS = {
    "transaction",
    "posting",
    "date",
    "description",
    "amount",
    "withdrawal",
    "withdrawals",
    "deposit",
    "deposits",
    "credit",
    "debit",
    "charges",
    "purchases",
}


class BankOfAmericaExtractor(StatementExtractor):
    name = "bofa"

    def supports(self, document: PdfDocument) -> bool:
        text = document.text.lower()
        if "bank of america" not in text and "bofa" not in text:
            return False
        for table in document.tables:
            mapping, data_rows = self._prepare_table(table)
            if mapping and data_rows:
                return True
        return False

    def extract(self, document: PdfDocument) -> ExtractionResult:
        period = _parse_statement_period(document.text)
        account_name, account_type = _infer_account_details(document.text)
        transactions: list[ExtractedTransaction] = []

        for table in document.tables:
            mapping, data_rows = self._prepare_table(table)
            if not mapping:
                continue
            transactions.extend(self._parse_rows(data_rows, mapping, period))

        metadata = StatementMetadata(
            institution="Bank of America",
            account_name=account_name,
            account_type=account_type,
            start_date=period.start_date,
            end_date=period.end_date,
        )
        return ExtractionResult(metadata=metadata, transactions=transactions)

    def _find_column_mapping(self, headers: Iterable[str]) -> _ColumnMapping | None:
        normalized = [" ".join(header.lower().split()) for header in headers]
        date_idx = _find_index(normalized, {"date", "transaction date", "posting date"})
        desc_idx = _find_index(normalized, {"description", "transaction description"})
        if date_idx is None or desc_idx is None:
            return None
        amount_idx = _find_index(normalized, {"amount", "transaction amount", "purchase amount"})
        deposits_idx = _find_index(
            normalized,
            {
                "deposits",
                "deposits and other credits",
                "deposits/credits",
                "credits",
            },
        )
        withdrawals_idx = _find_index(
            normalized,
            {
                "withdrawals",
                "withdrawals and other debits",
                "withdrawals/debits",
                "debits",
                "charges",
            },
        )
        return _ColumnMapping(
            date_index=date_idx,
            description_index=desc_idx,
            amount_index=amount_idx,
            deposits_index=deposits_idx,
            withdrawals_index=withdrawals_idx,
        )

    def _prepare_table(
        self,
        table: PdfTable,
    ) -> tuple[_ColumnMapping | None, list[tuple[str, ...]]]:
        """Return column mapping and data rows starting after the header block."""

        candidate_rows: list[tuple[str, ...]] = [table.headers, *table.rows]
        max_scan = min(len(candidate_rows), 8)

        for idx in range(max_scan):
            base = candidate_rows[idx]
            header_variants = [(_normalize_cells(base), 1)]
            if idx + 1 < len(candidate_rows):
                header_variants.append((
                    _merge_rows(base, candidate_rows[idx + 1]),
                    2,
                ))
            if idx + 2 < len(candidate_rows):
                header_variants.append((
                    _merge_rows(base, candidate_rows[idx + 1], candidate_rows[idx + 2]),
                    3,
                ))

            for header, span in header_variants:
                if not _looks_like_header(header):
                    continue
                mapping = self._find_column_mapping(header)
                if mapping:
                    data_rows = candidate_rows[idx + span :]
                    return mapping, [tuple(_normalize_cells(row)) for row in data_rows]

        return None, [tuple(_normalize_cells(row)) for row in table.rows]

    def _parse_rows(
        self,
        rows: Sequence[tuple[str, ...]],
        mapping: _ColumnMapping,
        period: _StatementPeriod,
    ) -> list[ExtractedTransaction]:
        transactions: list[ExtractedTransaction] = []
        current: dict[str, object] | None = None

        for row in rows:
            cells = list(row)
            if len(cells) <= max(mapping.date_index, mapping.description_index):
                continue

            date_value = cells[mapping.date_index]
            description = cells[mapping.description_index]

            if not any(cells):
                continue

            if date_value:
                if current and current.get("amount") is not None:
                    finalized = _finalize_transaction(current)
                    if finalized is not None:
                        transactions.append(finalized)
                    current = None

                try:
                    txn_date = _parse_bofa_date(date_value, period)
                except ValueError:
                    current = None
                    continue

                normalized_desc = description.strip()
                if _is_summary_row(normalized_desc):
                    current = None
                    continue

                amount = _resolve_amount(cells, mapping)

                current = {
                    "date": txn_date,
                    "description_parts": [normalized_desc] if normalized_desc else [],
                    "amount": amount,
                }
                continue

            if current is None:
                continue

            normalized_desc = description.strip()
            if normalized_desc and not _is_summary_row(normalized_desc):
                current["description_parts"].append(normalized_desc)  # type: ignore[index]

            amount = _resolve_amount(cells, mapping)
            if amount is not None:
                current["amount"] = amount

        if current and current.get("amount") is not None:
            finalized = _finalize_transaction(current)
            if finalized is not None:
                transactions.append(finalized)

        return transactions


def _normalize_cells(row: Iterable[str]) -> tuple[str, ...]:
    return tuple((cell or "").strip() for cell in row)


def _merge_rows(*rows: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []
    for column_cells in zip_longest(*rows, fillvalue=""):
        merged_value = " ".join(part for part in column_cells if part).strip()
        merged.append(merged_value)
    return tuple(merged)


def _looks_like_header(row: Iterable[str]) -> bool:
    values = [value for value in row if value]
    if len(values) < 2:
        return False
    normalized = " ".join(values).lower()
    return any(keyword in normalized for keyword in _HEADER_KEYWORDS)


def _is_summary_row(value: str) -> bool:
    if not value:
        return False
    normalized = " ".join(value.lower().split())
    if normalized in _SUMMARY_ROW_KEYWORDS:
        return True
    if normalized.startswith("total ") and "payments" in normalized and "credits" in normalized:
        return True
    return False


def _finalize_transaction(state: dict[str, object]) -> ExtractedTransaction | None:
    parts = [part for part in state.get("description_parts", []) if part]
    description = " ".join(parts).strip()
    amount = float(state["amount"])  # type: ignore[arg-type]
    if amount <= 0:
        return None
    return ExtractedTransaction(
        date=state["date"],  # type: ignore[arg-type]
        merchant=description,
        amount=amount,
        original_description=description,
    )


def _parse_statement_period(text: str) -> _StatementPeriod:
    match = _PERIOD_NUMERIC_RE.search(text)
    if match:
        start = _parse_date_with_format(match.group(1))
        end = _parse_date_with_format(match.group(2))
        return _StatementPeriod(start, end)
    match = _PERIOD_LONG_RE.search(text)
    if match:
        start = datetime.strptime(match.group(1), "%B %d, %Y").date()
        end = datetime.strptime(match.group(2), "%B %d, %Y").date()
        return _StatementPeriod(start, end)
    return _StatementPeriod(start_date=None, end_date=None)


def _parse_date_with_format(value: str) -> date:
    value = value.replace(" ", "")
    if len(value.split("/")) == 3 and len(value.split("/")[-1]) == 2:
        return datetime.strptime(value, "%m/%d/%y").date()
    return datetime.strptime(value, "%m/%d/%Y").date()


def _infer_account_details(text: str) -> tuple[str, str]:
    for pattern, name, acc_type in _ACCOUNT_NAME_PATTERNS:
        if pattern.search(text):
            return name, acc_type
    lowered = text.lower()
    if any(keyword in lowered for keyword in {"credit card", "visa", "mastercard", "payment due"}):
        return "Bank of America Credit Card", "credit"
    return "Bank of America Checking", "checking"


def _parse_bofa_date(value: str, period: _StatementPeriod) -> date:
    cleaned = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
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
    if mapping.withdrawals_index is not None and mapping.withdrawals_index < len(cells):
        raw = cells[mapping.withdrawals_index]
        if raw:
            return abs(_parse_amount(raw))
    if mapping.deposits_index is not None and mapping.deposits_index < len(cells):
        raw = cells[mapping.deposits_index]
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
