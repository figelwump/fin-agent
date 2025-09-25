"""Spending pattern analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ..metrics import safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries
from ...shared.dataframe import build_window_frames

_GROUP_CHOICES = {"day", "week", "date"}
_WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass(frozen=True)
class PatternRow:
    label: str
    spend: float
    visits: int
    comparison_spend: float
    comparison_visits: int


def analyze(context: AnalysisContext) -> AnalysisResult:
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    frames = build_window_frames(context)
    frame = frames.frame
    if frame.empty:
        raise AnalysisError("No transactions available for the selected window.")

    group_by = (context.options.get("group_by") or "day").lower()
    if group_by not in _GROUP_CHOICES:
        raise AnalysisError(f"Invalid --by value '{group_by}'. Choose from day, week, date.")

    current = _summarise(frame, group_by)
    if not current:
        raise AnalysisError("No spending patterns detected for the selected window.")

    comparison = (
        _summarise(frames.comparison_frame, group_by)
        if frames.comparison_frame is not None and not frames.comparison_empty()
        else {}
    )

    rows = _merge_patterns(current, comparison, group_by)
    table = _build_table(rows)
    summary_lines = _build_summary(rows, group_by)

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "group_by": group_by,
        "patterns": [
            {
                "label": row.label,
                "spend": round(row.spend, 2),
                "visits": row.visits,
                "comparison_spend": round(row.comparison_spend, 2),
                "comparison_visits": row.comparison_visits,
            }
            for row in rows
        ],
    }

    return AnalysisResult(
        title="Spending Patterns",
        summary=summary_lines,
        tables=[table],
        json_payload=json_payload,
    )


def _summarise(frame: pd.DataFrame | None, group_by: str) -> dict[str, tuple[float, int]]:
    if frame is None or frame.empty:
        return {}

    working = frame.copy()
    if group_by == "day":
        key_series = working["weekday"].fillna("Unknown")
    elif group_by == "week":
        iso = working["date"].dt.isocalendar()
        key_series = (iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2))
    else:  # date
        key_series = working["date"].dt.date.astype(str)

    working["group_key"] = key_series
    grouped = working.groupby("group_key")
    results: dict[str, tuple[float, int]] = {}
    for key, group in grouped:
        spend_total = safe_float(group["spend_amount"].sum())
        visits = int(len(group))
        results[key] = (spend_total, visits)
    return results


def _merge_patterns(
    current: dict[str, tuple[float, int]],
    comparison: dict[str, tuple[float, int]],
    group_by: str,
) -> list[PatternRow]:
    labels = set(current) | set(comparison)
    ordered_labels = _order_labels(labels, group_by)
    rows: list[PatternRow] = []
    for label in ordered_labels:
        current_spend, current_visits = current.get(label, (0.0, 0))
        previous_spend, previous_visits = comparison.get(label, (0.0, 0))
        rows.append(
            PatternRow(
                label=label,
                spend=current_spend,
                visits=current_visits,
                comparison_spend=previous_spend,
                comparison_visits=previous_visits,
            )
        )
    return rows


def _order_labels(labels: set[str], group_by: str) -> list[str]:
    if group_by == "day":
        return [label for label in _WEEKDAY_ORDER if label in labels]
    if group_by == "week":
        # Sort by ISO week label (YYYY-Www)
        return sorted(labels)
    # date grouping
    return sorted(labels)


def _build_table(rows: Sequence[PatternRow]) -> TableSeries:
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                row.label,
                round(row.spend, 2),
                row.visits,
                round(row.comparison_spend, 2),
                row.comparison_visits,
            ]
        )
    return TableSeries(
        name="spending_patterns",
        columns=["Group", "Spend", "Visits", "Prev Spend", "Prev Visits"],
        rows=table_rows,
        metadata={"unit": "USD"},
    )


def _build_summary(rows: Sequence[PatternRow], group_by: str) -> list[str]:
    if not rows:
        return ["No spending patterns detected."]
    top = max(rows, key=lambda row: row.spend)
    summary = [
        f"Highest spend group ({group_by}): {top.label} (${top.spend:,.2f}).",
    ]
    return summary

