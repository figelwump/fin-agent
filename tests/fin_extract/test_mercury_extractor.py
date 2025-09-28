from __future__ import annotations

from datetime import date

from fin_cli.fin_extract.extractors.mercury import MercuryExtractor
from fin_cli.fin_extract.parsers.pdf_loader import PdfDocument, PdfTable


def _build_document() -> PdfDocument:
    text = """
    Mercury Business Checking Statement
    Statement Period: August 1, 2024 - August 31, 2024
    Account ending 1234
    """
    table = PdfTable(
        headers=("Date", "Description", "Money In", "Money Out", "Balance"),
        rows=[
            ("08/03/2024", "Stripe Payout", "$5,000.00", "", "12,000.00"),
            ("08/05/2024", "AWS Marketplace", "", "320.45", "11,679.55"),
            ("08/06/2024", "Team Lunch", "", "145.20", "11,534.35"),
            ("", "San Francisco, CA", "", "", ""),
        ],
    )
    return PdfDocument(text=text, tables=[table])


def test_mercury_supports_document() -> None:
    document = _build_document()
    extractor = MercuryExtractor()
    assert extractor.supports(document)


def test_mercury_extracts_transactions() -> None:
    document = _build_document()
    extractor = MercuryExtractor()
    result = extractor.extract(document)

    assert result.metadata.institution == "Mercury"
    assert result.metadata.account_type == "checking"
    assert result.metadata.account_name.endswith("1234")
    assert result.metadata.start_date == date(2024, 8, 1)
    assert result.metadata.end_date == date(2024, 8, 31)

    assert len(result.transactions) == 2

    first = result.transactions[0]
    assert first.merchant == "AWS Marketplace"
    assert first.amount == 320.45

    lunch = result.transactions[-1]
    assert lunch.amount == 145.2
    assert "San Francisco" in lunch.merchant
