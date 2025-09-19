from __future__ import annotations

from datetime import date

from fin_cli.fin_extract.extractors import detect_extractor
from fin_cli.fin_extract.extractors.chase import ChaseExtractor
from fin_cli.fin_extract.parsers.pdf_loader import PdfDocument, PdfTable


def _build_document() -> PdfDocument:
    headers = (
        "Transaction Date",
        "Post Date",
        "Description",
        "Type",
        "Amount",
    )
    rows = [
        ("11/27/2024", "11/27/2024", "WHOLEFDS #10234", "Sale", "127.34"),
        ("11/26/2024", "11/26/2024", "AUTOMATIC PAYMENT", "Payment", "$1,500.00"),
    ]
    return PdfDocument(text="Chase Card Services Statement", tables=[PdfTable(headers=headers, rows=rows)])


def test_chase_extractor_supports_document() -> None:
    document = _build_document()
    extractor = ChaseExtractor()
    assert extractor.supports(document)


def test_chase_extractor_extracts_transactions() -> None:
    document = _build_document()
    extractor = ChaseExtractor()
    result = extractor.extract(document)
    assert len(result.transactions) == 2
    grocery, payment = result.transactions
    assert grocery.date == date(2024, 11, 27)
    assert grocery.amount == -127.34  # sale should be negative
    assert payment.amount == 1500.0  # payment should remain positive


def test_detect_extractor_returns_chase() -> None:
    document = _build_document()
    extractor = detect_extractor(document)
    assert isinstance(extractor, ChaseExtractor)
