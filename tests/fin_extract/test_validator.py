from __future__ import annotations

from copy import deepcopy
from datetime import date
from fin_cli.fin_extract.extractors.bofa import BankOfAmericaExtractor
from fin_cli.fin_extract.extractors.mercury import MercuryExtractor
from fin_cli.fin_extract.parsers.pdf_loader import PdfTable, PdfDocument
from fin_cli.fin_extract.types import ExtractedTransaction, ExtractionResult, StatementMetadata
from fin_cli.fin_extract.validator import validate_extraction


def _bofa_document() -> PdfDocument:
    return PdfDocument(
        text="Statement Period: 09/01/2025 - 09/30/2025",
        tables=[
            PdfTable(
                headers=(
                    "Date",
                    "Description",
                    "Withdrawals and Other Debits",
                    "Deposits and Other Credits",
                ),
                rows=[
                    ("09/03", "Trader Joe's #1234", "-150.20", "", ""),
                    ("09/05", "Stripe Payout", "", "2500.00", ""),
                ],
            )
        ],
    )


def _mercury_document() -> PdfDocument:
    return PdfDocument(
        text="Statement Period: September 1, 2025 - September 30, 2025",
        tables=[
            PdfTable(
                headers=("Date", "Description", "Money In", "Money Out", "Balance"),
                rows=[
                    ("09/07/2025", "AWS Marketplace", "", "320.45", ""),
                    ("09/09/2025", "Team Lunch", "", "145.20", ""),
                    ("", "San Mateo, CA", "", "", ""),
                ],
            )
        ],
    )


def _load_bofa_result() -> ExtractionResult:
    return BankOfAmericaExtractor().extract(_bofa_document())


def _load_mercury_result() -> ExtractionResult:
    return MercuryExtractor().extract(_mercury_document())


def test_validator_accepts_bofa_sample() -> None:
    result = _load_bofa_result()

    report = validate_extraction(result)

    assert report.ok
    assert {issue.code for issue in report.issues} <= {"missing_period"}


def test_validator_accepts_mercury_sample() -> None:
    result = _load_mercury_result()

    report = validate_extraction(result)

    assert report.ok
    assert {issue.code for issue in report.issues} <= {"missing_period"}


def test_validator_flags_summary_row_leak() -> None:
    base = _load_bofa_result()
    mutated = deepcopy(base)
    mutated.transactions.append(
        ExtractedTransaction(
            date=date(2025, 9, 30),
            merchant="Total fees for this period",
            amount=25.0,
            original_description="Total fees for this period",
        )
    )

    report = validate_extraction(mutated)

    assert not report.ok
    codes = {issue.code for issue in report.issues}
    assert "bofa_summary_row" in codes


def test_validator_flags_mercury_credit_row() -> None:
    base = _load_mercury_result()
    mutated = deepcopy(base)
    mutated.transactions.append(
        ExtractedTransaction(
            date=date(2025, 5, 12),
            merchant="AngelList ACH In",
            amount=1000.0,
            original_description="AngelList ACH In",
        )
    )

    report = validate_extraction(mutated)

    assert not report.ok
    codes = {issue.code for issue in report.issues}
    assert "mercury_non_spend" in codes
