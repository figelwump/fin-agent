"""Pandas helpers for loading windowed financial data from SQLite."""

from __future__ import annotations

import json
from typing import Any, Mapping

try:
    import pandas as pd
except ImportError:  # pragma: no cover - pandas is an optional dependency
    pd = None  # type: ignore[assignment]

from fin_cli.fin_analyze.types import AnalysisContext, TimeWindow, WindowFrameSet
from fin_cli.shared.database import connect
from fin_cli.shared.merchants import AGGREGATOR_LABELS, GENERIC_PLATFORMS, friendly_display_name, merchant_pattern_key, normalize_merchant

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

# Negative ledger amounts represent spend; convert to absolute values so analyzers
# receive comparable positive numbers while preserving positive income values.
CATEGORY_TOTALS_QUERY = """
SELECT
    COALESCE(c.category, 'Uncategorized') AS category,
    COALESCE(c.subcategory, 'Uncategorized') AS subcategory,
    SUM(t.amount) AS total_amount,
    SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END) AS spend_amount,
    SUM(CASE WHEN t.amount >= 0 THEN t.amount ELSE 0 END) AS income_amount,
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
    _attach_merchant_fields(frame)
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



def _attach_merchant_fields(frame: "pd.DataFrame") -> None:
    canonical_keys: list[str] = []
    display_names: list[str] = []
    for merchant, metadata in zip(frame.get("merchant", []), frame.get("transaction_metadata", [])):
        canonical, display = _derive_merchant_fields(str(merchant), metadata)
        canonical_keys.append(canonical)
        display_names.append(display)
    frame["merchant_canonical"] = canonical_keys
    frame["merchant_display"] = display_names


def _derive_merchant_fields(merchant: str, metadata: Any) -> tuple[str, str]:
    meta = metadata if isinstance(metadata, Mapping) else {}
    canonical: str | None = None
    display_candidates: list[str] = []

    pattern_display = meta.get("merchant_pattern_display") if isinstance(meta, Mapping) else None
    if isinstance(pattern_display, str) and pattern_display.strip():
        display_candidates.append(pattern_display.strip())

    display_hint = meta.get("merchant_display") if isinstance(meta, Mapping) else None
    if isinstance(display_hint, str) and display_hint.strip():
        display_candidates.append(display_hint.strip())

    pattern_key = meta.get("merchant_pattern_key") if isinstance(meta, Mapping) else None

    metadata_block = meta.get("merchant_metadata") if isinstance(meta, Mapping) else None
    platform = None
    if isinstance(metadata_block, Mapping):
        platform = metadata_block.get("platform")
        for key in ("restaurant_name", "hotel_name", "merchant_name", "business_name"):
            value = metadata_block.get(key)
            if isinstance(value, str) and value.strip():
                display_candidates.append(value.strip())

    if platform:
        platform_upper = normalize_merchant(str(platform))
        if platform_upper in AGGREGATOR_LABELS:
            canonical = platform_upper
            display_candidates.insert(0, AGGREGATOR_LABELS[platform_upper])
        elif platform_upper == "HOTEL" and isinstance(metadata_block, Mapping) and metadata_block.get("hotel_name"):
            hotel_name = str(metadata_block["hotel_name"]).strip()
            if hotel_name:
                canonical = normalize_merchant(hotel_name)
                display_candidates.insert(0, hotel_name)
        elif platform_upper not in GENERIC_PLATFORMS and platform_upper:
            canonical = platform_upper
            display_candidates.insert(0, str(platform).strip())

    if canonical is None and isinstance(pattern_key, str) and pattern_key.strip():
        canonical = normalize_merchant(pattern_key)

    normalized_merchant = normalize_merchant(merchant)
    if canonical is None or canonical not in AGGREGATOR_LABELS:
        for agg_key, label in AGGREGATOR_LABELS.items():
            if agg_key in normalized_merchant:
                canonical = agg_key
                if label not in display_candidates:
                    display_candidates.insert(0, label)
                break

    if canonical is None:
        canonical = merchant_pattern_key(merchant) or normalized_merchant or "UNKNOWN"

    display = _select_display(canonical, display_candidates, merchant)
    return canonical, display


def _select_display(canonical: str, candidates: list[str], merchant: str) -> str:
    for candidate in candidates:
        cleaned = candidate.strip()
        if not cleaned:
            continue
        if "•" in cleaned:
            parts = [part.strip().title() for part in cleaned.split("•") if part.strip()]
            if parts:
                return " • ".join(parts)
        if cleaned.isupper() and len(cleaned) > 3:
            return cleaned.title()
        return cleaned
    return friendly_display_name(canonical, [merchant])

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
