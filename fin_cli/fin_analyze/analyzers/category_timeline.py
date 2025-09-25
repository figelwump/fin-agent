"""Category spend timeline analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ..metrics import percentage_change, significance, safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries
from ...shared.dataframe import (
    build_window_frames,
    filter_frame_by_category,
    prepare_grouped_spend,
    summarize_merchants,
)


@dataclass(frozen=True)
class TimelineRow:
    interval: str
    start: Any
    end: Any
    spend: float
    income: float
    net: float
    transaction_count: int
    cumulative_spend: float


def analyze(context: AnalysisContext) -> AnalysisResult:
    """Aggregate spending by interval with optional category filter."""

    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    interval = str(context.options.get("interval", "month"))
    category = context.options.get("category")
    subcategory = context.options.get("subcategory")
    include_merchants = bool(context.options.get("include_merchants"))
    top_n_option = context.options.get("top_n")

    top_n: int | None = None
    if top_n_option is not None:
        try:
            top_n = max(1, int(top_n_option))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise AnalysisError("--top-n must be a positive integer") from exc

    frames = build_window_frames(context)
    primary = filter_frame_by_category(
        frames.frame,
        category=str(category) if category else None,
        subcategory=str(subcategory) if subcategory else None,
    )

    if primary.empty:
        raise AnalysisError("No transactions match the requested filters for this window.")

    grouped = _group_with_cumulative(primary, interval)
    if grouped.empty:
        raise AnalysisError("Unable to group transactions for the requested interval.")

    comparison_grouped = None
    comparison_total = None
    change_vs_comparison = None
    if context.compare and frames.comparison_frame is not None and not frames.comparison_empty():
        comparison_frame = filter_frame_by_category(
            frames.comparison_frame,
            category=str(category) if category else None,
            subcategory=str(subcategory) if subcategory else None,
        )
        if not comparison_frame.empty:
            comparison_grouped = _group_with_cumulative(comparison_frame, interval)
            comparison_total = safe_float(comparison_grouped["spend"].sum())
            change_vs_comparison = percentage_change(
                safe_float(grouped["spend"].sum()),
                comparison_total,
            )

    table_rows = _build_table_rows(grouped, top_n)
    table = TableSeries(
        name="category_timeline",
        columns=[
            "Interval",
            "Start",
            "End",
            "Spend",
            "Income",
            "Net",
            "Txns",
            "Cumulative Spend",
        ],
        rows=table_rows,
        metadata={
            "interval": interval,
            "filter": {"category": category, "subcategory": subcategory},
        },
    )

    total_spend = safe_float(grouped["spend"].sum())
    summaries = _build_summaries(
        total_spend=total_spend,
        filtered_category=category,
        filtered_subcategory=subcategory,
        change_vs_comparison=change_vs_comparison,
        threshold=context.threshold,
        interval_label=interval,
        interval_count=len(grouped),
    )

    json_payload: dict[str, Any] = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "interval": interval,
        "filter": {"category": category, "subcategory": subcategory},
        "intervals": [
            {
                "interval": str(row.interval),
                "start": row.start.isoformat(),
                "end": row.end.isoformat(),
                "spend": round(float(row.spend), 2),
                "income": round(float(row.income), 2),
                "net": round(float(row.net), 2),
                "transaction_count": int(row.transaction_count),
                "cumulative_spend": round(float(row.cumulative_spend), 2),
            }
            for row in _iter_rows(grouped)
        ],
        "totals": {
            "spend": round(total_spend, 2),
            "income": round(safe_float(grouped["income"].sum()), 2),
            "net": round(safe_float(grouped["net"].sum()), 2),
            "intervals": len(grouped),
        },
        "metadata": {
            "top_n": top_n,
            "table_intervals": len(table_rows),
        },
    }

    if comparison_grouped is not None and not comparison_grouped.empty and comparison_total is not None:
        json_payload["comparison"] = {
            "spend": round(comparison_total, 2),
            "intervals": len(comparison_grouped),
            "change_pct": None
            if change_vs_comparison is None
            else round(float(change_vs_comparison), 4),
        }

    if include_merchants:
        json_payload["merchants"] = summarize_merchants(primary)

    return AnalysisResult(
        title="Category Timeline",
        summary=summaries,
        tables=[table],
        json_payload=json_payload,
    )


def _group_with_cumulative(frame: pd.DataFrame, interval: str) -> pd.DataFrame:
    grouped = prepare_grouped_spend(frame, interval=interval)
    if grouped.empty:
        return grouped
    grouped = grouped.sort_values("start").reset_index(drop=True)
    grouped["cumulative_spend"] = grouped["spend"].cumsum()
    return grouped


def _iter_rows(grouped: pd.DataFrame) -> Sequence[TimelineRow]:
    rows: list[TimelineRow] = []
    for record in grouped.itertuples(index=False):
        rows.append(
            TimelineRow(
                interval=getattr(record, "interval"),
                start=getattr(record, "start"),
                end=getattr(record, "end"),
                spend=safe_float(getattr(record, "spend")),
                income=safe_float(getattr(record, "income")),
                net=safe_float(getattr(record, "net")),
                transaction_count=int(getattr(record, "transaction_count")),
                cumulative_spend=safe_float(getattr(record, "cumulative_spend")),
            )
        )
    return rows


def _build_table_rows(grouped: pd.DataFrame, top_n: int | None) -> list[list[Any]]:
    display = grouped
    if top_n is not None and top_n < len(grouped):
        display = grouped.sort_values("start").tail(top_n)

    rows: list[list[Any]] = []
    for row in _iter_rows(display):
        rows.append(
            [
                row.interval,
                row.start.isoformat(),
                row.end.isoformat(),
                round(row.spend, 2),
                round(row.income, 2),
                round(row.net, 2),
                row.transaction_count,
                round(row.cumulative_spend, 2),
            ]
        )
    return rows


def _build_summaries(
    *,
    total_spend: float,
    filtered_category: str | None,
    filtered_subcategory: str | None,
    change_vs_comparison: float | None,
    threshold: float | None,
    interval_label: str,
    interval_count: int,
) -> list[str]:
    summaries: list[str] = []

    label_parts = ["All categories"]
    if filtered_category:
        label_parts = [filtered_category]
    if filtered_subcategory:
        label_parts.append(filtered_subcategory)

    summaries.append(
        f"{', '.join(label_parts)} spend totals {interval_count} {interval_label}(s): ${total_spend:,.2f}."
    )

    if change_vs_comparison is not None:
        direction = "up" if change_vs_comparison > 0 else "down"
        pct_display = abs(change_vs_comparison) * 100
        marker = " (significant)" if significance(change_vs_comparison, threshold) else ""
        summaries.append(
            f"Overall spend {direction} {pct_display:.1f}% versus previous window{marker}."
        )

    return summaries

