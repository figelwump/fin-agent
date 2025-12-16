"""Identify concentration risk across holdings."""

from __future__ import annotations

from typing import Any

from fin_cli.fin_analyze.assets import load_portfolio_snapshot, window_as_of
from fin_cli.fin_analyze.metrics import safe_float
from fin_cli.fin_analyze.types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries


def analyze(context: AnalysisContext) -> AnalysisResult:
    as_of_date = context.options.get("as_of_date") or window_as_of(context)
    snapshot = load_portfolio_snapshot(context, as_of_date=as_of_date)
    if snapshot.empty:
        raise AnalysisError(
            "No holdings found for concentration analysis. Import statements or widen the window (e.g., --period 6m)."
        )

    total_value = safe_float(snapshot["market_value"].sum())
    if total_value <= 0:
        raise AnalysisError("Portfolio market value is zero; cannot compute concentrations.")

    snapshot_sorted = snapshot.sort_values("market_value", ascending=False).reset_index(drop=True)
    snapshot_sorted["weight_pct"] = (
        snapshot_sorted["market_value"].apply(safe_float) / total_value * 100
    )

    top_n = int(context.options.get("top_n", 5))
    top_holdings = snapshot_sorted.head(top_n)

    fee_rows = None
    if context.options.get("highlight_fees"):
        if "fees" in snapshot_sorted.columns:
            fee_rows = snapshot_sorted[snapshot_sorted.get("fees", 0) > 0]

    hhi = (top_holdings["weight_pct"] / 100).pow(2).sum() * 10000  # Herfindahl index scaled

    summaries = [
        f"Top {len(top_holdings)} holdings represent {top_holdings['weight_pct'].sum():.1f}% of portfolio value.",
        f"HHI (higher = more concentrated): {hhi:.0f}",
    ]
    if context.options.get("highlight_fees"):
        if fee_rows is None:
            summaries.append("Fee data not available for current holdings.")
        elif fee_rows.empty:
            summaries.append("No fee-bearing holdings flagged.")
        else:
            summaries.append(
                f"Fee-bearing holdings: {', '.join(fee_rows['symbol'].astype(str).tolist())}"
            )
    summaries = [line for line in summaries if line]

    table_rows = [
        [
            row.get("symbol"),
            row.get("instrument_name"),
            row.get("account_name"),
            row.get("main_class"),
            round(safe_float(row.get("market_value")), 2),
            round(safe_float(row.get("weight_pct")), 2),
            row.get("fees"),
        ]
        for _, row in top_holdings.iterrows()
    ]

    tables = [
        TableSeries(
            name="Concentration",
            columns=["symbol", "name", "account", "class", "value", "weight_pct", "fees"],
            rows=table_rows,
            metadata={"as_of_date": as_of_date},
        )
    ]

    json_payload: dict[str, Any] = {
        "as_of_date": as_of_date,
        "total_value": round(total_value, 2),
        "top_holdings": [
            {
                "symbol": row.get("symbol"),
                "name": row.get("instrument_name"),
                "account": row.get("account_name"),
                "main_class": row.get("main_class"),
                "weight_pct": round(safe_float(row.get("weight_pct")), 4),
                "value": round(safe_float(row.get("market_value")), 2),
                "fees": safe_float(row.get("fees")) if "fees" in row else None,
            }
            for _, row in top_holdings.iterrows()
        ],
        "hhi": round(hhi, 2),
    }
    if fee_rows is not None:
        json_payload["fee_flags"] = fee_rows[["symbol", "fees"]].to_dict(orient="records")

    return AnalysisResult(
        title="Concentration Risk",
        summary=summaries,
        tables=tables,
        json_payload=json_payload,
    )
