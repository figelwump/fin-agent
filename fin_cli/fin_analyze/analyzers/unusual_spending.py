"""Unusual spending analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Sequence

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ..metrics import percentage_change, safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries, TimeWindow
from ...shared.dataframe import build_window_frames, load_transactions_frame
from ...shared.merchants import friendly_display_name


@dataclass(frozen=True)
class AnomalyRecord:
    merchant: str
    canonical: str
    spend: float
    baseline_spend: float
    spend_change_pct: float | None
    visits: int
    baseline_visits: int
    visit_change_pct: float | None
    notes: str


def analyze(context: AnalysisContext) -> AnalysisResult:
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    frames = build_window_frames(context)
    current = frames.frame
    if current.empty:
        raise AnalysisError("No transactions available for the selected window. Suggestion: Try using a longer time period (e.g., 6m, 12m, 24m, 36m, or all) or ask the user if they have imported any transactions yet.")

    baseline_frame = frames.comparison_frame
    baseline_window = frames.comparison_window
    baseline_source = "provided"
    if baseline_frame is None or frames.comparison_empty():
        fallback_window = _fallback_baseline_window(context.window)
        fallback_frame = load_transactions_frame(context, window=fallback_window)
        if fallback_frame is not None and not fallback_frame.empty:
            baseline_frame = fallback_frame
            baseline_window = fallback_window
            baseline_source = "fallback"
        else:
            baseline_frame = None
            if baseline_window is None:
                baseline_window = fallback_window
            baseline_source = "missing"

    sensitivity = int(context.options.get("sensitivity", 3) or 3)
    sensitivity = min(max(sensitivity, 1), 5)
    base_threshold = context.threshold if context.threshold is not None else 0.10
    multiplier = {1: 0.75, 2: 1.0, 3: 1.25, 4: 1.5, 5: 2.0}[sensitivity]
    threshold_pct = base_threshold * multiplier

    current_totals = _merchant_metrics(current)
    comparison_totals = _merchant_metrics(baseline_frame)
    baseline_available = bool(comparison_totals)

    anomalies: list[AnomalyRecord] = []
    new_merchants: list[str] = []
    seen_new_merchants: set[str] = set()
    increased_frequency: set[str] = set()

    for canonical, metrics in current_totals.items():
        if not baseline_available:
            if canonical not in seen_new_merchants:
                seen_new_merchants.add(canonical)
                new_merchants.append(metrics.display_name)
            continue

        baseline = comparison_totals.get(canonical)
        spend_change = percentage_change(metrics.spend, baseline.spend if baseline else None) if baseline else None
        visit_change = percentage_change(metrics.visits, baseline.visits if baseline else None) if baseline else None

        notes: list[str] = []
        if baseline is None:
            notes.append("new merchant")
            # Track via canonical key so multiple raw variants collapse into one entry.
            if canonical not in seen_new_merchants:
                seen_new_merchants.add(canonical)
                new_merchants.append(metrics.display_name)
            if metrics.spend >= 50.0:
                anomalies.append(
                    AnomalyRecord(
                        merchant=metrics.display_name,
                        canonical=metrics.canonical,
                        spend=metrics.spend,
                        baseline_spend=0.0,
                        spend_change_pct=None,
                        visits=metrics.visits,
                        baseline_visits=0,
                        visit_change_pct=None,
                        notes=", ".join(notes),
                    )
                )
            continue

        if visit_change and visit_change > threshold_pct:
            notes.append(f"visits +{visit_change * 100:.1f}%")
            increased_frequency.add(metrics.display_name)

        should_flag = False
        if spend_change is not None and spend_change > threshold_pct and metrics.spend >= 25.0:
            should_flag = True
            notes.append(f"spend +{spend_change * 100:.1f}%")
        elif spend_change is None and metrics.spend >= 25.0:
            should_flag = True

        if should_flag:
            anomalies.append(
                AnomalyRecord(
                    merchant=metrics.display_name,
                    canonical=metrics.canonical,
                    spend=metrics.spend,
                    baseline_spend=baseline.spend,
                    spend_change_pct=spend_change,
                    visits=metrics.visits,
                    baseline_visits=baseline.visits,
                    visit_change_pct=visit_change,
                    notes=", ".join(notes),
                )
            )

    anomalies.sort(key=lambda record: record.spend_change_pct or 0, reverse=True)

    table = _build_table(anomalies)
    summary_lines = _build_summary(anomalies, new_merchants, sorted(increased_frequency))

    fallback_recommended = False
    if not baseline_available:
        summary_lines.append("Baseline window lacked transactions; heuristics limited to listing new merchants.")
        fallback_recommended = True
    elif not anomalies:
        summary_lines.append("No spending anomalies met heuristic thresholds; LLM review recommended.")
        fallback_recommended = True

    if fallback_recommended:
        context.cli_ctx.logger.info(
            f"unusual_spending: limited heuristic insight (baseline_source={baseline_source})."
        )

    baseline_payload: dict[str, Any] = {
        "source": baseline_source,
        "has_data": baseline_available,
        "row_count": 0 if baseline_frame is None else int(len(baseline_frame)),
    }
    if baseline_window is not None:
        baseline_payload["window"] = {
            "label": baseline_window.label,
            "start": baseline_window.start.isoformat(),
            "end": baseline_window.end.isoformat(),
        }

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "threshold_pct": round(threshold_pct, 4),
        "sensitivity": sensitivity,
        "baseline": baseline_payload,
        "anomalies": [
            {
                "merchant": record.merchant,
                "canonical": record.canonical,
                "spend": round(record.spend, 2),
                "baseline_spend": round(record.baseline_spend, 2),
                "spend_change_pct": None
                if record.spend_change_pct is None
                else round(record.spend_change_pct, 4),
                "visits": record.visits,
                "baseline_visits": record.baseline_visits,
                "visit_change_pct": None
                if record.visit_change_pct is None
                else round(record.visit_change_pct, 4),
                "notes": record.notes,
            }
            for record in anomalies
        ],
        "new_merchants": new_merchants,
        "fallback_recommended": fallback_recommended,
    }

    return AnalysisResult(
        title="Unusual Spending",
        summary=summary_lines,
        tables=[table],
        json_payload=json_payload,
    )


@dataclass(frozen=True)
class _MerchantMetrics:
    canonical: str
    display_name: str
    spend: float
    visits: int


def _merchant_metrics(frame: pd.DataFrame | None) -> dict[str, _MerchantMetrics]:
    if frame is None or frame.empty:
        return {}

    working = frame.copy()
    working["spend_amount"] = working["spend_amount"].astype(float)
    canonical_col = "merchant_canonical" if "merchant_canonical" in working.columns else "merchant"
    display_col = "merchant_display" if "merchant_display" in working.columns else "merchant"
    # Group by canonical merchant keys so downstream anomaly detection treats
    # distinct raw strings (e.g., order numbers) as the same merchant.
    grouped = working.groupby(canonical_col, sort=False)
    metrics: dict[str, _MerchantMetrics] = {}
    for canonical, group in grouped:
        spend_total = safe_float(group["spend_amount"].sum())
        visits = int(len(group))
        if spend_total <= 0:
            continue
        display_series = group[display_col].dropna().astype(str)
        if not display_series.empty:
            mode_values = display_series.mode()
            display_name = mode_values.iloc[0] if not mode_values.empty else display_series.iloc[0]
        else:
            raw_values = set(group["merchant"].astype(str))
            display_name = friendly_display_name(str(canonical), raw_values)
        canonical_key = str(canonical) if canonical is not None else "UNKNOWN"
        canonical_key = canonical_key.strip() or "UNKNOWN"
        metrics[canonical_key] = _MerchantMetrics(
            canonical=canonical_key,
            display_name=display_name,
            spend=spend_total,
            visits=visits,
        )
    return metrics


def _build_table(records: Sequence[AnomalyRecord]) -> TableSeries:
    rows: list[list[Any]] = []
    for record in records:
        rows.append(
            [
                record.merchant,
                round(record.spend, 2),
                round(record.baseline_spend, 2),
                None if record.spend_change_pct is None else round(record.spend_change_pct * 100, 2),
                record.visits,
                record.baseline_visits,
                None
                if record.visit_change_pct is None
                else round(record.visit_change_pct * 100, 2),
                record.notes,
            ]
        )
    return TableSeries(
        name="unusual_spending",
        columns=[
            "Merchant",
            "Spend",
            "Baseline Spend",
            "Change %",
            "Visits",
            "Baseline Visits",
            "Visit Change %",
            "Notes",
        ],
        rows=rows,
        metadata={"unit": "USD"},
    )


def _build_summary(
    anomalies: Sequence[AnomalyRecord],
    new_merchants: Sequence[str],
    increased_frequency: Sequence[str],
) -> list[str]:
    lines = []
    if anomalies:
        lines.append(f"Anomalies detected: {len(anomalies)} merchants flagged.")
    if new_merchants:
        lines.append(f"New merchants this window: {len(new_merchants)}.")
    if increased_frequency:
        lines.append(f"Merchants with notable visit increases: {len(increased_frequency)}.")
    if not lines:
        lines.append("No unusual spending patterns detected.")
    return lines


def _fallback_baseline_window(window: TimeWindow) -> TimeWindow:
    span_days = max(window.days, 30)
    start = window.start - timedelta(days=span_days)
    label = f"{window.label}_baseline_fallback"
    return TimeWindow(label=label, start=start, end=window.start)
