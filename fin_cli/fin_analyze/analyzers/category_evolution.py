"""Category evolution analyzer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ...shared.dataframe import build_window_frames
from ..metrics import percentage_change, safe_float, significance
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries


@dataclass(frozen=True)
class CategoryAggregate:
    category: str
    subcategory: str
    transactions: int
    spend: float


@dataclass(frozen=True)
class EvolutionRecord:
    category: str
    subcategory: str
    transactions_current: int
    transactions_previous: int
    spend_current: float
    spend_previous: float
    spend_change_pct: float | None
    transaction_change_pct: float | None


def analyze(context: AnalysisContext) -> AnalysisResult:
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    frames = build_window_frames(context)
    current_frame = frames.frame
    if current_frame.empty:
        raise AnalysisError("No transactions found for the selected window.")

    current_map = _aggregate(current_frame)
    comparison_map = (
        _aggregate(frames.comparison_frame)
        if frames.comparison_frame is not None and not frames.comparison_empty()
        else {}
    )

    new_categories = _diff_categories(current_map, comparison_map)
    dormant_categories = _diff_categories(comparison_map, current_map)

    records = _build_evolution_records(current_map, comparison_map)
    significant = _significant_changes(records, threshold=context.threshold)

    summary_lines = [f"Categories active this window: {len(current_map)}."]
    if new_categories:
        summary_lines.append(f"New categories introduced: {len(new_categories)}.")
    if dormant_categories:
        summary_lines.append(f"Categories now inactive: {len(dormant_categories)}.")
    if significant:
        summary_lines.append("Significant shifts: " + "; ".join(significant) + ".")

    table = _build_table(records)

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "new_categories": new_categories,
        "dormant_categories": dormant_categories,
        "changes": [
            {
                "category": rec.category,
                "subcategory": rec.subcategory,
                "transactions_current": rec.transactions_current,
                "transactions_previous": rec.transactions_previous,
                "spend_current": round(rec.spend_current, 2),
                "spend_previous": round(rec.spend_previous, 2),
                "spend_change_pct": (
                    None if rec.spend_change_pct is None else round(rec.spend_change_pct, 4)
                ),
                "transaction_change_pct": (
                    None
                    if rec.transaction_change_pct is None
                    else round(rec.transaction_change_pct, 4)
                ),
            }
            for rec in records
        ],
        "threshold": context.threshold if context.threshold is not None else 0.10,
    }

    return AnalysisResult(
        title="Category Evolution",
        summary=summary_lines,
        tables=[table],
        json_payload=json_payload,
    )


def _aggregate(frame: pd.DataFrame | None) -> dict[tuple[str, str], CategoryAggregate]:
    if frame is None or frame.empty:
        return {}

    working = frame.copy()
    working["category"] = working["category"].fillna("Uncategorized")
    working["subcategory"] = working["subcategory"].fillna("Uncategorized")
    grouped = (
        working.groupby(["category", "subcategory"], sort=True)
        .agg({"transaction_id": "count", "spend_amount": "sum"})
        .reset_index()
    )

    aggregates: dict[tuple[str, str], CategoryAggregate] = {}
    for row in grouped.itertuples(index=False):
        key = (str(row.category), str(row.subcategory))
        aggregates[key] = CategoryAggregate(
            category=key[0],
            subcategory=key[1],
            transactions=int(row.transaction_id),
            spend=safe_float(row.spend_amount),
        )
    return aggregates


def _diff_categories(
    primary: dict[tuple[str, str], CategoryAggregate],
    secondary: dict[tuple[str, str], CategoryAggregate],
) -> list[dict[str, Any]]:
    diff = []
    for key, aggregate in primary.items():
        if key in secondary:
            continue
        diff.append(
            {
                "category": aggregate.category,
                "subcategory": aggregate.subcategory,
                "transactions": aggregate.transactions,
                "spend": round(aggregate.spend, 2),
            }
        )
    return diff


def _build_evolution_records(
    current: dict[tuple[str, str], CategoryAggregate],
    previous: dict[tuple[str, str], CategoryAggregate],
) -> list[EvolutionRecord]:
    records: list[EvolutionRecord] = []
    all_keys = set(current) | set(previous)
    for key in sorted(all_keys):
        current_stats = current.get(key)
        previous_stats = previous.get(key)
        current_transactions = current_stats.transactions if current_stats else 0
        previous_transactions = previous_stats.transactions if previous_stats else 0
        current_spend = current_stats.spend if current_stats else 0.0
        previous_spend = previous_stats.spend if previous_stats else 0.0
        spend_change = percentage_change(current_spend, previous_spend)
        txn_change = percentage_change(current_transactions, previous_transactions)
        records.append(
            EvolutionRecord(
                category=key[0],
                subcategory=key[1],
                transactions_current=current_transactions,
                transactions_previous=previous_transactions,
                spend_current=current_spend,
                spend_previous=previous_spend,
                spend_change_pct=spend_change,
                transaction_change_pct=txn_change,
            )
        )
    # Sort by absolute spend change descending for table readability
    records.sort(key=lambda rec: abs(rec.spend_change_pct or 0), reverse=True)
    return records


def _build_table(records: Sequence[EvolutionRecord]) -> TableSeries:
    rows: list[list[Any]] = []
    for rec in records:
        rows.append(
            [
                rec.category,
                rec.subcategory,
                rec.transactions_current,
                rec.transactions_previous,
                round(rec.spend_current, 2),
                round(rec.spend_previous, 2),
                None if rec.spend_change_pct is None else round(rec.spend_change_pct * 100, 2),
                (
                    None
                    if rec.transaction_change_pct is None
                    else round(rec.transaction_change_pct * 100, 2)
                ),
            ]
        )
    return TableSeries(
        name="category_evolution",
        columns=[
            "Category",
            "Subcategory",
            "Transactions (Current)",
            "Transactions (Previous)",
            "Spend (Current)",
            "Spend (Previous)",
            "Spend Change %",
            "Txn Change %",
        ],
        rows=rows,
        metadata={"unit": "USD", "percentage_basis": 100},
    )


def _significant_changes(
    records: Sequence[EvolutionRecord], *, threshold: float | None
) -> list[str]:
    highlights: list[str] = []
    for rec in records:
        change_pct = rec.spend_change_pct
        if change_pct is None or change_pct == 0:
            continue
        if significance(change_pct, threshold):
            direction = "up" if change_pct > 0 else "down"
            highlights.append(
                f"{rec.category} > {rec.subcategory} spend {direction} {abs(change_pct)*100:.1f}%"
            )
    return highlights
