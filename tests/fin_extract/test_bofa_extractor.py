from __future__ import annotations

from datetime import date
from fin_cli.fin_extract.extractors.bofa import BankOfAmericaExtractor
from fin_cli.fin_extract.declarative import DeclarativeExtractor, load_spec
from fin_cli.fin_extract.parsers.pdf_loader import PdfDocument, PdfTable


def _build_document() -> PdfDocument:
    text = """
    Bank of America Advantage Banking Statement
    Statement Period: 08/01/2024 - 08/31/2024
    """
    tables = [
        PdfTable(
            headers=(
                "Date",
                "Description",
                "Withdrawals and Other Debits",
                "Deposits and Other Credits",
                "Balance",
            ),
            rows=[
                ("08/02", "Rent Payment", "2,500.00", "", "12,000.00"),
                ("", "ACH Transfer to Landlord", "", "", ""),
                ("08/05", "Stripe Payout", "", "3,200.15", "15,200.15"),
            ],
        ),
        PdfTable(
            headers=("Date", "Description", "Amount"),
            rows=[
                ("08/08", "ATM Withdrawal", "-200.00"),
                ("08/10", "Café Coffee", "$12.50"),
            ],
        ),
    ]
    return PdfDocument(text=text, tables=tables)


def test_bofa_supports_document() -> None:
    document = _build_document()
    extractor = BankOfAmericaExtractor()
    assert extractor.supports(document)


def test_bofa_extracts_transactions() -> None:
    document = _build_document()
    extractor = BankOfAmericaExtractor()
    result = extractor.extract(document)

    assert result.metadata.institution == "Bank of America"
    assert result.metadata.account_type == "checking"
    assert result.metadata.account_name == "BofA Advantage Checking"
    assert result.metadata.start_date == date(2024, 8, 1)
    assert result.metadata.end_date == date(2024, 8, 31)

    assert len(result.transactions) == 2

    rent = result.transactions[0]
    assert rent.date == date(2024, 8, 2)
    assert rent.amount == 2500.0
    assert rent.merchant.endswith("ACH Transfer to Landlord")
    # Continuation row should append to the prior description/original.
    assert rent.original_description.endswith("ACH Transfer to Landlord")

    coffee = result.transactions[-1]
    assert coffee.amount == 12.5
    assert coffee.merchant == "Café Coffee"

    assert all(txn.amount > 0 for txn in result.transactions)


def test_bofa_bundled_spec_parity() -> None:
    document = _build_document()

    python_result = BankOfAmericaExtractor().extract(document)
    spec = load_spec("fin_cli/fin_extract/bundled_specs/bofa.yaml")
    declarative_result = DeclarativeExtractor(spec).extract(document)

    assert len(python_result.transactions) == len(declarative_result.transactions)

    python_rows = {
        (txn.date, txn.merchant, txn.amount) for txn in python_result.transactions
    }
    declarative_rows = {
        (txn.date, txn.merchant, txn.amount) for txn in declarative_result.transactions
    }
    assert python_rows == declarative_rows

    assert python_result.metadata.account_type == declarative_result.metadata.account_type
