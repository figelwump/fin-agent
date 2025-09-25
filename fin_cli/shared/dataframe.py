"""Pandas helpers for loading windowed financial data from SQLite."""

from __future__ import annotations

import json
from typing import Any

try:
    import pandas as pd
except ImportError:  # pragma: no cover - pandas is an optional dependency
    pd = None  # type: ignore[assignment]

from fin_cli.fin_analyze.types import AnalysisContext, TimeWindow, WindowFrameSet
from fin_cli.shared.database import connect

# Known column order for transaction datasets; maintained manually to avoid repeated PRAGMA calls.
TRANSACTION_COLUMNS = [
    "transaction_id",
    "date",
    "merchant",
    "amount",
    "account_id",
    "account_name",
    "institution",
    "account_type",
    "category_id",
    "category",
    "subcategory",
    "original_description",
    "transaction_metadata",
    "category_auto_generated",
    "category_user_approved",
]

TRANSACTION_QUERY = """
SELECT
    t.id AS transaction_id,
    t.date AS date,
    t.merchant AS merchant,
    t.amount AS amount,
    t.account_id AS account_id,
    a.name AS account_name,
    a.institution AS institution,
    a.account_type AS account_type,
    t.category_id AS category_id,
    c.category AS category,
    c.subcategory AS subcategory,
    t.original_description AS original_description,
    t.metadata AS transaction_metadata,
    c.auto_generated AS category_auto_generated,
    c.user_approved AS category_user_approved
FROM transactions t
LEFT JOIN accounts a ON t.account_id = a.id
LEFT JOIN categories c ON t.category_id = c.id
WHERE t.date >= ? AND t.date < ?
ORDER BY t.date ASC, t.id ASC
"""

CATEGORY_TOTALS_QUERY = """
SELECT
    COALESCE(c.category, 'Uncategorized') AS category,
    COALESCE(c.subcategory, 'Uncategorized') AS subcategory,
    SUM(t.amount) AS total_amount,
    SUM(CASE WHEN t.amount >= 0 THEN t.amount ELSE 0 END) AS spend_amount,
    SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END) AS income_amount,
    COUNT(*) AS transaction_count
FROM transactions t
LEFT JOIN categories c ON t.category_id = c.id
WHERE t.date >= ? AND t.date < ?
GROUP BY category, subcategory
ORDER BY total_amount DESC
"""

RECURRING_CANDIDATES_QUERY = """
SELECT
    t.merchant,
    t.amount,
    t.date,
    t.account_id,
    a.name AS account_name,
    a.institution AS institution,
    c.category,
    c.subcategory,
    t.metadata AS transaction_metadata
FROM transactions t
LEFT JOIN accounts a ON t.account_id = a.id
LEFT JOIN categories c ON t.category_id = c.id
WHERE t.date >= ? AND t.date < ?
ORDER BY t.merchant ASC, t.date ASC
"""


def _ensure_pandas() -> "pd.DataFrame":
    """Return the pandas module or raise a helpful error if missing."""

    if pd is None:
        raise ImportError(
            "pandas is required for fin-analyze. Install the 'analysis' extra (pip install .[analysis])."
        )
    return pd


def load_transactions_frame(
    context: AnalysisContext,
    *,
    window: TimeWindow | None = None
) -> "pd.DataFrame":
    """Return denormalised transactions for a specific window."""

    pandas = _ensure_pandas()
    target_window = window or context.window
    params = (target_window.start.isoformat(), target_window.end.isoformat())

    with connect(context.app_config, read_only=True, apply_migrations=False) as connection:
        frame = pandas.read_sql_query(TRANSACTION_QUERY, connection, params=params)

    if frame.empty:
        frame = pandas.DataFrame(columns=TRANSACTION_COLUMNS)

    _normalise_transactions(frame, pandas=pandas)
    _attach_temporal_columns(frame, pandas=pandas)
    frame["window_label"] = target_window.label

    return frame


def load_category_totals(
    context: AnalysisContext,
    *,
    window: TimeWindow | None = None,
) -> "pd.DataFrame":
    """Aggregate category totals for the supplied window."""

    pandas = _ensure_pandas()
    target_window = window or context.window
    params = (target_window.start.isoformat(), target_window.end.isoformat())

    with connect(context.app_config, read_only=True, apply_migrations=False) as connection:
        frame = pandas.read_sql_query(CATEGORY_TOTALS_QUERY, connection, params=params)

    if frame.empty:
        frame = pandas.DataFrame(
            columns=["category", "subcategory", "total_amount", "spend_amount", "income_amount", "transaction_count"],
        )

    frame["window_label"] = target_window.label
    return frame


def load_recurring_candidates(
    context: AnalysisContext,
    *,
    window: TimeWindow | None = None,
) -> "pd.DataFrame":
    """Return transaction slices useful for subscription detection heuristics."""

    pandas = _ensure_pandas()
    target_window = window or context.window
    params = (target_window.start.isoformat(), target_window.end.isoformat())

    with connect(context.app_config, read_only=True, apply_migrations=False) as connection:
        frame = pandas.read_sql_query(RECURRING_CANDIDATES_QUERY, connection, params=params)

    if frame.empty:
        frame = pandas.DataFrame(columns=[
            "merchant",
            "amount",
            "date",
            "account_id",
            "account_name",
            "institution",
            "category",
            "subcategory",
            "transaction_metadata",
        ])

    frame["date"] = pandas.to_datetime(frame["date"], errors="coerce")
    frame["window_label"] = target_window.label
    return frame


def build_window_frames(context: AnalysisContext) -> WindowFrameSet:
    """Load primary/comparison transaction frames for an analysis run."""

    primary = load_transactions_frame(context, window=context.window)
    comparison_frame = (
        load_transactions_frame(context, window=context.comparison_window)
        if context.comparison_window
        else None
    )

    metadata: dict[str, Any] = {
        "window_label": context.window.label,
        "comparison_label": context.comparison_window.label if context.comparison_window else None,
        "threshold": context.threshold,
    }

    return WindowFrameSet(
        window=context.window,
        frame=primary,
        comparison_window=context.comparison_window,
        comparison_frame=comparison_frame,
        metadata=metadata,
    )


def _normalise_transactions(frame: "pd.DataFrame", *, pandas: "pd") -> None:
    """Coerce types and derived columns in place."""

    frame["date"] = pandas.to_datetime(frame["date"], errors="coerce")
    frame["amount"] = frame["amount"].astype(float)
    frame["is_credit"] = frame["amount"] > 0
    frame["spend_amount"] = (-frame["amount"]).where(frame["amount"] < 0, 0.0)
    frame["income_amount"] = frame["amount"].where(frame["amount"] > 0, 0.0)
    if "transaction_metadata" not in frame:
        frame["transaction_metadata"] = pandas.Series(dtype=object)
    mask = frame["transaction_metadata"].notna()
    if mask.any():
        frame.loc[mask, "transaction_metadata"] = frame.loc[mask, "transaction_metadata"].apply(_safe_json_load)


def _attach_temporal_columns(frame: "pd.DataFrame", *, pandas: "pd") -> None:
    """Add time-derived helper columns used by multiple analyzers."""

    if frame.empty:
        return
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.to_period("M").astype(str)
    frame["day"] = frame["date"].dt.day
    frame["weekday"] = frame["date"].dt.day_name()
    frame["week_of_year"] = frame["date"].dt.isocalendar().week.astype(int)


def _safe_json_load(value: Any) -> Any:
    """Best-effort JSON loader that keeps raw values when decoding fails."""

    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):  # pragma: no cover - defensive fallback
        return value

