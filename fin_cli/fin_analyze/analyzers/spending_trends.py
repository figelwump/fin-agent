"""Spending trend analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

try:
    import numpy as np  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]

from ..metrics import percentage_change, significance, safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries
from ...shared.dataframe import build_window_frames


@dataclass(frozen=True)
class TrendRow:
    month: str
    spend: float
    change_pct: float | None


@dataclass(frozen=True)
class CategoryRow:
    category: str
    subcategory: str
    spend: float
    pct_of_total: float


def analyze(context: AnalysisContext) -> AnalysisResult:
    """Compute monthly spending totals with optional category drill-down."""

    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    frames = build_window_frames(context)
    frame = frames.frame
    if frame.empty:
        raise AnalysisError(
            "No transactions available for the selected window. Suggestion: Try using a longer time period (e.g., 6m, 12m, or all) or ask the user if they have imported any transactions yet."
        )

    monthly_trend = _summarise_monthly(frame)
    total_spend = sum(row.spend for row in monthly_trend)
    trend_slope = _trend_slope(monthly_trend)

    comparison_total = None
    comparison_rows: list[TrendRow] = []
    change_vs_comparison: float | None = None
    if frames.comparison_frame is not None and not frames.comparison_empty():
        comparison_rows = _summarise_monthly(frames.comparison_frame)
        comparison_total = sum(row.spend for row in comparison_rows)
        change_vs_comparison = percentage_change(total_spend, comparison_total)

    summaries = _build_summaries(
        context=context,
        total_spend=total_spend,
        change_vs_comparison=change_vs_comparison,
        monthly_trend=monthly_trend,
        trend_slope=trend_slope,
    )

    trend_table = _build_trend_table(monthly_trend)

    category_table: TableSeries | None = None
    category_payload: list[dict[str, Any]] | None = None
    if context.options.get("show_categories"):
        category_rows = _top_categories(frame, limit=10)
        category_table = _build_category_table(category_rows)
        category_payload = [
            {
                "category": row.category,
                "subcategory": row.subcategory,
                "spend": row.spend,
                "pct_of_total": row.pct_of_total,
            }
            for row in category_rows
        ]

    tables: list[TableSeries] = [trend_table]
    if category_table is not None:
        tables.append(category_table)

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "total_spend": round(total_spend, 2),
        "monthly": [
            {
                "month": row.month,
                "spend": round(row.spend, 2),
                "change_pct": None if row.change_pct is None else round(row.change_pct, 4),
            }
            for row in monthly_trend
        ],
        "comparison": None,
        "options": {"show_categories": bool(context.options.get("show_categories"))},
        "threshold": context.threshold if context.threshold is not None else 0.10,
        "trend_slope": None if trend_slope is None else round(trend_slope, 2),
    }

    if comparison_total is not None:
        json_payload["comparison"] = {
            "total_spend": round(comparison_total, 2),
            "change_pct": None if change_vs_comparison is None else round(change_vs_comparison, 4),
            "window_label": frames.comparison_window.label if frames.comparison_window else None,
        }
    if category_payload is not None:
        json_payload["category_breakdown"] = category_payload

    return AnalysisResult(
        title="Spending Trends",
        summary=summaries,
        tables=tables,
        json_payload=json_payload,
    )


def _summarise_monthly(frame: pd.DataFrame) -> list[TrendRow]:
    ordered = frame.sort_values("date")
    grouped = (
        ordered.groupby("month", sort=True)["spend_amount"]
        .sum()
        .reset_index()
        .sort_values("month")
    )

    rows: list[TrendRow] = []
    previous_value: float | None = None
    for record in grouped.itertuples(index=False):
        month = str(record.month)
        spend = safe_float(record.spend_amount)
        change_pct = percentage_change(spend, previous_value)
        rows.append(TrendRow(month=month, spend=spend, change_pct=change_pct))
        previous_value = spend
    return rows


def _trend_slope(rows: Sequence[TrendRow]) -> float | None:
    if np is None or len(rows) < 2:
        return None
    y = np.array([row.spend for row in rows], dtype=float)
    if not np.any(y):
        return 0.0
    x = np.arange(len(rows), dtype=float)
    try:
        slope, _intercept = np.polyfit(x, y, 1)
    except Exception:  # pragma: no cover - defensive fallback when np.polyfit fails
        return None
    return float(slope)


def _build_summaries(
    *,
    context: AnalysisContext,
    total_spend: float,
    change_vs_comparison: float | None,
    monthly_trend: Sequence[TrendRow],
    trend_slope: float | None,
) -> list[str]:
    summaries: list[str] = []
    start = context.window.start
    end = context.window.end - pd.DateOffset(days=1)
    summaries.append(
        f"Total spend between {start:%Y-%m-%d} and {end:%Y-%m-%d}: ${total_spend:,.2f}"
    )

    threshold = context.threshold
    if change_vs_comparison is not None:
        direction = "up" if change_vs_comparison > 0 else "down"
        change_pct_display = abs(change_vs_comparison) * 100
        marker = " (significant)" if significance(change_vs_comparison, threshold) else ""
        summaries.append(
            f"Spend {direction} {change_pct_display:.1f}% versus prior window{marker}."
        )

    if trend_slope is not None:
        trend_direction = "upward" if trend_slope > 0 else "downward"
        summaries.append(
            f"Trendline indicates {trend_direction} movement of ${abs(trend_slope):,.2f} per period."
        )

    if monthly_trend:
        most_recent = monthly_trend[-1]
        summaries.append(
            f"Most recent month ({most_recent.month}) spend: ${most_recent.spend:,.2f}."
        )
        if most_recent.change_pct is not None:
            direction = "↑" if most_recent.change_pct > 0 else "↓"
            summaries.append(
                f"Month-over-month change: {direction} {abs(most_recent.change_pct)*100:.1f}%"
            )

    if context.options.get("show_categories"):
        summaries.append("Top categories included below per --show-categories option.")

    return summaries


def _build_trend_table(rows: Iterable[TrendRow]) -> TableSeries:
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                row.month,
                round(row.spend, 2),
                None if row.change_pct is None else round(row.change_pct * 100, 2),
            ]
        )
    return TableSeries(
        name="monthly_spend",
        columns=["Month", "Spend", "Change %"],
        rows=table_rows,
        metadata={"unit": "USD", "change_units": "percent"},
    )


def _top_categories(frame: pd.DataFrame, *, limit: int = 10) -> list[CategoryRow]:
    working = frame.copy()
    working["category"] = working["category"].fillna("Uncategorized")
    working["subcategory"] = working["subcategory"].fillna("Uncategorized")
    grouped = (
        working.groupby(["category", "subcategory"], sort=True)["spend_amount"].sum().reset_index()
    )
    grouped.sort_values("spend_amount", ascending=False, inplace=True)
    total = safe_float(grouped["spend_amount"].sum()) or 1.0
    rows: list[CategoryRow] = []
    for record in grouped.head(limit).itertuples(index=False):
        spend = safe_float(record.spend_amount)
        pct = (spend / total) if total else 0.0
        rows.append(
            CategoryRow(
                category=str(record.category),
                subcategory=str(record.subcategory),
                spend=spend,
                pct_of_total=pct,
            )
        )
    return rows


def _build_category_table(rows: Sequence[CategoryRow]) -> TableSeries:
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                row.category,
                row.subcategory,
                round(row.spend, 2),
                round(row.pct_of_total * 100, 2),
            ]
        )
    return TableSeries(
        name="category_breakdown",
        columns=["Category", "Subcategory", "Spend", "% of Total"],
        rows=table_rows,
        metadata={"unit": "USD", "percentage_basis": 100},
    )

