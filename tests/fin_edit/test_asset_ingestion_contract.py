"""Golden tests for asset ingestion fixtures.

These fixtures pre-define the normalized JSON contract that future parsers
must emit before we wire broker-specific extraction. The tests validate
structure, referential integrity, and basic numeric consistency so changes
fail fast and keep downstream CLI work deterministic for LLMs.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "asset_tracking"
BROKER_FIXTURES = ["ubs_statement", "schwab_statement", "mercury_statement"]
ALLOWED_SOURCES = {"statement", "upload", "api", "manual"}
ALLOWED_VEHICLE_TYPES = {
    "stock",
    "ETF",
    "mutual_fund",
    "bond",
    "MMF",
    "fund_LP",
    "note",
    "option",
    "crypto",
    None,
}


def _load_payload(name: str) -> dict:
    path = FIXTURE_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing asset ingestion fixture: {path}")
    return json.loads(path.read_text())


def _assert_iso_date(value: str) -> None:
    date.fromisoformat(value)


def _assert_optional_iso_datetime(value: str | None) -> None:
    if value is None:
        return
    # Allow trailing Z for UTC which sqlite strftime can parse after normalization.
    if value.endswith("Z"):
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        datetime.fromisoformat(value)


def test_asset_ingestion_fixtures_present() -> None:
    for name in BROKER_FIXTURES:
        assert (FIXTURE_ROOT / f"{name}.json").exists()


@pytest.mark.parametrize("fixture_name", BROKER_FIXTURES)
def test_asset_ingestion_contract_is_well_formed(fixture_name: str) -> None:
    payload = _load_payload(fixture_name)

    # Document block
    assert set(payload.keys()) == {"document", "instruments", "holdings", "holding_values"}
    document = payload["document"]
    for key in ("document_hash", "broker", "as_of_date"):
        assert key in document and isinstance(document[key], str) and document[key]
    _assert_iso_date(document["as_of_date"])
    if "period_end_date" in document:
        _assert_iso_date(document["period_end_date"])

    # Instrument definitions
    instruments = payload["instruments"]
    assert instruments, "fixtures should include at least one instrument"
    symbols: set[str] = set()
    identifiers_present = False
    for instrument in instruments:
        assert instrument["name"]
        assert instrument.get("currency", "").isupper() and len(instrument["currency"]) == 3
        assert instrument.get("vehicle_type") in ALLOWED_VEHICLE_TYPES
        if "symbol" in instrument and instrument["symbol"]:
            symbol = instrument["symbol"]
            assert symbol not in symbols
            symbols.add(symbol)
        identifiers = instrument.get("identifiers")
        if identifiers is not None:
            assert isinstance(identifiers, dict)
            identifiers_present = identifiers_present or bool(identifiers)
    assert identifiers_present, "at least one identifier helps canonical mapping during tests"

    # Holdings reference instruments and account keys
    holdings = payload["holdings"]
    assert holdings, "fixtures should define holdings to tie accounts to instruments"
    holding_pairs: set[tuple[str, str]] = set()
    account_keys: set[str] = set()
    for holding in holdings:
        account_key = holding["account_key"]
        symbol = holding["symbol"]
        account_keys.add(account_key)
        assert symbol in symbols, f"holding references unknown symbol {symbol}"
        status = holding.get("status", "active")
        assert status in {"active", "closed"}
        if "position_side" in holding:
            assert holding["position_side"] in {"long", "short"}
        pair = (account_key, symbol)
        assert pair not in holding_pairs, "duplicate holding entries are not expected in fixtures"
        holding_pairs.add(pair)

    # Holding values align to holdings + document
    holding_values = payload["holding_values"]
    assert holding_values, "fixtures need valuations to drive analyzer snapshots"
    value_keys: set[tuple[str, str, str, str]] = set()
    values_per_pair: dict[tuple[str, str], int] = {}
    for value in holding_values:
        account_key = value["account_key"]
        symbol = value["symbol"]
        assert account_key in account_keys
        assert symbol in symbols
        _assert_iso_date(value["as_of_date"])
        _assert_optional_iso_datetime(value.get("as_of_datetime"))
        assert value.get("document_hash") == document["document_hash"]

        source = value.get("source", "statement")
        assert source in ALLOWED_SOURCES

        quantity = float(value["quantity"])
        assert quantity >= 0
        price = value.get("price")
        market_value = value.get("market_value")
        assert price is not None or market_value is not None
        if price is not None:
            assert float(price) >= 0
        if market_value is not None:
            assert float(market_value) >= 0
        if price is not None and market_value is not None:
            assert math.isclose(
                float(market_value), float(quantity) * float(price), rel_tol=1e-6, abs_tol=0.05
            )

        valuation_currency = value.get("valuation_currency", "USD")
        assert valuation_currency.isupper() and len(valuation_currency) == 3
        if "fx_rate_used" in value:
            assert float(value["fx_rate_used"]) > 0

        key = (account_key, symbol, value["as_of_date"], source)
        assert key not in value_keys, "duplicate valuation rows violate UNIQUE constraint contract"
        value_keys.add(key)
        values_per_pair[key[:2]] = values_per_pair.get(key[:2], 0) + 1

    # Every holding should have at least one valuation to keep tests meaningful.
    for pair in holding_pairs:
        assert values_per_pair.get(pair, 0) >= 1
