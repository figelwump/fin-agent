"""Chase-specific statement extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Iterable, Sequence

from ..parsers.pdf_loader import PdfDocument
from ..types import ExtractionResult, ExtractedTransaction, StatementMetadata
from ..utils import SignClassifier, normalize_pdf_table, normalize_token, parse_amount
from .base import StatementExtractor


_SECTION_HEADER_DESCRIPTIONS = {
    "PAYMENTS AND OTHER CREDITS",
}


@dataclass(slots=True)
class _ColumnMapping:
    date_index: int
    description_index: int
    amount_index: int
    type_index: int | None = None


_KEYWORD_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}

_ACCOUNT_NAME_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("amazon", "prime visa"), "Amazon Prime Visa"),
    (("ultimate rewards", "travel credit", "first $300"), "Chase Sapphire Reserve"),
]

_CHASE_SIGN_CLASSIFIER = SignClassifier(
    charge_keywords={"sale", "purchase", "debit"},
    credit_keywords={"payment", "credit", "adjustment", "refund"},
    transfer_keywords={"transfer"},
    interest_keywords={"interest"},
    card_payment_keywords={"payment"},
)

_DATE_NO_YEAR_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")


class ChaseExtractor(StatementExtractor):
    name = "chase"

    def supports(self, document: PdfDocument) -> bool:
        text = document.text
        if not _contains_keyword(text, "chase"):
            return False
        for table in document.tables:
            normalized = normalize_pdf_table(table, header_predicate=_chase_header_predicate)
            if self._find_column_mapping(normalized.headers):
                return True
        return _contains_keyword(text, "account activity")

    def extract(self, document: PdfDocument) -> ExtractionResult:
        transactions: list[ExtractedTransaction] = []
        statement_month, statement_year = _infer_statement_month_year(document.text)
        year_hint = statement_year or datetime.today().year
        for table in document.tables:
            normalized = normalize_pdf_table(table, header_predicate=_chase_header_predicate)
            mapping = self._find_column_mapping(normalized.headers)
            if not mapping:
                continue
            transactions.extend(
                self._parse_rows(
                    normalized.rows,
                    mapping,
                    year_hint=year_hint,
                    statement_month=statement_month,
                )
            )

        if not transactions:
            transactions = self._extract_from_text(document.text)

        account_name = _infer_account_name(document.text)
        metadata = StatementMetadata(
            institution="Chase",
            account_name=account_name,
            account_type="credit",
            start_date=None,
            end_date=None,
        )
        return ExtractionResult(metadata=metadata, transactions=transactions)

    def _find_column_mapping(self, headers: Iterable[str]) -> _ColumnMapping | None:
        normalized = [header.strip().lower() for header in headers]
        date_idx = _find_index(normalized, {"transaction date", "date", "post date"})
        desc_idx = _find_index(normalized, {"merchant name", "description", "transaction description"})
        amount_idx = _find_index(normalized, {"amount", "transaction amount", "total"})
        type_idx = _find_index(normalized, {"type", "transaction type"})
        if date_idx is None or desc_idx is None or amount_idx is None:
            return None
        return _ColumnMapping(
            date_index=date_idx,
            description_index=desc_idx,
            amount_index=amount_idx,
            type_index=type_idx,
        )

    def _parse_rows(
        self,
        rows: Sequence[tuple[str, ...]],
        mapping: _ColumnMapping,
        *,
        year_hint: int | None = None,
        statement_month: int | None = None,
    ) -> list[ExtractedTransaction]:
        transactions: list[ExtractedTransaction] = []
        current_date: date | None = None
        last_transaction: ExtractedTransaction | None = None
        last_resolved_date: date | None = None

        for row in rows:
            cells = list(row)
            if len(cells) <= max(mapping.date_index, mapping.description_index):
                continue

            date_value = _get_cell(cells, mapping.date_index)
            description = _get_cell(cells, mapping.description_index)
            type_value = _get_cell(cells, mapping.type_index)

            if date_value:
                try:
                    current_date = _parse_chase_date(
                        date_value,
                        year_hint=year_hint,
                        statement_month=statement_month,
                        last_date=last_resolved_date,
                    )
                    last_resolved_date = current_date
                except ValueError:
                    current_date = None
            if current_date is None:
                continue

            if not description:
                continue

            if description.upper() in _SECTION_HEADER_DESCRIPTIONS:
                continue

            amount_value = _get_cell(cells, mapping.amount_index)
            if not amount_value:
                if last_transaction is not None:
                    appended = f"{last_transaction.merchant} {description.strip()}".strip()
                    last_transaction.merchant = appended
                    last_transaction.original_description = (
                        f"{last_transaction.original_description} {description.strip()}".strip()
                    )
                continue

            try:
                amount = abs(parse_amount(amount_value))
            except ValueError:
                continue

            signed = _CHASE_SIGN_CLASSIFIER.classify(
                amount,
                description=description,
                type_value=type_value,
            )
            if signed is None or signed <= 0:
                continue

            txn = ExtractedTransaction(
                date=current_date,
                merchant=description.strip(),
                amount=signed,
                original_description=description.strip(),
            )
            transactions.append(txn)
            last_transaction = txn

        return transactions

    def _extract_from_text(self, text: str) -> list[ExtractedTransaction]:
        year = _infer_statement_year(text)
        current_section: str | None = None
        transactions: list[ExtractedTransaction] = []
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            upper_line = line.upper()
            if _contains_keyword(upper_line, "PAYMENTS AND OTHER CREDITS"):
                current_section = "credit"
                continue
            if _contains_keyword(upper_line, "PURCHASE") or _contains_keyword(upper_line, "PURCHASES"):
                current_section = "purchase"
                continue
            match = _STATEMENT_LINE_RE.match(line)
            if not match:
                continue
            month, day, description, amount_str = match.groups()
            description = description.strip()
            if description.upper() in _SECTION_HEADER_DESCRIPTIONS:
                continue
            try:
                txn_date = _resolve_date(month, day, year)
                amount = abs(parse_amount(amount_str))
            except ValueError:
                continue
            signed = _CHASE_SIGN_CLASSIFIER.classify(
                amount,
                description=description,
                type_value=current_section or "",
            )
            if signed is None or signed <= 0:
                continue
            transactions.append(
                ExtractedTransaction(
                    date=txn_date,
                    merchant=description,
                    amount=signed,
                    original_description=description,
                )
            )
        return transactions


def _contains_keyword(text: str, keyword: str) -> bool:
    pattern = _KEYWORD_PATTERN_CACHE.get(keyword)
    if pattern is None:
        parts: list[str] = []
        for char in keyword:
            if char.isalpha():
                parts.append(f"{re.escape(char)}+")
            elif char.isspace():
                parts.append(r"\s+")
            else:
                parts.append(re.escape(char))
        pattern = re.compile("".join(parts), re.IGNORECASE)
        _KEYWORD_PATTERN_CACHE[keyword] = pattern
    return bool(pattern.search(text))


def _infer_account_name(text: str) -> str:
    for keywords, name in _ACCOUNT_NAME_PATTERNS:
        if all(_contains_keyword(text, keyword) for keyword in keywords):
            return name
    return "Chase Account"


def _chase_header_predicate(header: tuple[str, ...]) -> bool:
    normalized = [cell.lower() for cell in header if cell]
    return (
        any("date" in cell for cell in normalized)
        and any("description" in cell for cell in normalized)
        and any("amount" in cell for cell in normalized)
    )


def _get_cell(cells: Sequence[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(cells):
        return ""
    return cells[index].strip()


def _find_index(headers: list[str], targets: set[str]) -> int | None:
    for idx, header in enumerate(headers):
        normalized = header.lower()
        if normalized in targets:
            return idx
        for target in targets:
            if target in normalized:
                return idx
    return None


_STATEMENT_LINE_RE = re.compile(
    r"^(\d{2})/(\d{2})\s+(.+?)\s+([-\$\(\)\d,\.]+)$"
)


_MONTH_TO_INT = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _infer_statement_month_year(text: str) -> tuple[int | None, int | None]:
    month_year_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
        text,
        re.IGNORECASE,
    )
    if month_year_match:
        month_name = month_year_match.group(1).lower()
        year_value = int(month_year_match.group(2))
        month_value = _MONTH_TO_INT.get(month_name)
        return month_value, year_value
    return None, None


def _infer_statement_year(text: str) -> int:
    month_value, year_value = _infer_statement_month_year(text)
    if year_value is not None:
        return year_value
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
    if month_i == 12 and datetime.today().month == 1:
        year -= 1
    return date(year, month_i, day_i)


def _parse_chase_date(
    value: str,
    *,
    year_hint: int | None = None,
    statement_month: int | None = None,
    last_date: date | None = None,
) -> datetime.date:
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    match = _DATE_NO_YEAR_RE.match(value)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        base_year = year_hint or datetime.today().year

        # If we know the statement month, adjust for cross-year statements
        if statement_month is not None and month > statement_month and month - statement_month > 1:
            base_year -= 1
        elif last_date is not None:
            if month > last_date.month and month - last_date.month > 6:
                base_year = last_date.year - 1
            elif month < last_date.month and last_date.month - month > 6:
                base_year = last_date.year + 1

        return date(base_year, month, day)

    raise ValueError(f"Unrecognized date format: {value}")
