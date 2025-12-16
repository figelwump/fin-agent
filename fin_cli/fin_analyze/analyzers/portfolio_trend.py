"""Portfolio market value trend analyzer."""

from __future__ import annotations

from typing import Any

try:  # Optional dependency
    import numpy as np  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional
    np = None  # type: ignore[assignment]

from fin_cli.fin_analyze.assets import load_valuation_timeseries
from fin_cli.fin_analyze.metrics import percentage_change, safe_float
from fin_cli.fin_analyze.types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries


def analyze(context: AnalysisContext) -> AnalysisResult:
    frame = load_valuation_timeseries(
        context,
        start_date=context.window.start,
        end_date=context.window.end,
        account_id=context.options.get("account_id"),
    )

    if frame.empty:
        raise AnalysisError(
            "No valuation history found for the selected window. Import statements or pick a wider period (e.g., --period 6m)."
        )

    series = _aggregate_portfolio(frame)
    current_value = safe_float(series["market_value"].iloc[-1])
    start_value = safe_float(series["market_value"].iloc[0])
    total_change_pct = percentage_change(current_value, start_value)
    slope = _trend_slope(series)

    comparison = None
    comparison_change = None
    if context.compare and context.comparison_window:
        comparison_frame = load_valuation_timeseries(
            context,
            start_date=context.comparison_window.start,
            end_date=context.comparison_window.end,
            account_id=context.options.get("account_id"),
        )
        if not comparison_frame.empty:
            comparison_series = _aggregate_portfolio(comparison_frame)
            comparison = safe_float(comparison_series["market_value"].iloc[-1])
            comparison_change = percentage_change(current_value, comparison)

    summaries = _summaries(
        series=series,
        current_value=current_value,
        total_change_pct=total_change_pct,
        slope=slope,
        comparison_value=comparison,
        comparison_change=comparison_change,
        threshold=context.threshold,
    )

    trend_table = TableSeries(
        name="Portfolio Trend",
        columns=["date", "market_value", "change_pct"],
        rows=[
            [
                row["as_of_date"].date().isoformat(),
                safe_float(row["market_value"]),
                row["change_pct"],
            ]
            for _, row in series.iterrows()
        ],
        metadata={"window_label": context.window.label},
    )

    json_payload: dict[str, Any] = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "current_value": round(current_value, 2),
        "change_pct": None if total_change_pct is None else round(total_change_pct, 4),
        "trend_slope": slope,
        "series": [
            {
                "date": row["as_of_date"].date().isoformat(),
                "market_value": round(safe_float(row["market_value"]), 2),
                "change_pct": None if row["change_pct"] is None else round(row["change_pct"], 4),
            }
            for _, row in series.iterrows()
        ],
        "comparison": None,
    }
    if comparison is not None:
        json_payload["comparison"] = {
            "value": round(comparison, 2),
            "change_pct": None if comparison_change is None else round(comparison_change, 4),
            "window_label": context.comparison_window.label if context.comparison_window else None,
        }

    return AnalysisResult(
        title="Portfolio Trend",
        summary=summaries,
        tables=[trend_table],
        json_payload=json_payload,
    )


def _aggregate_portfolio(frame):
    ordered = frame.sort_values("as_of_date")
    grouped = ordered.groupby("as_of_date", sort=True)["market_value"].sum().reset_index()
    grouped["market_value"] = grouped["market_value"].apply(safe_float)
    change_values = [None]
    for i in range(1, len(grouped)):
        change_values.append(
            percentage_change(
                safe_float(grouped["market_value"].iloc[i]),
                safe_float(grouped["market_value"].iloc[i - 1]),
            )
        )
    grouped["change_pct"] = change_values
    return grouped


def _trend_slope(series):
    if np is None or len(series) < 2:
        return None
    y = np.array(series["market_value"].tolist(), dtype=float)
    if not np.any(y):
        return 0.0
    x = np.arange(len(series), dtype=float)
    try:
        slope, _ = np.polyfit(x, y, 1)
    except Exception:  # pragma: no cover - defensive
        return None
    return round(float(slope), 2)


def _summaries(
    *,
    series,
    current_value: float,
    total_change_pct: float | None,
    slope: float | None,
    comparison_value: float | None,
    comparison_change: float | None,
    threshold: float | None,
) -> list[str]:
    summaries: list[str] = [
        f"Portfolio value now: ${current_value:,.2f}",
    ]

    if total_change_pct is not None:
        direction = "↑" if total_change_pct > 0 else "↓"
        summaries.append(
            f"Change since window start: {direction} {abs(total_change_pct) * 100:.1f}%"
        )

    if comparison_value is not None and comparison_change is not None:
        direction = "up" if comparison_change > 0 else "down"
        marker = (
            " (significant)"
            if threshold is not None and abs(comparison_change) >= threshold
            else ""
        )
        summaries.append(
            f"Value {direction} {abs(comparison_change) * 100:.1f}% versus comparison window{marker}."
        )

    if slope is not None:
        summaries.append(
            f"Trend slope: ${abs(slope):,.2f} per observation ({'upward' if slope > 0 else 'downward'})."
        )

    if len(series) >= 2:
        recent = series.iloc[-1]
        prior = series.iloc[-2]
        recent_change = percentage_change(
            safe_float(recent["market_value"]), safe_float(prior["market_value"])
        )
        if recent_change is not None:
            direction = "↑" if recent_change > 0 else "↓"
            summaries.append(
                f"Most recent move ({recent['as_of_date'].date()}): {direction} {abs(recent_change) * 100:.1f}%"
            )

    return summaries
