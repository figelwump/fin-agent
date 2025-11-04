"""Bank of America statement extractor."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from ..parsers.pdf_loader import PdfDocument
from ..types import ExtractedTransaction, ExtractionResult, StatementMetadata
from ..utils import SignClassifier, normalize_pdf_table, normalize_token, parse_amount
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
    (
        re.compile(r"advantage\s+relationship", re.IGNORECASE),
        "BofA Advantage Relationship",
        "checking",
    ),
    (re.compile(r"adv\s+relationship", re.IGNORECASE), "BofA Advantage Relationship", "checking"),
    (re.compile(r"travel\s+rewards", re.IGNORECASE), "BofA Travel Rewards", "credit"),
    (
        re.compile(r"customized\s+cash\s+rewards", re.IGNORECASE),
        "BofA Customized Cash Rewards",
        "credit",
    ),
    (re.compile(r"premium\s+rewards", re.IGNORECASE), "BofA Premium Rewards", "credit"),
    (re.compile(r"cash\s+rewards", re.IGNORECASE), "BofA Cash Rewards", "credit"),
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
    "total purchases and adjustments for this period",
    "total fees for this period",
    "interest charged",
    "interest charged on purchases",
    "late fee for payment due",
    "continued on next page",
    "continued from previous page",
}

_BOFA_SIGN_CLASSIFIER = SignClassifier(
    charge_keywords={"debit", "withdrawal", "purchase", "sale", "charge"},
    credit_keywords={"payment", "credit", "refund", "deposit"},
    transfer_keywords={"transfer", "atm withdrawal", "mercuryach"},
    interest_keywords={"interest"},
    card_payment_keywords={"credit card", "credit crd", "card services", "applecard"},
)


class BankOfAmericaExtractor(StatementExtractor):
    name = "bofa"

    def supports(self, document: PdfDocument) -> bool:
        text = document.text.lower()
        if "bank of america" not in text and "bofa" not in text:
            return False
        for table in document.tables:
            normalized = normalize_pdf_table(table, header_predicate=_bofa_header_predicate)
            if self._find_column_mapping(normalized.headers):
                return True
        return False

    def extract(self, document: PdfDocument) -> ExtractionResult:
        period = _parse_statement_period(document.text)
        account_name, account_type = _infer_account_details(document.text)
        transactions: list[ExtractedTransaction] = []

        for table in document.tables:
            normalized = normalize_pdf_table(
                table,
                header_predicate=_bofa_header_predicate,
                header_scan=6,
            )
            header_text = " ".join(normalized.headers).lower()
            if (
                ("deposit" in header_text or "other additions" in header_text)
                and "withdraw" not in header_text
                and "debit" not in header_text
            ):
                continue
            mapping = self._find_column_mapping(normalized.headers)
            if not mapping:
                continue
            transactions.extend(self._parse_rows(normalized.rows, mapping, period))

        if not transactions:
            transactions = self._extract_from_text(document.text, period)

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
        distinct_indices = {
            idx
            for idx in (date_idx, desc_idx, amount_idx, deposits_idx, withdrawals_idx)
            if idx is not None
        }
        if len(distinct_indices) <= 2:
            return None
        has_posting_column = any("posting" in header for header in normalized)
        has_dual_amount_columns = withdrawals_idx is not None or deposits_idx is not None
        if not has_posting_column and not has_dual_amount_columns:
            header_text = " ".join(normalized)
            if (
                "all transactions" in header_text
                or "date (utc)" in header_text
                or "end of day balance" in header_text
            ):
                return None
        return _ColumnMapping(
            date_index=date_idx,
            description_index=desc_idx,
            amount_index=amount_idx,
            deposits_index=deposits_idx,
            withdrawals_index=withdrawals_idx,
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

            if date_value:
                try:
                    current_date = _parse_bofa_date(date_value, period)
                except ValueError:
                    current_date = None
            if current_date is None:
                continue

            if not description:
                continue
            if _is_summary_row(description):
                continue

            amount = _resolve_amount(cells, mapping)
            money_in_value = _get_cell(cells, mapping.deposits_index)
            money_out_value = _get_cell(cells, mapping.withdrawals_index)

            if amount is None:
                # Only append if it's not a summary row (prevents Interest Charged text from being appended)
                if last_transaction is not None and not _is_summary_row(description):
                    appended = f"{last_transaction.merchant} {description.strip()}".strip()
                    last_transaction.merchant = appended
                    last_transaction.original_description = (
                        f"{last_transaction.original_description} {description.strip()}".strip()
                    )
                continue

            signed_amount = _BOFA_SIGN_CLASSIFIER.classify(
                abs(amount),
                description=description,
                money_in_value=money_in_value,
                money_out_value=money_out_value,
            )

            if signed_amount is None or signed_amount <= 0:
                continue

            # Clean up merchant name by removing PDF layout text
            merchant = description.strip()
            merchant_lower = merchant.lower()
            if "continued on next page" in merchant_lower:
                # Find and remove the text while preserving original case
                idx = merchant_lower.find("continued on next page")
                merchant = merchant[:idx].strip()
            elif "continued from previous page" in merchant_lower:
                idx = merchant_lower.find("continued from previous page")
                merchant = merchant[:idx].strip()

            txn = ExtractedTransaction(
                date=current_date,
                merchant=merchant.strip(),
                amount=signed_amount,
                original_description=description.strip(),
            )
            transactions.append(txn)
            last_transaction = txn

        return transactions

    def _extract_from_text(
        self,
        text: str,
        period: _StatementPeriod,
    ) -> list[ExtractedTransaction]:
        transactions: list[ExtractedTransaction] = []
        pattern = re.compile(r"(\d{2}/\d{2}/\d{2})\s+(.+?)\s+(-[$\d,\.]+)")
        for line in text.splitlines():
            match = pattern.search(line)
            if not match:
                continue
            date_str, description, amount_str = match.groups()
            try:
                txn_date = _parse_bofa_date(date_str, period)
                amount = abs(parse_amount(amount_str))
            except ValueError:
                continue

            signed_amount = _BOFA_SIGN_CLASSIFIER.classify(
                amount,
                description=description,
            )
            if signed_amount is None or signed_amount <= 0:
                desc_norm = normalize_token(description)
                if not amount_str.strip().startswith("-"):
                    continue
                if any(keyword in desc_norm for keyword in _BOFA_SIGN_CLASSIFIER.transfer_keywords):
                    continue
                if any(keyword in desc_norm for keyword in _BOFA_SIGN_CLASSIFIER.interest_keywords):
                    continue
                if any(
                    keyword in desc_norm for keyword in _BOFA_SIGN_CLASSIFIER.card_payment_keywords
                ):
                    continue
                signed_amount = amount

            transactions.append(
                ExtractedTransaction(
                    date=txn_date,
                    merchant=description.strip(),
                    amount=signed_amount,
                    original_description=description.strip(),
                )
            )
        return transactions


def _bofa_header_predicate(header: tuple[str, ...]) -> bool:
    # Require a multi-column header so single-column ledgers (e.g., Mercury)
    # do not satisfy BofA detection heuristics.
    if len([cell for cell in header if cell]) < 3:
        return False
    normalized = [cell.lower() for cell in header if cell]
    return any("date" in cell for cell in normalized) and any(
        "description" in cell for cell in normalized
    )


def _is_summary_row(value: str) -> bool:
    normalized = normalize_token(value)
    if normalized in _SUMMARY_ROW_KEYWORDS:
        return True
    if normalized.startswith("total") and (
        "payments" in normalized or "purchases" in normalized or "fees" in normalized
    ):
        return True
    if "interest charged" in normalized:
        return True
    if "total" in normalized and "for this period" in normalized:
        return True
    if normalized.endswith("for this period"):
        return True
    if "continued on next page" in normalized:
        return True
    if "continued from previous page" in normalized:
        return True
    return False


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
    credit_keywords = {
        "credit card",
        "visa",
        "mastercard",
        "payment due",
        "card services",
        "statement closing date",
        "minimum payment",
    }
    if any(keyword in lowered for keyword in credit_keywords):
        return "Bank of America Credit Card", "credit"
    if "checking" in lowered or "checking" in text:
        return "Bank of America Checking", "checking"
    return "Bank of America Credit Card", "credit"


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


def _get_cell(cells: Sequence[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(cells):
        return ""
    return cells[index].strip()


def _resolve_amount(cells: Sequence[str], mapping: _ColumnMapping) -> float | None:
    candidate = _get_cell(cells, mapping.amount_index)
    if candidate:
        return abs(parse_amount(candidate))
    withdraw = _get_cell(cells, mapping.withdrawals_index)
    if withdraw:
        return abs(parse_amount(withdraw))
    deposit = _get_cell(cells, mapping.deposits_index)
    if deposit:
        return abs(parse_amount(deposit))
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
