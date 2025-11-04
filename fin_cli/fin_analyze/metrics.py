"""Common metric helpers for fin-analyze."""

from __future__ import annotations

from typing import Any


def percentage_change(current: float | None, previous: float | None) -> float | None:
    """Return percentage change from previous to current, None when undefined."""

    if current is None or previous is None:
        return None
    try:
        if previous == 0:
            return None
        return (current - previous) / previous
    except ZeroDivisionError:  # pragma: no cover - guarded above
        return None


def significance(change_pct: float | None, threshold: float | None) -> bool:
    """True when the absolute change exceeds the configured threshold."""

    if change_pct is None:
        return False
    effective = threshold if threshold is not None else 0.10
    return abs(change_pct) >= effective


def safe_float(value: Any) -> float:
    """Convert pandas/numpy scalar to float for JSON compatibility."""

    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def jaccard_similarity(a: set[Any], b: set[Any]) -> float:
    """Return Jaccard similarity between two sets (0-1 range)."""

    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return intersection / union


def ratio(numerator: float, denominator: float) -> float:
    """Safe ratio helper returning 0 when denominator is zero."""

    if denominator == 0:
        return 0.0
    return numerator / denominator
