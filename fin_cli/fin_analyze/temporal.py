"""Utilities for parsing month/period/year flags into concrete time windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Tuple

from dateutil.relativedelta import relativedelta

from .types import AnalysisConfigurationError, TimeWindow


@dataclass(frozen=True)
class WindowResolution:
    """Holds primary and comparison windows for an analysis run."""

    window: TimeWindow
    comparison: TimeWindow | None


def resolve_windows(
    *,
    month: str | None,
    period: str | None,
    year: int | None,
    last_twelve_months: bool,
    compare: bool,
    today: date | None = None,
) -> WindowResolution:
    """Resolve CLI window flags into concrete primary/comparison windows."""

    ensure_exclusive_flags(month, period, year, last_twelve_months)
    anchor_today = today or datetime.now(timezone.utc).date()

    if month:
        window = _from_month(month)
    elif period:
        window = _from_period(period, anchor_today)
    elif year is not None:
        window = _from_year(year)
    elif last_twelve_months:
        window = _rolling_twelve_months(anchor_today)
    else:
        window = _default_current_month(anchor_today)

    comparison = _derive_comparison(window) if compare else None
    return WindowResolution(window=window, comparison=comparison)


# ----- Window helpers -----------------------------------------------------------------------


def ensure_exclusive_flags(
    month: str | None,
    period: str | None,
    year: int | None,
    last_twelve_months: bool,
) -> None:
    """Raise when more than one mutually exclusive window selector is provided."""

    provided = [bool(month), bool(period), year is not None, last_twelve_months]
    if sum(1 for flag in provided if flag) > 1:
        raise AnalysisConfigurationError(
            "Use only one of --month, --period, --year, or --last-12-months."
        )


def _from_month(month: str) -> TimeWindow:
    try:
        start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise AnalysisConfigurationError(
            f"Invalid month '{month}'. Expected YYYY-MM format."
        ) from exc
    end = start + relativedelta(months=1)
    label = f"month_{start:%Y_%m}"
    return TimeWindow(label=label, start=start, end=end)


def _from_period(period: str, today: date) -> TimeWindow:
    if not period:
        raise AnalysisConfigurationError("Period value is required when --period is supplied.")
    unit = period[-1].lower()
    magnitude_str = period[:-1]
    if unit not in {"d", "w", "m"}:
        raise AnalysisConfigurationError(
            f"Unsupported period '{period}'. Use suffix d, w, or m (e.g., 30d, 6w, 3m)."
        )
    try:
        magnitude = int(magnitude_str)
    except ValueError as exc:
        raise AnalysisConfigurationError(
            f"Invalid period magnitude in '{period}'. Expected integer before unit."
        ) from exc
    if magnitude <= 0:
        raise AnalysisConfigurationError("Period magnitude must be positive.")

    end = today + relativedelta(days=1)
    if unit == "d":
        start = end - relativedelta(days=magnitude)
    elif unit == "w":
        start = end - relativedelta(weeks=magnitude)
    else:  # unit == "m"
        start = end - relativedelta(months=magnitude)
    label = f"period_{start:%Y_%m_%d}_to_{end:%Y_%m_%d}"
    return TimeWindow(label=label, start=start, end=end)


def _from_year(year: int) -> TimeWindow:
    if year < 1900 or year > 9999:
        raise AnalysisConfigurationError(f"Year '{year}' is out of supported range.")
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    label = f"calendar_year_{year}"
    return TimeWindow(label=label, start=start, end=end)


def _rolling_twelve_months(today: date) -> TimeWindow:
    anchor = today.replace(day=1)
    start = anchor - relativedelta(months=12)
    label = f"last_12_months_{start:%Y_%m}_to_{anchor:%Y_%m}"
    return TimeWindow(label=label, start=start, end=anchor)


def _default_current_month(today: date) -> TimeWindow:
    anchor = today.replace(day=1)
    end = anchor + relativedelta(months=1)
    label = f"month_{anchor:%Y_%m}"
    return TimeWindow(label=label, start=anchor, end=end)


def _derive_comparison(window: TimeWindow) -> TimeWindow:
    """Return a prior window of equal length immediately before the provided window."""

    delta_days = window.days
    if delta_days <= 0:
        raise AnalysisConfigurationError("Window duration must be positive for comparison mode.")
    start = window.start - relativedelta(days=delta_days)
    end = window.end - relativedelta(days=delta_days)

    if window.label.startswith("calendar_year_"):
        label = f"preceding_{window.label}"
    elif window.label.startswith("last_12_months"):
        label = window.label.replace("last_12_months", "preceding_12_months", 1)
    elif window.label.startswith("month_"):
        label = f"preceding_{window.label}"
    else:
        label = f"preceding_{window.label}"
    return TimeWindow(label=label, start=start, end=end)

