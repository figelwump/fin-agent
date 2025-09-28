"""Mercury business checking statement extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from itertools import zip_longest
from typing import Iterable, Sequence

from ..parsers.pdf_loader import PdfDocument, PdfTable
from ..types import ExtractionResult, ExtractedTransaction, StatementMetadata
from .base import StatementExtractor


@dataclass(slots=True)
class _ColumnMapping:
    date_index: int
    description_index: int
    amount_index: int | None = None
    money_in_index: int | None = None
    money_out_index: int | None = None
    type_index: int | None = None


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

_HEADER_KEYWORDS = {"date", "description", "amount", "balance", "type"}

_DEPOSIT_KEYWORDS = {
    "ach in",
    "transfer in",
    "interest",
    "interest payment",
    "deposit",
    "credit",
    "incoming",
}

_WITHDRAW_KEYWORDS = {
    "ach pull",
    "transfer out",
    "debit",
    "withdrawal",
    "payment",
    "purchase",
    "fee",
    "transfer to",
}

_TRANSFER_KEYWORDS = {
    "transfer to",
    "transfer from",
    "transfer",
    "internal",
    "mercury checking",
    "cash sending apps",
}

_CREDIT_CARD_PAYMENT_KEYWORDS = {
    "card",
    "credit crd",
    "credit card",
    "applecard",
    "chase credit",
    "bank of america",
    "amex",
    "american express",
}


class MercuryExtractor(StatementExtractor):
    name = "mercury"

    def supports(self, document: PdfDocument) -> bool:
        text = document.text.lower()
        if "mercury" not in text:
            return False
        for table in document.tables:
            mapping, data_rows = self._prepare_table(table)
            if mapping and data_rows:
                return True
        return False

    def extract(self, document: PdfDocument) -> ExtractionResult:
        period = _parse_statement_period(document.text)
        transactions: list[ExtractedTransaction] = []
        account_name = _infer_account_name(document.text)

        for table in document.tables:
            mapping, data_rows = self._prepare_table(table)
            if not mapping:
                continue
            transactions.extend(self._parse_rows(data_rows, mapping, period))

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
        type_idx = _find_index(normalized, {"type", "transaction type"})
        return _ColumnMapping(
            date_index=date_idx,
            description_index=desc_idx,
            amount_index=amount_idx,
            money_in_index=money_in_idx,
            money_out_index=money_out_idx,
            type_index=type_idx,
        )

    def _prepare_table(
        self,
        table: PdfTable,
    ) -> tuple[_ColumnMapping | None, list[tuple[str, ...]]]:
        candidate_rows: list[tuple[str, ...]] = [table.headers, *table.rows]
        max_scan = min(len(candidate_rows), 6)

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
        current_date: date | None = None

        for row in rows:
            cells = [cell.strip() for cell in row]
            if len(cells) <= max(mapping.date_index, mapping.description_index):
                continue

            raw_date = cells[mapping.date_index]
            description = cells[mapping.description_index]
            type_value = (
                cells[mapping.type_index]
                if mapping.type_index is not None and mapping.type_index < len(cells)
                else ""
            )

            if raw_date:
                try:
                    current_date = _parse_mercury_date(raw_date, period)
                except ValueError:
                    continue

            if current_date is None or not description:
                continue

            normalized_desc = description.lower()
            if any(keyword in normalized_desc for keyword in _SUMMARY_KEYWORDS):
                continue

            amount = _resolve_amount(cells, mapping)
            if amount is None:
                if description and transactions:
                    last_txn = transactions[-1]
                    appended = f"{last_txn.merchant} {description.strip()}".strip()
                    last_txn.merchant = appended
                    last_txn.original_description = (
                        f"{last_txn.original_description} {description.strip()}".strip()
                    )
                continue

            money_out_value = (
                cells[mapping.money_out_index]
                if mapping.money_out_index is not None and mapping.money_out_index < len(cells)
                else ""
            )
            money_in_value = (
                cells[mapping.money_in_index]
                if mapping.money_in_index is not None and mapping.money_in_index < len(cells)
                else ""
            )

            final_amount = _apply_sign(amount, type_value, description, money_in_value, money_out_value)
            if final_amount <= 0:
                continue

            if _is_transfer(description, type_value):
                continue

            if _is_interest(description, type_value):
                continue

            if _is_credit_card_payment(description, type_value):
                continue

            transactions.append(
                ExtractedTransaction(
                    date=current_date,
                    merchant=description.strip(),
                    amount=final_amount,
                    original_description=description.strip(),
                )
            )

        return transactions


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
    bullet_match = re.search(r"\u2022\u2022(\d{3,4})", text)
    if bullet_match:
        return f"Mercury Checking ****{bullet_match.group(1)}"

    matches = re.findall(
        r"Account(?:\s+(?:Number|No\.?|Ending))?[^\d]{0,10}(\d{3,4})(?!\d)",
        text,
        re.IGNORECASE,
    )
    if matches:
        return f"Mercury Checking ****{matches[-1]}"
    return "Mercury Business Checking"


def _parse_mercury_date(value: str, period: _StatementPeriod) -> date:
    cleaned = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    month_match = re.match(r"([A-Za-z]+)\s+(\d{1,2})", cleaned)
    if month_match:
        month_name, day_str = month_match.groups()
        month = None
        for fmt in ("%b", "%B"):
            try:
                month = datetime.strptime(month_name, fmt).month
                break
            except ValueError:
                continue
        if month is not None:
            year = period.infer_year(month)
            return date(year, month, int(day_str))
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
    cleaned = cleaned.replace("–", "-").replace("−", "-")
    clean_no_dollar = cleaned.replace("$", "")
    negative = False
    if clean_no_dollar.startswith("(") and clean_no_dollar.endswith(")"):
        negative = True
        clean_no_dollar = clean_no_dollar[1:-1]
    if clean_no_dollar.startswith("-"):
        negative = True
        clean_no_dollar = clean_no_dollar[1:]
    match = re.search(r"\d+(?:\.\d+)?", clean_no_dollar)
    if not match:
        raise ValueError(f"Empty amount in '{value}'")
    amount = float(match.group())
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


def _normalize_cells(row: Iterable[str]) -> tuple[str, ...]:
    return tuple((cell or "").strip() for cell in row)


def _merge_rows(*rows: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []
    for column_cells in zip_longest(*rows, fillvalue=""):
        merged_value = " ".join(part for part in column_cells if part).strip()
        merged.append(merged_value)
    return tuple(merged)


def _looks_like_header(row: Iterable[str]) -> bool:
    values = [value.strip().lower() for value in row if value and value.strip()]
    if len(values) < 2:
        return False
    matches = sum(1 for value in values for keyword in _HEADER_KEYWORDS if keyword in value)
    return matches >= 2


def _normalize_token(value: str) -> str:
    if not value:
        return ""
    lowered = value.lower()
    return re.sub(r"[^a-z0-9\s]", "", lowered)


def _matches_keywords(normalized: str, keywords: set[str]) -> bool:
    if not normalized:
        return False
    return any(keyword in normalized for keyword in keywords)


def _apply_sign(
    amount: float,
    type_value: str,
    description: str,
    money_in_value: str,
    money_out_value: str,
) -> float:
    if amount == 0:
        return 0.0

    if money_in_value and not money_out_value:
        return -abs(amount)
    if money_out_value and not money_in_value:
        return abs(amount)

    normalized_type = _normalize_token(type_value)
    normalized_desc = _normalize_token(description)
    normalized_in = _normalize_token(money_in_value)
    normalized_out = _normalize_token(money_out_value)

    if _matches_keywords(normalized_type, _DEPOSIT_KEYWORDS) or _matches_keywords(
        normalized_desc, _DEPOSIT_KEYWORDS
    ) or _matches_keywords(normalized_in, _DEPOSIT_KEYWORDS):
        return -abs(amount)

    if _matches_keywords(normalized_type, _WITHDRAW_KEYWORDS) or _matches_keywords(
        normalized_desc, _WITHDRAW_KEYWORDS
    ) or _matches_keywords(normalized_out, _WITHDRAW_KEYWORDS):
        return abs(amount)

    if amount < 0:
        return abs(amount)
    return amount


def _is_transfer(description: str, type_value: str) -> bool:
    normalized_desc = _normalize_token(description)
    normalized_type = _normalize_token(type_value)
    return _matches_keywords(normalized_desc, _TRANSFER_KEYWORDS) or "transfer" in normalized_type


def _is_interest(description: str, type_value: str) -> bool:
    normalized_desc = _normalize_token(description)
    normalized_type = _normalize_token(type_value)
    return "interest" in normalized_desc or "interest" in normalized_type


def _is_credit_card_payment(description: str, type_value: str) -> bool:
    normalized_desc = _normalize_token(description)
    normalized_type = _normalize_token(type_value)
    return (
        "ach pull" in normalized_type
        and _matches_keywords(normalized_desc, _CREDIT_CARD_PAYMENT_KEYWORDS)
    )
