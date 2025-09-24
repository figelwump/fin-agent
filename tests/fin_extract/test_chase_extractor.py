from __future__ import annotations

from datetime import date

from fin_cli.fin_extract.extractors import detect_extractor
from fin_cli.fin_extract.extractors.chase import ChaseExtractor, _contains_keyword
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
        ("11/28/2024", "11/28/2024", "PAYMENTS AND OTHER CREDITS", "Payment", "0.00"),
        ("11/27/2024", "11/27/2024", "WHOLEFDS #10234", "Sale", "127.34"),
        ("11/26/2024", "11/26/2024", "AUTOMATIC PAYMENT", "Payment", "$1,500.00"),
    ]
    text = "Chase Card Services Statement October 2024"
    return PdfDocument(text=text, tables=[PdfTable(headers=headers, rows=rows)])


def _build_text_only_document() -> PdfDocument:
    text = """
    Chase Amazon Prime Visa Statement
    ACCOUNT ACTIVITY
    PAYMENTS AND OTHER CREDITS
    09/14 AUTOMATIC PAYMENT - THANK YOU -554.38
    PURCHASE
    09/15 WHOLEFDS #10234 127.34
    """
    return PdfDocument(text=text, tables=[])


def _build_duplicated_glyph_document() -> PdfDocument:
    text = """
    CChhaassee Amazon Prime Visa Statement
    AACCCCOOUUNNTT AACCTTIIVVIITTYY
    PAYMENTS AND OTHER CREDITS
    07/14 AUTOMATIC PAYMENT - THANK YOU -2,742.06
    PURCHASE
    07/17 GOOGLE *YouTubePremium g.co/helppay# CA 13.99
    """
    return PdfDocument(text=text, tables=[])


def test_chase_extractor_supports_document() -> None:
    document = _build_document()
    extractor = ChaseExtractor()
    assert extractor.supports(document)


def test_chase_extractor_extracts_transactions() -> None:
    document = _build_document()
    extractor = ChaseExtractor()
    result = extractor.extract(document)
    assert len(result.transactions) == 1
    grocery = result.transactions[0]
    assert grocery.date == date(2024, 11, 27)
    assert grocery.amount == -127.34  # sale should be negative
    assert grocery.original_description == "WHOLEFDS #10234"
    assert result.metadata.account_name == "Chase Account"


def test_detect_extractor_returns_chase() -> None:
    document = _build_document()
    extractor = detect_extractor(document)
    assert isinstance(extractor, ChaseExtractor)


def test_text_only_document_supported() -> None:
    document = _build_text_only_document()
    extractor = detect_extractor(document)
    assert isinstance(extractor, ChaseExtractor)
    result = extractor.extract(document)
    assert len(result.transactions) == 1
    assert result.transactions[0].merchant == "WHOLEFDS #10234"
    assert result.metadata.account_name == "Amazon Prime Visa"


def test_keyword_search_handles_duplicated_letters() -> None:
    assert _contains_keyword("CChhaassee", "chase")
    assert _contains_keyword("AACCCCOOUUNNTT AACCTTIIVVIITTYY", "account activity")


def test_document_with_duplicated_glyphs_supported() -> None:
    document = _build_duplicated_glyph_document()
    extractor = detect_extractor(document)
    assert isinstance(extractor, ChaseExtractor)
    result = extractor.extract(document)
    assert result.metadata.account_name == "Amazon Prime Visa"
    # Payment should be filtered as a credit; only the purchase remains.
    assert len(result.transactions) == 1
    txn = result.transactions[0]
    assert txn.merchant == "GOOGLE *YouTubePremium g.co/helppay# CA"
    assert txn.amount == -13.99
