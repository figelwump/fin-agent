"""Category spend timeline analyzer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ...shared.dataframe import (
    build_window_frames,
    filter_frame_by_category,
    prepare_grouped_spend,
    summarize_merchants,
)
from ..metrics import percentage_change, safe_float, significance
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries


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
    comparison_frame_filtered = None
    if context.compare and frames.comparison_frame is not None and not frames.comparison_empty():
        comparison_candidate = filter_frame_by_category(
            frames.comparison_frame,
            category=str(category) if category else None,
            subcategory=str(subcategory) if subcategory else None,
        )
        comparison_frame_filtered = comparison_candidate
        if not comparison_candidate.empty:
            comparison_grouped = _group_with_cumulative(comparison_candidate, interval)
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

    evolution_payload: dict[str, Any] | None = None
    new_categories_count = 0
    dormant_categories_count = 0
    significant_changes: Sequence[str] = ()
    if comparison_frame_filtered is not None:
        current_map = _aggregate(primary)
        comparison_map = _aggregate(comparison_frame_filtered)
        new_categories = _diff_categories(current_map, comparison_map)
        dormant_categories = _diff_categories(comparison_map, current_map)
        evolution_records = _build_evolution_records(current_map, comparison_map)
        significant_changes = _significant_changes(evolution_records, threshold=context.threshold)
        new_categories_count = len(new_categories)
        dormant_categories_count = len(dormant_categories)
        evolution_payload = {
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
                for rec in evolution_records
            ],
            "significant_changes": significant_changes,
            "threshold": context.threshold if context.threshold is not None else 0.10,
        }
    else:
        evolution_payload = {
            "new_categories": [],
            "dormant_categories": [],
            "changes": [],
            "significant_changes": [],
            "threshold": context.threshold if context.threshold is not None else 0.10,
        }

    total_spend = safe_float(grouped["spend"].sum())
    summaries = _build_summaries(
        total_spend=total_spend,
        filtered_category=category,
        filtered_subcategory=subcategory,
        change_vs_comparison=change_vs_comparison,
        threshold=context.threshold,
        interval_label=interval,
        interval_count=len(grouped),
        new_categories_count=new_categories_count,
        dormant_categories_count=dormant_categories_count,
        significant_changes=significant_changes,
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

    if (
        comparison_grouped is not None
        and not comparison_grouped.empty
        and comparison_total is not None
    ):
        json_payload["comparison"] = {
            "spend": round(comparison_total, 2),
            "intervals": len(comparison_grouped),
            "change_pct": (
                None if change_vs_comparison is None else round(float(change_vs_comparison), 4)
            ),
        }

    if include_merchants:
        json_payload["merchants"] = summarize_merchants(primary)

    if evolution_payload is not None:
        json_payload["evolution"] = evolution_payload

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
                interval=record.interval,
                start=record.start,
                end=record.end,
                spend=safe_float(record.spend),
                income=safe_float(record.income),
                net=safe_float(record.net),
                transaction_count=int(record.transaction_count),
                cumulative_spend=safe_float(record.cumulative_spend),
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
    new_categories_count: int,
    dormant_categories_count: int,
    significant_changes: Sequence[str],
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

    if new_categories_count:
        summaries.append(f"New categories introduced: {new_categories_count}.")
    if dormant_categories_count:
        summaries.append(f"Categories now inactive: {dormant_categories_count}.")
    if significant_changes:
        summaries.append("Significant category shifts: " + "; ".join(significant_changes) + ".")

    return summaries


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
    diff: list[dict[str, Any]] = []
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
    records.sort(key=lambda rec: abs(rec.spend_change_pct or 0), reverse=True)
    return records


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
                f"{rec.category} > {rec.subcategory} spend {direction} {abs(change_pct) * 100:.1f}%"
            )
    return highlights
