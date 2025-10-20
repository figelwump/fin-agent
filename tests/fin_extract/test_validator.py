from __future__ import annotations

from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from fin_cli.fin_extract.extractors.bofa import BankOfAmericaExtractor
from fin_cli.fin_extract.extractors.mercury import MercuryExtractor
from fin_cli.fin_extract.parsers.pdf_loader import load_pdf_document_with_engine
from fin_cli.fin_extract.types import ExtractedTransaction, ExtractionResult, StatementMetadata
from fin_cli.fin_extract.validator import validate_extraction


def _load_bofa_result(pdf_name: str) -> ExtractionResult:
    pytest.importorskip("pdfplumber")
    pdf_path = Path("statements/bofa") / pdf_name
    document = load_pdf_document_with_engine(pdf_path, "pdfplumber")
    return BankOfAmericaExtractor().extract(document)


def _load_mercury_result(pdf_name: str) -> ExtractionResult:
    pytest.importorskip("pdfplumber")
    pdf_path = Path("statements/mercury") / pdf_name
    document = load_pdf_document_with_engine(pdf_path, "pdfplumber")
    return MercuryExtractor().extract(document)


def test_validator_accepts_bofa_sample() -> None:
    result = _load_bofa_result("eStmt_2025-09-22.pdf")

    report = validate_extraction(result)

    assert report.ok
    assert {issue.code for issue in report.issues} <= {"missing_period"}


def test_validator_accepts_mercury_sample() -> None:
    result = _load_mercury_result("vishal-kapur-and-sneha-kapur-2550-monthly-statement-2025-05.pdf")

    report = validate_extraction(result)

    assert report.ok
    assert {issue.code for issue in report.issues} <= {"missing_period"}


def test_validator_flags_summary_row_leak() -> None:
    base = _load_bofa_result("eStmt_2025-09-22.pdf")
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
    base = _load_mercury_result("vishal-kapur-and-sneha-kapur-2550-monthly-statement-2025-05.pdf")
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
