"""Portfolio allocation snapshot analyzer."""

from __future__ import annotations

from typing import Any

from fin_cli.fin_analyze.assets import (
    load_allocation_by_account,
    load_allocation_by_class,
    load_portfolio_snapshot,
    window_as_of,
)
from fin_cli.fin_analyze.metrics import percentage_change, safe_float, significance
from fin_cli.fin_analyze.types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries


def analyze(context: AnalysisContext) -> AnalysisResult:
    as_of_date = context.options.get("as_of_date") or window_as_of(context)

    snapshot = load_portfolio_snapshot(context, as_of_date=as_of_date)
    if snapshot.empty:
        raise AnalysisError(
            "No holdings with valuations are available for the selected window. "
            "Import asset statements or widen the date window (e.g., --period 6m)."
        )

    total_value = safe_float(snapshot["market_value"].sum())

    allocation_class = load_allocation_by_class(context, as_of_date=as_of_date)
    allocation_account = load_allocation_by_account(context, as_of_date=as_of_date)

    comparison_value = None
    change_vs_comparison = None
    if context.compare and context.comparison_window:
        comparison_as_of = context.comparison_window.end.isoformat()
        comparison_snapshot = load_portfolio_snapshot(context, as_of_date=comparison_as_of)
        comparison_value = (
            safe_float(comparison_snapshot["market_value"].sum())
            if not comparison_snapshot.empty
            else 0.0
        )
        change_vs_comparison = percentage_change(total_value, comparison_value)

    summaries = _build_summaries(
        total_value=total_value,
        as_of_date=as_of_date,
        allocation_class=allocation_class,
        comparison_value=comparison_value,
        change_vs_comparison=change_vs_comparison,
        threshold=context.threshold,
    )

    tables = [
        _table_from_frame(
            allocation_class,
            name="Allocation by Class",
            columns=[
                "main_class",
                "sub_class",
                "holding_count",
                "instrument_count",
                "total_value",
                "allocation_pct",
            ],
        ),
        _table_from_frame(
            allocation_account,
            name="Allocation by Account",
            columns=["account_id", "account_name", "institution", "total_value", "allocation_pct"],
        ),
    ]

    json_payload: dict[str, Any] = {
        "as_of_date": as_of_date,
        "total_value": round(total_value, 2),
        "allocation_by_class": allocation_class.to_dict(orient="records"),
        "allocation_by_account": allocation_account.to_dict(orient="records"),
        "comparison": None,
    }
    if comparison_value is not None:
        json_payload["comparison"] = {
            "value": round(comparison_value, 2),
            "change_pct": None if change_vs_comparison is None else round(change_vs_comparison, 4),
            "window_label": context.comparison_window.label if context.comparison_window else None,
        }

    return AnalysisResult(
        title="Allocation Snapshot",
        summary=summaries,
        tables=tables,
        json_payload=json_payload,
    )


def _build_summaries(
    *,
    total_value: float,
    as_of_date: str,
    allocation_class,
    comparison_value: float | None,
    change_vs_comparison: float | None,
    threshold: float | None,
) -> list[str]:
    summaries: list[str] = [f"Portfolio value as of {as_of_date}: ${total_value:,.2f}"]

    if change_vs_comparison is not None and comparison_value is not None:
        direction = "up" if change_vs_comparison > 0 else "down"
        pct_display = abs(change_vs_comparison) * 100
        marker = " (significant)" if significance(change_vs_comparison, threshold) else ""
        summaries.append(f"Value {direction} {pct_display:.1f}% versus prior window{marker}.")

    if not allocation_class.empty:
        top_row = allocation_class.iloc[0]
        summaries.append(
            f"Largest exposure: {top_row['main_class']}/{top_row['sub_class']} at {safe_float(top_row['allocation_pct']):.1f}%"
        )
        unclassified = allocation_class[allocation_class["main_class"] == "unclassified"]
        if not unclassified.empty:
            summaries.append(
                f"Unclassified holdings: {safe_float(unclassified['total_value'].sum()):,.0f} USD still needs mapping."
            )

    return summaries


def _table_from_frame(frame, *, name: str, columns: list[str]) -> TableSeries:
    rows = []
    for _, record in frame.iterrows():
        rows.append([record.get(col) for col in columns])
    return TableSeries(name=name, columns=columns, rows=rows)
