"""Compare current allocations to targets and suggest moves."""

from __future__ import annotations

from typing import Any

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from fin_cli.fin_analyze.assets import (
    load_allocation_by_class,
    load_portfolio_snapshot,
    window_as_of,
)
from fin_cli.fin_analyze.metrics import safe_float
from fin_cli.fin_analyze.types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries
from fin_cli.shared.database import connect

TARGETS_SQL = """
SELECT pt.scope, pt.scope_id, pt.target_weight, ac.main_class, ac.sub_class
FROM portfolio_targets pt
JOIN asset_classes ac ON ac.id = pt.asset_class_id
WHERE pt.scope IN ('portfolio', 'account')
"""


def analyze(context: AnalysisContext) -> AnalysisResult:
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    as_of_date = context.options.get("as_of_date") or window_as_of(context)
    account_filter = context.options.get("account_id")

    snapshot = load_portfolio_snapshot(context, as_of_date=as_of_date)
    if snapshot.empty:
        raise AnalysisError(
            "No holdings available for rebalance analysis. Import asset data first."
        )

    total_value = safe_float(snapshot["market_value"].sum())
    allocations = load_allocation_by_class(context, as_of_date=as_of_date)
    allocations = allocations.rename(columns={"allocation_pct": "current_pct"})

    targets = _load_targets(context, account_filter)
    overrides = _parse_target_overrides(context.options.get("target") or [])
    if overrides is not None:
        targets = overrides

    if targets.empty:
        raise AnalysisError(
            "No portfolio targets found. Add rows to portfolio_targets or pass --target main=sub:pct."
        )

    merged = targets.merge(
        allocations,
        how="left",
        on=["main_class", "sub_class"],
        suffixes=("", "_actual"),
    )
    merged["current_pct"] = merged["current_pct"].fillna(0.0)
    merged["delta_pct"] = merged["target_weight"] - merged["current_pct"]
    merged["delta_value"] = merged["delta_pct"] / 100.0 * total_value

    under = merged[merged["delta_value"] > 0].sort_values("delta_value", ascending=False)
    over = merged[merged["delta_value"] < 0].sort_values("delta_value")

    summaries = [
        f"Portfolio value: ${total_value:,.0f} as of {as_of_date}.",
        f"Underweight buckets: {len(under)}; overweight buckets: {len(over)}.",
    ]
    if not under.empty:
        top = under.iloc[0]
        summaries.append(
            f"Largest gap: {top['main_class']}/{top['sub_class']} needs +{top['delta_pct']:.1f}% (~${top['delta_value']:,.0f})."
        )

    table_rows = [
        [
            row["main_class"],
            row["sub_class"],
            round(safe_float(row["target_weight"]), 2),
            round(safe_float(row["current_pct"]), 2),
            round(safe_float(row["delta_pct"]), 2),
            round(safe_float(row["delta_value"]), 2),
        ]
        for _, row in merged.iterrows()
    ]

    tables = [
        TableSeries(
            name="Rebalance Suggestions",
            columns=[
                "main_class",
                "sub_class",
                "target_pct",
                "current_pct",
                "delta_pct",
                "delta_value",
            ],
            rows=table_rows,
            metadata={"as_of_date": as_of_date},
        )
    ]

    json_payload: dict[str, Any] = {
        "as_of_date": as_of_date,
        "total_value": round(total_value, 2),
        "suggestions": merged.to_dict(orient="records"),
    }

    return AnalysisResult(
        title="Rebalance Suggestions",
        summary=summaries,
        tables=tables,
        json_payload=json_payload,
    )


def _load_targets(context: AnalysisContext, account_filter: int | None) -> pd.DataFrame:
    with connect(context.app_config, read_only=True, apply_migrations=False) as connection:
        frame = pd.read_sql_query(TARGETS_SQL, connection)

    if frame.empty:
        return frame

    frame = frame[
        (frame["scope"] == "portfolio")
        | ((frame["scope"] == "account") & (frame["scope_id"] == account_filter))
    ]
    return frame[["main_class", "sub_class", "target_weight"]]


def _parse_target_overrides(values: list[str]) -> pd.DataFrame | None:
    if not values:
        return None
    records = []
    for item in values:
        if ":" in item:
            lhs, weight = item.split(":", 1)
        elif "=" in item:
            lhs, weight = item.split("=", 1)
        else:
            raise AnalysisError("Targets must look like equities=60 or bonds:25")
        if "/" in lhs:
            main, sub = lhs.split("/", 1)
        elif "-" in lhs:
            main, sub = lhs.split("-", 1)
        else:
            main, sub = lhs, "unknown"
        try:
            weight_value = float(weight)
        except ValueError as exc:  # pragma: no cover - defensive
            raise AnalysisError(f"Invalid target weight '{weight}'") from exc
        records.append(
            {"main_class": main.strip(), "sub_class": sub.strip(), "target_weight": weight_value}
        )
    return pd.DataFrame.from_records(records)
