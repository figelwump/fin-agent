"""Category breakdown analyzer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ...shared.dataframe import load_category_totals
from ..metrics import percentage_change, safe_float, significance
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries


@dataclass(frozen=True)
class CategoryRecord:
    category: str
    subcategory: str
    spend: float
    income: float
    transactions: int
    pct_of_total: float
    change_pct: float | None


def analyze(context: AnalysisContext) -> AnalysisResult:
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    min_amount = context.options.get("min_amount")
    try:
        min_amount_val = float(min_amount) if min_amount is not None else 0.0
    except (TypeError, ValueError):
        raise AnalysisError("--min-amount must be numeric when provided.")

    current = load_category_totals(context)
    if current.empty:
        raise AnalysisError(
            "No categorized spend found for the selected window. Suggestion: Try using a longer time period (e.g., 6m, 12m, 24m, 36m, or all) or ask the user if they have imported any transactions yet."
        )

    current = current.fillna({"category": "Uncategorized", "subcategory": "Uncategorized"})
    current["spend_amount"] = current["spend_amount"].astype(float)
    current["income_amount"] = current["income_amount"].astype(float)
    current["transaction_count"] = current["transaction_count"].astype(int)

    if min_amount_val > 0:
        current = current[current["spend_amount"] >= min_amount_val]

    total_spend = safe_float(current["spend_amount"].sum())
    if total_spend <= 0:
        raise AnalysisError("No positive spend detected for this window.")

    comparison = None
    comparison_map: dict[tuple[str, str], float] = {}
    if context.compare and context.comparison_window is not None:
        comparison = load_category_totals(context, window=context.comparison_window)
        comparison = comparison.fillna(
            {"category": "Uncategorized", "subcategory": "Uncategorized"}
        )
        comparison["spend_amount"] = comparison["spend_amount"].astype(float)
        comparison_map = {
            (str(row.category), str(row.subcategory)): safe_float(row.spend_amount)
            for row in comparison.itertuples(index=False)
        }

    records = _build_records(current, total_spend, comparison_map)
    tables = [_build_table(records)]

    change_summary = _change_summary(records, threshold=context.threshold)
    top_categories = ", ".join(
        f"{rec.category} > {rec.subcategory} (${rec.spend:,.0f})" for rec in records[:3]
    )

    summary_lines = [
        f"Total spend: ${total_spend:,.2f} across {len(records)} categories.",
    ]
    if top_categories:
        summary_lines.append(f"Top categories: {top_categories}.")
    summary_lines.extend(change_summary)

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "threshold": context.threshold if context.threshold is not None else 0.10,
        "total_spend": round(total_spend, 2),
        "categories": [
            {
                "category": rec.category,
                "subcategory": rec.subcategory,
                "spend": round(rec.spend, 2),
                "income": round(rec.income, 2),
                "transaction_count": rec.transactions,
                "pct_of_total": round(rec.pct_of_total, 4),
                "change_pct": None if rec.change_pct is None else round(rec.change_pct, 4),
            }
            for rec in records
        ],
    }

    if comparison is not None and not comparison.empty:
        comp_total = safe_float(comparison["spend_amount"].sum())
        json_payload["comparison"] = {
            "total_spend": round(comp_total, 2),
        }

    return AnalysisResult(
        title="Category Breakdown",
        summary=summary_lines,
        tables=tables,
        json_payload=json_payload,
    )


def _build_records(
    current: pd.DataFrame,
    total_spend: float,
    comparison_map: dict[tuple[str, str], float],
) -> list[CategoryRecord]:
    records: list[CategoryRecord] = []
    for row in current.sort_values("spend_amount", ascending=False).itertuples(index=False):
        cat = str(row.category)
        sub = str(row.subcategory)
        spend = safe_float(row.spend_amount)
        income = safe_float(row.income_amount)
        pct = spend / total_spend if total_spend else 0.0
        comparison_value = comparison_map.get((cat, sub))
        change_pct = (
            percentage_change(spend, comparison_value) if comparison_value is not None else None
        )
        records.append(
            CategoryRecord(
                category=cat,
                subcategory=sub,
                spend=spend,
                income=income,
                transactions=int(row.transaction_count),
                pct_of_total=pct,
                change_pct=change_pct,
            )
        )
    return records


def _build_table(records: Sequence[CategoryRecord]) -> TableSeries:
    rows: list[list[Any]] = []
    for rec in records:
        rows.append(
            [
                rec.category,
                rec.subcategory,
                round(rec.spend, 2),
                round(rec.pct_of_total * 100, 2),
                rec.transactions,
                None if rec.change_pct is None else round(rec.change_pct * 100, 2),
            ]
        )
    return TableSeries(
        name="category_breakdown",
        columns=["Category", "Subcategory", "Spend", "% of Total", "Transactions", "Change %"],
        rows=rows,
        metadata={"unit": "USD", "percentage_basis": 100},
    )


def _change_summary(records: Sequence[CategoryRecord], *, threshold: float | None) -> list[str]:
    significant: list[str] = []
    for rec in records:
        if rec.change_pct is None:
            continue
        if significance(rec.change_pct, threshold):
            direction = "up" if rec.change_pct > 0 else "down"
            significant.append(
                f"{rec.category} > {rec.subcategory} {direction} {abs(rec.change_pct)*100:.1f}%"
            )
    if not significant:
        return []
    return ["Significant movements: " + "; ".join(significant) + "."]
