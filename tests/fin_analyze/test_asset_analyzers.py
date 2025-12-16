from __future__ import annotations

import pytest

from fin_cli.fin_analyze.analyzers import (
    allocation_snapshot,
    cash_mix,
    concentration_risk,
    portfolio_trend,
    rebalance_suggestions,
)


@pytest.fixture()
def asset_window(window_factory):
    return window_factory("fall_2025", "2025-09-01", "2025-12-01")


def test_allocation_snapshot_reports_classes(load_analysis_dataset, analysis_context, asset_window):
    load_analysis_dataset("assets_portfolio")
    context = analysis_context(asset_window, None, {}, compare=False, threshold=0.1)

    result = allocation_snapshot.analyze(context)
    payload = result.json_payload

    assert pytest.approx(payload["total_value"], rel=1e-4) == 36000.0
    classes = {(row["main_class"], row["sub_class"]) for row in payload["allocation_by_class"]}
    assert ("cash", "money market") in classes
    assert ("equities", "US equity") in classes


def test_portfolio_trend_tracks_growth(load_analysis_dataset, analysis_context, asset_window):
    load_analysis_dataset("assets_portfolio")
    context = analysis_context(asset_window, None, {}, compare=False, threshold=0.1)

    result = portfolio_trend.analyze(context)
    payload = result.json_payload

    assert pytest.approx(payload["current_value"], rel=1e-4) == 36000.0
    assert payload["series"][0]["market_value"] == pytest.approx(30000.0, rel=1e-4)
    assert payload["change_pct"] is not None


def test_concentration_risk_flags_top_holdings(
    load_analysis_dataset, analysis_context, asset_window
):
    load_analysis_dataset("assets_portfolio")
    context = analysis_context(asset_window, None, {"top_n": 2}, compare=False, threshold=0.1)

    result = concentration_risk.analyze(context)
    payload = result.json_payload

    top = payload["top_holdings"][0]
    assert top["symbol"] == "AAPL"
    assert top["weight_pct"] == pytest.approx(41.6666, rel=1e-2)
    assert payload["hhi"] > 0


def test_cash_mix_calculates_runway(load_analysis_dataset, analysis_context, asset_window):
    load_analysis_dataset("assets_portfolio")
    context = analysis_context(asset_window, None, {}, compare=False, threshold=0.1)

    result = cash_mix.analyze(context)
    payload = result.json_payload

    assert payload["cash_total"] == pytest.approx(6000.0, rel=1e-4)
    assert payload["runway_months"] == pytest.approx(2.43, rel=1e-2)


def test_rebalance_suggestions_uses_targets(load_analysis_dataset, analysis_context, asset_window):
    load_analysis_dataset("assets_portfolio")
    context = analysis_context(asset_window, None, {}, compare=False, threshold=0.1)

    result = rebalance_suggestions.analyze(context)
    suggestions = {
        f"{row['main_class']}/{row['sub_class']}": row for row in result.json_payload["suggestions"]
    }

    equities = suggestions.get("equities/US equity")
    assert equities is not None
    assert equities["delta_pct"] > 0  # underweight vs target
    assert suggestions.get("cash/money market") is not None
