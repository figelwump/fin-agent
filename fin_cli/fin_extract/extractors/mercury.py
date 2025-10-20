"""Mercury business checking statement extractor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Iterable, Sequence

from ..parsers.pdf_loader import PdfDocument, PdfTable
from ..types import ExtractionResult, ExtractedTransaction, StatementMetadata
from ..utils import SignClassifier, normalize_pdf_table, normalize_token, parse_amount
from ..utils.table import NormalizedTable
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

_MERCURY_SIGN_CLASSIFIER = SignClassifier(
    charge_keywords={"ach pull", "debit", "withdrawal", "purchase"},
    credit_keywords={"ach in", "transfer in", "interest", "deposit"},
    transfer_keywords={"transfer to", "transfer from", "transfer", "cash sending apps", "mercury checking"},
    interest_keywords={"interest"},
    card_payment_keywords={"credit card", "credit crd", "applecard", "bank of america", "card"},
)

_MONTH_DAY_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b",
    re.IGNORECASE,
)

_AMOUNT_RE = re.compile(r"[\-−–]?\$[\d,]+(?:\.\d+)?")

_MERCURY_TYPE_SUFFIXES = (
    "ACH In",
    "ACH Pull",
    "Transfer Out",
    "Transfer In",
    "Check Deposit",
    "Interest Payment",
)


class MercuryExtractor(StatementExtractor):
    name = "mercury"

    def supports(self, document: PdfDocument) -> bool:
        text = document.text.lower()
        if "mercury" not in text:
            return False
        for table in document.tables:
            normalized = normalize_pdf_table(table, header_predicate=_mercury_header_predicate)
            if self._find_column_mapping(normalized.headers):
                return True
        return False

    def extract(self, document: PdfDocument) -> ExtractionResult:
        period = _parse_statement_period(document.text)
        account_name = _infer_account_name(document.text)
        transactions: list[ExtractedTransaction] = []

        for table in document.tables:
            normalized = normalize_pdf_table(
                table,
                header_predicate=_mercury_header_predicate,
                header_scan=6,
            )
            mapping = self._find_column_mapping(normalized.headers)
            rows: Sequence[tuple[str, ...]] = normalized.rows

            if not mapping:
                expanded = _expand_single_column_table(table)
                if expanded:
                    mapping = self._find_column_mapping(expanded.headers)
                    if mapping:
                        rows = expanded.rows

            if not mapping:
                continue

            transactions.extend(self._parse_rows(rows, mapping, period))

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

        distinct_indices = {
            idx
            for idx in (
                date_idx,
                desc_idx,
                amount_idx,
                money_in_idx,
                money_out_idx,
                type_idx,
            )
            if idx is not None
        }
        if len(distinct_indices) <= 2:
            return None

        return _ColumnMapping(
            date_index=date_idx,
            description_index=desc_idx,
            amount_index=amount_idx,
            money_in_index=money_in_idx,
            money_out_index=money_out_idx,
            type_index=type_idx,
        )

    def _parse_rows(
        self,
        rows: Sequence[tuple[str, ...]],
        mapping: _ColumnMapping,
        period: _StatementPeriod,
    ) -> list[ExtractedTransaction]:
        transactions: list[ExtractedTransaction] = []
        last_transaction: ExtractedTransaction | None = None
        current_date: date | None = None

        for row in rows:
            cells = list(row)
            if len(cells) <= max(mapping.date_index, mapping.description_index):
                continue

            date_value = _get_cell(cells, mapping.date_index)
            description = _get_cell(cells, mapping.description_index)
            type_value = _get_cell(cells, mapping.type_index)

            if date_value:
                try:
                    current_date = _parse_mercury_date(date_value, period)
                except ValueError:
                    current_date = None
            if current_date is None:
                continue

            if not description:
                continue

            if _is_summary_row(description):
                continue

            amount = _resolve_amount(cells, mapping)
            money_in_value = _get_cell(cells, mapping.money_in_index)
            money_out_value = _get_cell(cells, mapping.money_out_index)

            if amount is None:
                if last_transaction is not None:
                    appended = f"{last_transaction.merchant} {description.strip()}".strip()
                    last_transaction.merchant = appended
                    last_transaction.original_description = (
                        f"{last_transaction.original_description} {description.strip()}".strip()
                    )
                continue

            signed_amount = _MERCURY_SIGN_CLASSIFIER.classify(
                abs(amount),
                description=description,
                type_value=type_value,
                money_in_value=money_in_value,
                money_out_value=money_out_value,
            )

            if signed_amount is None or signed_amount <= 0:
                continue

            txn = ExtractedTransaction(
                date=current_date,
                merchant=description.strip(),
                amount=signed_amount,
                original_description=description.strip(),
            )
            transactions.append(txn)
            last_transaction = txn

        return transactions


def _expand_single_column_table(table: PdfTable) -> NormalizedTable | None:
    cells: list[str] = []
    cells.extend(cell for cell in table.headers if cell)
    for row in table.rows:
        cells.extend(cell for cell in row if cell)

    if not cells:
        return None

    combined = "\n".join(cells).strip()
    if "all transactions" not in combined.lower():
        return None

    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    header_idx = None
    for idx, line in enumerate(lines):
        lower = line.lower()
        if "date" in lower and "amount" in lower and "description" in lower:
            header_idx = idx
            break
    if header_idx is None:
        return None

    data_lines = lines[header_idx + 1 :]
    rows: list[tuple[str, ...]] = []
    current_date: str | None = None

    for line in data_lines:
        lowered = line.lower()
        if lowered.startswith("total ") or "banking services" in lowered or lowered.startswith("interest disclosure"):
            break

        date_match = _MONTH_DAY_RE.match(line)
        if date_match:
            current_date = date_match.group(0)
            rest = line[date_match.end() :].strip()
        else:
            rest = line
            if current_date is None:
                continue

        if not rest:
            continue

        amounts = _AMOUNT_RE.findall(rest)
        if not amounts:
            if rows:
                updated = list(rows[-1])
                updated[1] = f"{updated[1]} {line.strip()}".strip()
                rows[-1] = tuple(updated)
            continue

        amount_str = amounts[0]
        before, after = rest.split(amount_str, 1)
        balance_str = ""
        if len(amounts) > 1:
            balance_str = amounts[1]
            after = after.replace(balance_str, "", 1)

        description_raw = f"{before} {after}".strip()
        description_clean = _clean_mercury_text(description_raw)
        description_clean, type_value = _split_mercury_type(description_clean)

        rows.append(
            (
                current_date or "",
                description_clean,
                type_value,
                amount_str,
                balance_str,
            )
        )

    if not rows:
        return None

    headers = ("Date", "Description", "Type", "Amount", "End of Day Balance")
    return NormalizedTable(headers=headers, rows=rows)


def _clean_mercury_text(value: str) -> str:
    cleaned = value
    for glyph in ("\uea01", "\uea02", "\uea03", "\uea08"):
        cleaned = cleaned.replace(glyph, " ")
    cleaned = cleaned.replace("•", " ")
    return " ".join(cleaned.split())


def _split_mercury_type(description: str) -> tuple[str, str]:
    lowered = description.lower()
    for suffix in _MERCURY_TYPE_SUFFIXES:
        if lowered.endswith(suffix.lower()):
            trimmed = description[: -len(suffix)].strip()
            return trimmed or description, suffix
    return description, ""


def _mercury_header_predicate(header: tuple[str, ...]) -> bool:
    normalized = [cell.lower() for cell in header if cell]
    return (
        any("date" in cell for cell in normalized)
        and any("description" in cell for cell in normalized)
        and any("amount" in cell for cell in normalized)
    )


def _is_summary_row(value: str) -> bool:
    normalized = normalize_token(value)
    return normalized in _SUMMARY_KEYWORDS


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
        for fmt in ("%b", "%B"):
            try:
                month = datetime.strptime(month_name, fmt).month
                year = period.infer_year(month)
                return date(year, month, int(day_str))
            except ValueError:
                continue
    if "/" in cleaned:
        month_str, day_str = cleaned.split("/", 1)
        month = int(month_str)
        day = int(day_str)
        year = period.infer_year(month)
        return date(year, month, day)
    raise ValueError(f"Unrecognized date format: {value}")


def _get_cell(cells: Sequence[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(cells):
        return ""
    return cells[index].strip()


def _resolve_amount(cells: Sequence[str], mapping: _ColumnMapping) -> float | None:
    candidate = _get_cell(cells, mapping.amount_index)
    if candidate:
        return abs(parse_amount(candidate))
    money_out = _get_cell(cells, mapping.money_out_index)
    if money_out:
        return abs(parse_amount(money_out))
    money_in = _get_cell(cells, mapping.money_in_index)
    if money_in:
        return abs(parse_amount(money_in))
    return None


def _find_index(headers: list[str], targets: set[str]) -> int | None:
    for idx, header in enumerate(headers):
        normalized = header.lower()
        if normalized in targets:
            return idx
        for target in targets:
            if target in normalized:
                return idx
    return None
