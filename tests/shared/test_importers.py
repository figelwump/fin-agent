from __future__ import annotations

import io
from pathlib import Path

import pytest

from fin_cli.shared import models
from fin_cli.shared.importers import (
    CSVImportError,
    EnrichedCSVTransaction,
    load_enriched_transactions,
    load_enriched_transactions_from_stream,
)


def _make_row(**overrides: str) -> dict[str, str]:
    row = {
        "date": "2025-09-01",
        "merchant": "Amazon",
        "amount": "-42.10",
        "original_description": "AMAZON",
        "account_name": "Prime Visa",
        "institution": "Chase",
        "account_type": "credit",
        "last_4_digits": "6033",
        "category": "Shopping",
        "subcategory": "Online",
        "confidence": "0.8",
        "account_key": "custom-key",
        "fingerprint": "abc123",
    }
    row.update({k: v for k, v in overrides.items() if v is not None})
    return row


def test_load_enriched_transactions_handles_bom(tmp_path: Path) -> None:
    csv_path = tmp_path / "enriched.csv"
    headers = [
        "date",
        "merchant",
        "amount",
        "original_description",
        "account_name",
        "institution",
        "account_type",
        "last_4_digits",
        "category",
        "subcategory",
        "confidence",
        "account_key",
        "fingerprint",
    ]
    values = [
        "2025-09-01",
        "Amazon   Prime",
        "-42.10",
        "AMZN",
        "Prime Visa",
        "Chase",
        "credit",
        "6033",
        "Shopping",
        "Online",
        "",
        "",
        "",
    ]
    csv_path.write_text(
        "\ufeff" + ",".join(headers) + "\n" + ",".join(values) + "\n", encoding="utf-8"
    )

    transactions = load_enriched_transactions(csv_path)

    assert len(transactions) == 1
    txn = transactions[0]
    assert isinstance(txn, EnrichedCSVTransaction)
    assert txn.merchant == "Amazon Prime"
    # Amount should be normalized to positive
    assert txn.amount == pytest.approx(42.10)
    # Confidence should fall back to default since column was blank
    assert txn.confidence == pytest.approx(1.0)
    # Account key should be recomputed from institution/type/last4
    expected_key = models.compute_account_key_v2(
        institution="Chase",
        account_type="credit",
        last_4_digits="6033",
    )
    assert txn.account_key == expected_key


def test_load_enriched_transactions_missing_column_errors(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("date,merchant,amount\n2025-09-01,Amazon,-10\n", encoding="utf-8")

    with pytest.raises(CSVImportError) as excinfo:
        load_enriched_transactions(csv_path)

    assert "Missing required" in str(excinfo.value)


def test_load_enriched_transactions_parses_metadata_as_raw_when_invalid_json() -> None:
    headers = ",".join(list(_make_row().keys()) + ["merchant_metadata"])
    values = ",".join(list(_make_row().values()) + ["{not json"])
    stream = io.StringIO(headers + "\n" + values + "\n")

    [txn] = load_enriched_transactions_from_stream(stream, source_name="stream")

    assert isinstance(txn.merchant_metadata, str)
    assert txn.merchant_metadata == "{not json"


def test_load_enriched_transactions_rejects_unsupported_columns() -> None:
    headers = list(_make_row().keys()) + ["unexpected"]
    values = list(_make_row().values()) + ["value"]
    stream = io.StringIO(",".join(headers) + "\n" + ",".join(values))

    with pytest.raises(CSVImportError) as excinfo:
        load_enriched_transactions_from_stream(stream, source_name="stream")

    assert "Unsupported column" in str(excinfo.value)
