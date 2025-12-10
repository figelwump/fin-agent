from __future__ import annotations

import json
from pathlib import Path

import pytest

from fin_cli.fin_extract.asset_contract import validate_asset_payload

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "asset_tracking"


@pytest.mark.parametrize("fixture", ["ubs_statement", "schwab_statement", "mercury_statement"])
def test_fixtures_are_valid(fixture: str) -> None:
    payload = json.loads((FIXTURE_ROOT / f"{fixture}.json").read_text())
    assert validate_asset_payload(payload) == []


def test_invalid_payload_reports_errors(tmp_path: Path) -> None:
    payload = {
        "document": {"document_hash": "x", "broker": "Test", "as_of_date": "2025-01-01"},
        "instruments": [{"name": "Bad", "symbol": "BAD", "currency": "US"}],
        "holdings": [{"account_key": "ACC", "symbol": "BAD"}],
        "holding_values": [
            {"account_key": "ACC", "symbol": "BAD", "as_of_date": "bad-date", "quantity": -1}
        ],
    }
    errors = validate_asset_payload(payload)
    assert any("currency" in err for err in errors)
    assert any("as_of_date" in err for err in errors)
    assert any("non-negative" in err for err in errors)
