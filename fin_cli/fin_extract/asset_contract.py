"""Validation helpers for the asset ingestion contract.

Used by fin-extract asset commands and tests to ensure broker extractors emit
LLM-friendly normalized JSON before passing into fin-edit for persistence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any


def _assert_iso_date(value: str) -> None:
    date.fromisoformat(value)


def _assert_optional_iso_datetime(value: str | None) -> None:
    if value is None:
        return
    if value.endswith("Z"):
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        datetime.fromisoformat(value)


def _validate_currency(value: str) -> bool:
    return bool(value) and len(value) == 3 and value.isupper()


def validate_asset_payload(payload: Mapping[str, Any]) -> list[str]:
    """Return a list of validation errors (empty list means valid)."""

    errors: list[str] = []

    # Top-level keys
    expected_keys = {"document", "instruments", "holdings", "holding_values"}
    if set(payload.keys()) != expected_keys:
        errors.append(f"Payload must include keys {sorted(expected_keys)}")
        return errors

    # Document
    doc = payload.get("document", {})
    for key in ("document_hash", "broker", "as_of_date"):
        if not doc.get(key):
            errors.append(f"document.{key} is required")
    try:
        _assert_iso_date(doc.get("as_of_date", ""))
    except Exception as exc:  # pragma: no cover - defensive
        errors.append(f"document.as_of_date invalid: {exc}")
    if doc.get("period_end_date"):
        try:
            _assert_iso_date(doc["period_end_date"])
        except Exception as exc:
            errors.append(f"document.period_end_date invalid: {exc}")

    # Instruments
    instruments = payload.get("instruments") or []
    if not isinstance(instruments, Sequence) or not instruments:
        errors.append("instruments must be a non-empty array")
    symbols: set[str] = set()
    identifiers_present = False
    for inst in instruments:
        if not inst.get("name"):
            errors.append("instrument.name is required")
        currency = inst.get("currency", "")
        if not _validate_currency(currency):
            errors.append(f"instrument.currency invalid: {currency}")
        if inst.get("vehicle_type") is not None and not isinstance(inst.get("vehicle_type"), str):
            errors.append("instrument.vehicle_type must be a string when provided")
        symbol = inst.get("symbol")
        if symbol:
            if symbol in symbols:
                errors.append(f"duplicate instrument symbol '{symbol}'")
            symbols.add(symbol)
        identifiers = inst.get("identifiers") or {}
        if identifiers:
            identifiers_present = True
    if symbols and not identifiers_present:
        # Not an error, but warn via errors list for downstream clarity.
        pass

    # Holdings
    holdings = payload.get("holdings") or []
    holding_pairs: set[tuple[str, str]] = set()
    account_keys: set[str] = set()
    for holding in holdings:
        account_key = holding.get("account_key")
        symbol = holding.get("symbol")
        if not account_key or not symbol:
            errors.append("holding requires account_key and symbol")
            continue
        account_keys.add(account_key)
        pair = (account_key, symbol)
        if pair in holding_pairs:
            errors.append(f"duplicate holding for {account_key}/{symbol}")
        holding_pairs.add(pair)
        status = holding.get("status", "active")
        if status not in {"active", "closed"}:
            errors.append(f"holding.status invalid: {status}")
        if holding.get("position_side") not in {None, "long", "short"}:
            errors.append(f"holding.position_side invalid: {holding.get('position_side')}")

    # Holding values
    holding_values = payload.get("holding_values") or []
    value_keys: set[tuple[str, str, str, str]] = set()
    for value in holding_values:
        account_key = value.get("account_key")
        symbol = value.get("symbol")
        if not account_key or not symbol:
            errors.append("holding_value requires account_key and symbol")
            continue
        if account_key not in account_keys:
            errors.append(f"holding_value references unknown account_key {account_key}")
        if symbol not in symbols:
            errors.append(f"holding_value references unknown symbol {symbol}")
        try:
            _assert_iso_date(value.get("as_of_date", ""))
        except Exception as exc:
            errors.append(f"holding_value.as_of_date invalid: {exc}")
        try:
            _assert_optional_iso_datetime(value.get("as_of_datetime"))
        except Exception as exc:
            errors.append(f"holding_value.as_of_datetime invalid: {exc}")

        quantity = value.get("quantity")
        try:
            qty_float = float(quantity)
        except Exception:
            errors.append(f"quantity invalid: {quantity}")
            continue
        if qty_float < 0:
            errors.append("quantity must be non-negative (use position_side for shorts)")

        price = value.get("price")
        market_value = value.get("market_value")
        if price is None and market_value is None:
            errors.append("holding_value requires price or market_value")
        if price is not None and price < 0:
            errors.append("price must be non-negative")
        if market_value is not None and market_value < 0:
            errors.append("market_value must be non-negative")
        if price is not None and market_value is not None:
            if not math.isclose(market_value, qty_float * float(price), rel_tol=1e-6, abs_tol=0.05):
                errors.append("market_value does not match quantity*price")

        valuation_currency = value.get("valuation_currency", "USD")
        if not _validate_currency(valuation_currency):
            errors.append(f"valuation_currency invalid: {valuation_currency}")
        if "fx_rate_used" in value and float(value.get("fx_rate_used", 0)) <= 0:
            errors.append("fx_rate_used must be positive")

        key = (account_key, symbol, str(value.get("as_of_date")), value.get("source", "statement"))
        if key in value_keys:
            errors.append(
                f"duplicate holding_value for {account_key}/{symbol}/{value.get('as_of_date')} source={value.get('source')}"
            )
        value_keys.add(key)

    for pair in holding_pairs:
        if not any(vk[:2] == pair for vk in value_keys):
            errors.append(f"holding {pair[0]}/{pair[1]} missing valuation rows")

    return errors
