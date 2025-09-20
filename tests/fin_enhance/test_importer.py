from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fin_cli.fin_enhance.importer import CSVImportError, load_csv_transactions


def test_load_csv_transactions(tmp_path: Path) -> None:
    csv_path = tmp_path / "transactions.csv"
    csv_path.write_text(
        "date,merchant,amount,original_description,account_id\n"
        "2024-11-27,WHOLEFDS #10234,-127.34,WHOLEFDS #10234,1\n",
        encoding="utf-8",
    )
    result = load_csv_transactions(csv_path)
    assert len(result) == 1
    txn = result[0]
    assert txn.date == date(2024, 11, 27)
    assert txn.merchant == "WHOLEFDS #10234"
    assert txn.amount == -127.34
    assert txn.account_id == 1


def test_load_csv_transactions_missing_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(CSVImportError):
        load_csv_transactions(csv_path)
