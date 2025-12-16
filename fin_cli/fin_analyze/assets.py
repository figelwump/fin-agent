"""Asset data helpers for fin-analyze asset tracking analyzers.

The helpers here keep SQL close to the analyzers while reusing the saved
queries defined for `fin-query`. They intentionally return pandas DataFrames
so analyzers can perform vectorised calculations and render CSV-friendly
tables without re-implementing precedence logic (source priority + recency).
"""

from __future__ import annotations

from datetime import date, timedelta

try:  # Optional dependency; analyzers will raise a clear error when missing.
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - pandas is an optional extra
    pd = None  # type: ignore[assignment]

from fin_cli.fin_analyze.metrics import safe_float
from fin_cli.fin_analyze.types import AnalysisContext, AnalysisError
from fin_cli.fin_query import executor
from fin_cli.shared.database import connect

VALUATION_TIMESERIES_SQL = """
WITH ranked AS (
    SELECT
        hv.holding_id,
        hv.as_of_date,
        hv.market_value,
        hv.quantity,
        hv.price,
        hv.fees,
        hv.accrued_interest,
        hv.valuation_currency,
        hv.fx_rate_used,
        asrc.priority,
        ROW_NUMBER() OVER (
            PARTITION BY hv.holding_id, hv.as_of_date
            ORDER BY asrc.priority ASC, hv.as_of_datetime DESC, hv.ingested_at DESC
        ) AS rn
    FROM holding_values hv
    JOIN asset_sources asrc ON asrc.id = hv.source_id
    WHERE hv.as_of_date >= :start_date AND hv.as_of_date < :end_date
)
SELECT
    r.as_of_date,
    r.holding_id,
    r.market_value,
    r.quantity,
    r.price,
    r.fees,
    r.accrued_interest,
    r.valuation_currency,
    r.fx_rate_used,
    h.account_id,
    i.id AS instrument_id,
    i.symbol,
    i.name AS instrument_name,
    i.vehicle_type,
    ac.main_class,
    ac.sub_class
FROM ranked r
JOIN holdings h ON h.id = r.holding_id
JOIN instruments i ON i.id = h.instrument_id
LEFT JOIN instrument_classifications ic ON ic.instrument_id = i.id AND ic.is_primary = 1
LEFT JOIN asset_classes ac ON ac.id = ic.asset_class_id
WHERE r.rn = 1
  AND h.status = 'active'
  AND (:account_id IS NULL OR h.account_id = :account_id)
ORDER BY r.as_of_date ASC, r.holding_id ASC;
"""


def ensure_pandas():
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")
    return pd


def window_as_of(context: AnalysisContext) -> str:
    """Compute the default as_of_date for asset snapshots from the context window."""

    anchor = context.window.end - timedelta(days=1)
    return anchor.isoformat()


def load_portfolio_snapshot(context: AnalysisContext, *, as_of_date: str | None) -> pd.DataFrame:
    """Load the latest valuation per holding using the saved `portfolio_snapshot` query."""

    pandas = ensure_pandas()
    result = executor.run_saved_query(
        config=context.app_config,
        name="portfolio_snapshot",
        runtime_params={"as_of_date": as_of_date, "account_id": context.options.get("account_id")},
        limit=500,
    )
    frame = pandas.DataFrame(result.rows, columns=result.columns)
    if not frame.empty:
        frame["market_value"] = frame["market_value"].apply(safe_float)
    return frame


def load_allocation_by_class(context: AnalysisContext, *, as_of_date: str | None) -> pd.DataFrame:
    pandas = ensure_pandas()
    result = executor.run_saved_query(
        config=context.app_config,
        name="allocation_by_class",
        runtime_params={"as_of_date": as_of_date, "account_id": context.options.get("account_id")},
        limit=200,
    )
    return pandas.DataFrame(result.rows, columns=result.columns)


def load_allocation_by_account(context: AnalysisContext, *, as_of_date: str | None) -> pd.DataFrame:
    pandas = ensure_pandas()
    result = executor.run_saved_query(
        config=context.app_config,
        name="allocation_by_account",
        runtime_params={"as_of_date": as_of_date},
        limit=100,
    )
    return pandas.DataFrame(result.rows, columns=result.columns)


def load_valuation_timeseries(
    context: AnalysisContext,
    *,
    start_date: date,
    end_date: date,
    account_id: int | None = None,
) -> pd.DataFrame:
    """Return a holding-level valuation timeseries for the requested window."""

    pandas = ensure_pandas()
    with connect(context.app_config, read_only=True, apply_migrations=False) as connection:
        frame = pandas.read_sql_query(
            VALUATION_TIMESERIES_SQL,
            connection,
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "account_id": account_id,
            },
        )

    if frame.empty:
        return frame

    frame["as_of_date"] = pandas.to_datetime(frame["as_of_date"], errors="coerce")
    for column in ("market_value", "price", "fees", "accrued_interest", "fx_rate_used"):
        if column in frame.columns:
            frame[column] = frame[column].apply(safe_float)
    return frame
