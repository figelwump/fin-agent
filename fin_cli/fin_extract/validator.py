"""Lightweight extraction validator with issuer-specific heuristics.

The validator is intentionally simple: it consumes an ``ExtractionResult`` and
emits a list of issues that downstream tooling (CLI dev commands, CI checks,
agents) can surface. The heuristics here focus on common regression vectors
observed while porting Bank of America and Mercury extractors to the
declarative runtime:

* accidental inclusion of summary/total rows (should be filtered out)
* missing statement period metadata after Docling/pdfplumber parsing
* spend-only enforcement (credits, payments, transfers must be excluded)

Future issuers can plug into the same structure by adding new helpers similar
to ``_validate_bofa`` and ``_validate_mercury``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import ExtractedTransaction, ExtractionResult
from .utils.amounts import normalize_token

_SUMMARY_KEYWORDS = {
    "total",
    "balance",
    "summary",
    "fees",
    "transactions continued",
    "payments and other credits",
    "charges and purchases",
    "purchases and adjustments",
    "interest charged",
    "continued on next page",
    "continued from previous page",
}

_BOFA_CREDIT_KEYWORDS = {
    "credit",
    "payment",
    "deposit",
    "refund",
    "ach in",
    "transfer in",
    "interest",
}

_MERCURY_CREDIT_KEYWORDS = {
    "ach in",
    "interest",
    "deposit",
    "transfer in",
}

_TRANSFER_KEYWORDS = {
    "transfer",
    "atm withdrawal",
    "cash sending apps",
    "mercury checking",
}


@dataclass(slots=True)
class ValidationIssue:
    """Single validation finding."""

    code: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass(slots=True)
class ValidationReport:
    """Aggregate report returned by ``validate_extraction``."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no error-level issues were recorded."""

        return all(issue.severity != "error" for issue in self.issues)

    def add(self, code: str, message: str, *, severity: str = "error") -> None:
        self.issues.append(ValidationIssue(code=code, message=message, severity=severity))


def validate_extraction(result: ExtractionResult) -> ValidationReport:
    """Validate a single extraction result and emit heuristic findings."""

    report = ValidationReport()

    _validate_common_rules(result, report)

    institution_norm = result.metadata.institution.strip().lower()
    if "bank of america" in institution_norm or "bofa" in institution_norm:
        _validate_bofa(result, report)
    if "mercury" in institution_norm:
        _validate_mercury(result, report)

    return report


def _validate_common_rules(result: ExtractionResult, report: ValidationReport) -> None:
    """Checks that apply to every extraction."""

    if not result.transactions:
        report.add(
            "no_transactions",
            "No transactions were produced; verify spend rows were not dropped. "
            "This is treated as a warning to allow legitimately zero-spend statements.",
            severity="warning",
        )

    for txn in result.transactions:
        if txn.amount <= 0:
            report.add(
                "non_positive_amount",
                f"Transaction '{txn.merchant}' on {txn.date.isoformat()} has a non-positive amount ({txn.amount}).",
            )

    metadata = result.metadata
    if metadata.start_date is None or metadata.end_date is None:
        report.add(
            "missing_period",
            "Statement period could not be inferred (start/end date missing).",
            severity="warning",
        )
    elif metadata.start_date > metadata.end_date:
        report.add(
            "invalid_period",
            "Statement start date is after end date, check period inference.",
        )


def _validate_bofa(result: ExtractionResult, report: ValidationReport) -> None:
    """Bank of America specific heuristics."""

    account_type = result.metadata.account_type.lower()
    if "credit" not in account_type:
        report.add(
            "bofa_account_type",
            f"Expected credit account type for Bank of America statement, got '{result.metadata.account_type}'.",
            severity="warning",
        )

    for txn in result.transactions:
        if _contains_summary_keyword(txn):
            report.add(
                "bofa_summary_row",
                f"Summary row leaked into output: '{txn.merchant}'.",
            )

        if _looks_like_credit(txn):
            report.add(
                "bofa_non_spend",
                f"Non-spend row detected (keywords indicate credit/refund): '{txn.merchant}'.",
            )


def _validate_mercury(result: ExtractionResult, report: ValidationReport) -> None:
    """Mercury specific heuristics."""

    account_type = result.metadata.account_type.lower()
    if not any(token in account_type for token in ("checking", "savings")):
        report.add(
            "mercury_account_type",
            f"Expected checking or savings account type for Mercury statement, got '{result.metadata.account_type}'.",
            severity="warning",
        )

    for txn in result.transactions:
        normalized = normalize_token(txn.merchant)
        if _contains_summary_keyword(txn):
            report.add(
                "mercury_summary_row",
                f"Summary row leaked into output: '{txn.merchant}'.",
            )

        if any(keyword in normalized for keyword in _MERCURY_CREDIT_KEYWORDS | _TRANSFER_KEYWORDS):
            report.add(
                "mercury_non_spend",
                f"Non-spend row detected (looks like credit/transfer): '{txn.merchant}'.",
            )


def _contains_summary_keyword(txn: ExtractedTransaction) -> bool:
    merchant_norm = normalize_token(txn.merchant)
    original_norm = normalize_token(txn.original_description)
    return any(
        keyword in merchant_norm or keyword in original_norm for keyword in _SUMMARY_KEYWORDS
    )


def _looks_like_credit(txn: ExtractedTransaction) -> bool:
    normalized = normalize_token(txn.merchant)
    original_norm = normalize_token(txn.original_description)
    return any(
        keyword in normalized or keyword in original_norm for keyword in _BOFA_CREDIT_KEYWORDS
    )
