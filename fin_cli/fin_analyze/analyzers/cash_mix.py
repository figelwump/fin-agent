"""Cash vs non-cash allocation with spending context."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fin_cli.fin_analyze.assets import load_portfolio_snapshot, window_as_of
from fin_cli.fin_analyze.metrics import ratio, safe_float
from fin_cli.fin_analyze.types import (
    AnalysisContext,
    AnalysisError,
    AnalysisResult,
    TableSeries,
    TimeWindow,
)
from fin_cli.shared.dataframe import load_transactions_frame


def analyze(context: AnalysisContext) -> AnalysisResult:
    as_of_date = context.options.get("as_of_date") or window_as_of(context)
    snapshot = load_portfolio_snapshot(context, as_of_date=as_of_date)
    if snapshot.empty:
        raise AnalysisError(
            "No holdings found for cash mix analysis. Import statements or widen the window (e.g., --period 6m)."
        )

    total_value = safe_float(snapshot["market_value"].sum())
    if total_value <= 0:
        raise AnalysisError("Portfolio market value is zero; cannot compute cash mix.")

    cash_mask = snapshot["main_class"].fillna("").str.casefold().eq("cash") | snapshot[
        "vehicle_type"
    ].fillna("").str.lower().isin({"mmf", "cash"})
    cash_total = safe_float(snapshot.loc[cash_mask, "market_value"].sum())
    non_cash_total = total_value - cash_total
    cash_pct = ratio(cash_total, total_value) * 100

    spend_window_days = max(90, context.window.days)
    spend_window = TimeWindow(
        label=f"spend_trailing_{spend_window_days}d",
        start=context.window.end - timedelta(days=spend_window_days),
        end=context.window.end,
    )
    spend_frame = load_transactions_frame(context, window=spend_window)
    avg_monthly_spend = 0.0
    if not spend_frame.empty:
        total_spend = safe_float(spend_frame["spend_amount"].sum())
        avg_monthly_spend = total_spend / max(spend_window_days / 30.0, 1)

    runway_months = ratio(cash_total, avg_monthly_spend) if avg_monthly_spend else None

    summaries = [
        f"Cash & equivalents: ${cash_total:,.0f} ({cash_pct:.1f}% of ${total_value:,.0f}).",
    ]
    if avg_monthly_spend:
        summaries.append(
            f"Avg monthly spend (last {spend_window_days}d): ${avg_monthly_spend:,.0f}; cash runway ≈ {runway_months:.1f} months"
        )
    if cash_pct < 5:
        summaries.append("Cash cushion is thin (<5%).")
    elif cash_pct > 30:
        summaries.append("Cash overweight; consider deploying excess into targets.")

    tables = [
        TableSeries(
            name="Cash Mix",
            columns=["bucket", "value", "pct"],
            rows=[
                ["cash", round(cash_total, 2), round(cash_pct, 2)],
                ["non_cash", round(non_cash_total, 2), round(100 - cash_pct, 2)],
            ],
            metadata={"as_of_date": as_of_date},
        ),
        TableSeries(
            name="Cash Holdings",
            columns=["symbol", "account", "value"],
            rows=[
                [
                    row.get("symbol"),
                    row.get("account_name"),
                    round(safe_float(row.get("market_value")), 2),
                ]
                for _, row in snapshot.loc[cash_mask].iterrows()
            ],
            metadata={"as_of_date": as_of_date},
        ),
    ]

    json_payload: dict[str, Any] = {
        "as_of_date": as_of_date,
        "total_value": round(total_value, 2),
        "cash_total": round(cash_total, 2),
        "cash_pct": round(cash_pct, 4),
        "non_cash_total": round(non_cash_total, 2),
        "avg_monthly_spend": round(avg_monthly_spend, 2) if avg_monthly_spend else None,
        "runway_months": None if runway_months is None else round(runway_months, 2),
        "cash_holdings": snapshot.loc[cash_mask][
            ["symbol", "account_name", "market_value"]
        ].to_dict(orient="records"),
    }

    return AnalysisResult(
        title="Cash Mix",
        summary=summaries,
        tables=tables,
        json_payload=json_payload,
    )
