from __future__ import annotations

import pytest

from fin_cli.fin_analyze.analyzers import (
    category_breakdown,
    category_evolution,
    category_timeline,
    category_suggestions,
    merchant_frequency,
    spending_patterns,
    spending_trends,
    subscription_detect,
    unusual_spending,
)
from fin_cli.fin_analyze.types import AnalysisContext, AnalysisError


@pytest.mark.parametrize(
    "fixture_name, window_label, window_start, window_end, comparison_label, comparison_start, comparison_end, options, threshold",
    [
        (
            "subscriptions",
            "month_2025_08",
            "2025-08-01",
            "2025-09-01",
            "month_2025_07",
            "2025-07-01",
            "2025-08-01",
            {"include_inactive": True},
            0.05,
        ),
    ],
)
def test_subscription_detection_flags_new_and_price_increase(
    load_analysis_dataset,
    analysis_context,
    window_factory,
    fixture_name,
    window_label,
    window_start,
    window_end,
    comparison_label,
    comparison_start,
    comparison_end,
    options,
    threshold,
) -> None:
    load_analysis_dataset(fixture_name)
    window = window_factory(window_label, window_start, window_end)
    comparison = window_factory(comparison_label, comparison_start, comparison_end)
    context = analysis_context(window, comparison, options, compare=True, threshold=threshold)

    result = subscription_detect.analyze(context)
    payload = result.json_payload

    merchants = {entry["merchant"] for entry in payload["subscriptions"]}
    assert "NETFLIX" in merchants

    price_merchants = {entry["merchant"] for entry in payload["price_increases"]}
    assert "NETFLIX" in price_merchants

    new_names = {entry["merchant"] for entry in payload["new_merchants"]}
    assert "DISNEY+" in new_names

    cancelled_names = {entry["merchant"] for entry in payload["cancelled"]}
    assert "HULU" in cancelled_names


@pytest.mark.parametrize(
    "options",
    [
        {"sensitivity": 3},
        {"sensitivity": 4},
    ],
)
def test_unusual_spending_flags_large_increase(
    load_analysis_dataset,
    analysis_context,
    window_factory,
    options,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    comparison = window_factory("month_2025_07", "2025-07-01", "2025-08-01")
    context = analysis_context(window, comparison, options, compare=True, threshold=0.10)

    result = unusual_spending.analyze(context)
    payload = result.json_payload

    anomaly_merchants = {entry["merchant"] for entry in payload["anomalies"]}
    assert "AMAZON" in anomaly_merchants

    assert "TESLA SUPERCHARGER" in payload["new_merchants"]


def test_merchant_frequency_reports_new_and_dropped(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    comparison = window_factory("month_2025_07", "2025-07-01", "2025-08-01")
    context = analysis_context(window, comparison, {"min_visits": 1}, compare=True, threshold=0.10)

    result = merchant_frequency.analyze(context)
    payload = result.json_payload

    merchants = {entry["canonical"]: entry for entry in payload["merchants"]}
    amazon = merchants.get("AMAZON")
    assert amazon and amazon["visits"] == 3
    assert any(name.startswith("Tesla") for name in payload["new_merchants"])
    assert any(name.startswith("Target") for name in payload["dropped_merchants"])


def test_spending_patterns_day_group(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    comparison = window_factory("month_2025_07", "2025-07-01", "2025-08-01")
    context = analysis_context(window, comparison, {"group_by": "day"}, compare=True, threshold=0.10)

    result = spending_patterns.analyze(context)
    patterns = {entry["label"]: entry for entry in result.json_payload["patterns"]}
    assert "Tuesday" in patterns
    assert "Sunday" in patterns
    assert patterns["Tuesday"]["spend"] > patterns["Sunday"]["spend"]


def test_category_suggestions_overlap(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("category_overlap")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    context = analysis_context(window, None, {"min_overlap": 0.8}, compare=False, threshold=0.10)

    result = category_suggestions.analyze(context)
    suggestions = result.json_payload["suggestions"]
    assert any(
        suggestion["from"] == "Coffee > General" and suggestion["to"] == "Coffee Shops > Specialty"
        for suggestion in suggestions
    )


def test_merchant_frequency_with_category_filter(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    comparison = window_factory("month_2025_07", "2025-07-01", "2025-08-01")
    context = analysis_context(
        window,
        comparison,
        {"min_visits": 1, "category": "Shopping"},
        compare=True,
        threshold=0.10,
    )

    result = merchant_frequency.analyze(context)
    payload = result.json_payload

    assert payload.get("filter") == {"category": "Shopping", "subcategory": None}
    merchants = {entry["canonical"] for entry in payload["merchants"]}
    assert "AMAZON" in merchants


def test_spending_trends_with_categories_and_comparison(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("summer_2025", "2025-05-01", "2025-09-01")
    comparison = window_factory("spring_2025", "2025-01-01", "2025-05-01")
    context = analysis_context(
        window,
        comparison,
        {"show_categories": True},
        compare=True,
        threshold=0.15,
    )

    result = spending_trends.analyze(context)
    payload = result.json_payload

    assert payload["trend_slope"] and payload["trend_slope"] > 0
    assert payload["monthly"][-1]["month"] == "2025-08"
    assert "category_breakdown" in payload and payload["category_breakdown"][0]["category"] == "Shopping"


def test_category_breakdown_min_amount_and_change(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    comparison = window_factory("month_2025_07", "2025-07-01", "2025-08-01")
    context = analysis_context(
        window,
        comparison,
        {"min_amount": 50},
        compare=True,
        threshold=0.10,
    )

    result = category_breakdown.analyze(context)
    payload = result.json_payload

    categories = {entry["category"]: entry for entry in payload["categories"]}
    shopping = categories.get("Shopping")
    assert shopping and shopping["spend"] > 0
    assert shopping["transaction_count"] >= 4
    assert shopping["change_pct"] and shopping["change_pct"] > 0
    comparison = payload.get("comparison")
    assert comparison and comparison["total_spend"] < payload["total_spend"]
    assert all(entry["spend"] >= 50 for entry in payload["categories"])


def test_category_evolution_new_and_dormant(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    comparison = window_factory("month_2025_07", "2025-07-01", "2025-08-01")
    context = analysis_context(window, comparison, compare=True, threshold=0.10)

    result = category_evolution.analyze(context)
    payload = result.json_payload

    new_categories = {(entry["category"], entry["subcategory"]) for entry in payload["new_categories"]}
    dormant_categories = {(entry["category"], entry["subcategory"]) for entry in payload["dormant_categories"]}

    assert ("Travel", "Ridehail") in new_categories
    assert ("Home Improvement", "Hardware") in dormant_categories


def test_category_timeline_month_interval_with_merchants(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("rolling_year", "2024-09-01", "2025-09-01")
    comparison = window_factory("preceding_year", "2023-09-01", "2024-09-01")
    context = analysis_context(
        window,
        comparison,
        {
            "interval": "month",
            "category": "Shopping",
            "include_merchants": True,
            "top_n": 6,
        },
        compare=True,
        threshold=0.10,
    )

    result = category_timeline.analyze(context)
    payload = result.json_payload

    assert payload["interval"] == "month"
    assert payload["filter"] == {"category": "Shopping", "subcategory": None}
    assert payload["intervals"][-1]["interval"].startswith("2025-08")
    assert payload["totals"]["intervals"] >= 12
    assert "merchants" in payload and "AMAZON" in payload["merchants"]["canonical"]


def test_category_timeline_raises_when_no_matches(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    context = analysis_context(window, None, {"category": "Nonexistent"}, compare=False)

    with pytest.raises(AnalysisError):
        category_timeline.analyze(context)


def test_spending_trends_handles_sparse_and_empty_windows(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("sparse")
    data_window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    data_context = analysis_context(data_window, None, compare=False)
    result = spending_trends.analyze(data_context)
    assert len(result.json_payload["monthly"]) == 1

    empty_window = window_factory("month_2025_07", "2025-07-01", "2025-08-01")
    empty_context = analysis_context(empty_window, None, compare=False)
    with pytest.raises(AnalysisError):
        spending_trends.analyze(empty_context)


def test_json_payload_keys_remain_stable(
    load_analysis_dataset,
    analysis_context,
    window_factory,
) -> None:
    load_analysis_dataset("spending_multi_year")
    window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    comparison = window_factory("month_2025_07", "2025-07-01", "2025-08-01")

    trends_context = analysis_context(
        window,
        comparison,
        {"show_categories": True},
        compare=True,
        threshold=0.10,
    )
    trends_payload = spending_trends.analyze(trends_context).json_payload
    assert set(trends_payload.keys()) == {
        "window",
        "total_spend",
        "monthly",
        "comparison",
        "options",
        "threshold",
        "trend_slope",
        "category_breakdown",
    }

    breakdown_context = analysis_context(window, comparison, {"min_amount": 0}, compare=True, threshold=0.10)
    breakdown_payload = category_breakdown.analyze(breakdown_context).json_payload
    assert set(breakdown_payload.keys()) == {
        "window",
        "threshold",
        "total_spend",
        "categories",
        "comparison",
    }

    evolution_context = analysis_context(window, comparison, compare=True, threshold=0.10)
    evolution_payload = category_evolution.analyze(evolution_context).json_payload
    assert set(evolution_payload.keys()) == {
        "window",
        "new_categories",
        "dormant_categories",
        "changes",
        "threshold",
    }

    load_analysis_dataset("subscriptions")
    subs_window = window_factory("month_2025_08", "2025-08-01", "2025-09-01")
    subs_comparison = window_factory("month_2025_07", "2025-07-01", "2025-08-01")
    subs_context = analysis_context(subs_window, subs_comparison, {"include_inactive": True}, compare=True)
    subs_payload = subscription_detect.analyze(subs_context).json_payload
    assert set(subs_payload.keys()) == {
        "window",
        "subscriptions",
        "price_increases",
        "new_merchants",
        "cancelled",
        "threshold",
    }

    load_analysis_dataset("spending_multi_year")
    unusual_context = analysis_context(window, comparison, {"sensitivity": 3}, compare=True, threshold=0.10)
    unusual_payload = unusual_spending.analyze(unusual_context).json_payload
    assert set(unusual_payload.keys()) == {
        "window",
        "threshold_pct",
        "sensitivity",
        "anomalies",
        "new_merchants",
    }

    timeline_context = analysis_context(
        window,
        comparison,
        {"interval": "quarter", "category": "Shopping", "top_n": 4},
        compare=True,
        threshold=0.10,
    )
    timeline_payload = category_timeline.analyze(timeline_context).json_payload
    assert set(timeline_payload.keys()) >= {"window", "interval", "filter", "intervals", "totals", "metadata"}
    assert timeline_payload["interval"] == "quarter"
