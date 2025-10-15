from __future__ import annotations

from fin_cli.fin_extract.declarative import _expand_single_column_table
from fin_cli.fin_extract.parsers.pdf_loader import PdfTable


def test_expand_single_column_table_mercury_like_blob() -> None:
    table = PdfTable(
        headers=("All Transactions /",),
        rows=(
            ("Date (UTC) Description Type Amount End of Day Balance",),
            ("Sep 01 Savings Interest \uea03Interest Payment $87.74 $24,795.25",),
            ("Sep 02 UBS FINSVC \uea01 ACH In $30,000.00",),
            ("Transfer to Cash Sending Apps \uea03Transfer Out –$470.00",),
            ("Sep 02 APPLECARD GSBANK \uea02 ACH Pull –$4,982.03 $33,632.04",),
            ("Total $40,640.35",),
        ),
    )

    normalized = _expand_single_column_table(table)
    assert normalized is not None

    assert normalized.headers == ("Date", "Description", "Type", "Amount", "Balance")
    assert len(normalized.rows) == 4

    first = normalized.rows[0]
    assert first[0] == "Sep 01"
    assert first[1] == "Savings Interest"
    assert first[2] == "Interest Payment"
    assert first[3] == "$87.74"

    transfer = normalized.rows[2]
    assert transfer[0] == "Sep 02"
    assert transfer[1].startswith("Transfer to Cash Sending Apps")
    assert transfer[2] == "Transfer Out"
    assert transfer[3] in {"–$470.00", "-$470.00"}
