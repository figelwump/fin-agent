"""Unusual spending analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ..metrics import percentage_change, safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries
from ...shared.dataframe import build_window_frames


@dataclass(frozen=True)
class AnomalyRecord:
    merchant: str
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
        raise AnalysisError("No transactions available for the selected window.")

    sensitivity = int(context.options.get("sensitivity", 3) or 3)
    sensitivity = min(max(sensitivity, 1), 5)
    base_threshold = context.threshold if context.threshold is not None else 0.10
    multiplier = {1: 0.75, 2: 1.0, 3: 1.25, 4: 1.5, 5: 2.0}[sensitivity]
    threshold_pct = base_threshold * multiplier

    current_totals = _merchant_metrics(current)
    comparison_totals = _merchant_metrics(frames.comparison_frame) if frames.comparison_frame is not None else {}

    anomalies: list[AnomalyRecord] = []
    new_merchants: list[str] = []
    increased_frequency: list[str] = []

    for merchant, metrics in current_totals.items():
        baseline = comparison_totals.get(merchant)
        spend_change = percentage_change(metrics.spend, baseline.spend if baseline else None) if baseline else None
        visit_change = percentage_change(metrics.visits, baseline.visits if baseline else None) if baseline else None

        notes: list[str] = []
        if baseline is None:
            notes.append("new merchant")
            new_merchants.append(merchant)
            if metrics.spend >= 50.0:
                anomalies.append(
                    AnomalyRecord(
                        merchant=merchant,
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
            increased_frequency.append(merchant)

        should_flag = False
        if spend_change is not None and spend_change > threshold_pct and metrics.spend >= 25.0:
            should_flag = True
            notes.append(f"spend +{spend_change * 100:.1f}%")
        elif spend_change is None and metrics.spend >= 25.0:
            should_flag = True

        if should_flag:
            anomalies.append(
                AnomalyRecord(
                    merchant=merchant,
                    spend=metrics.spend,
                    baseline_spend=baseline.spend,
                    spend_change_pct=spend_change,
                    visits=metrics.visits,
                    baseline_visits=baseline.visits,
                    visit_change_pct=visit_change,
                    notes=", ".join(notes),
                )
            )

    if not anomalies and not new_merchants:
        raise AnalysisError("No unusual spending patterns detected with the current sensitivity.")

    anomalies.sort(key=lambda record: record.spend_change_pct or 0, reverse=True)

    table = _build_table(anomalies)
    summary_lines = _build_summary(anomalies, new_merchants, increased_frequency)

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "threshold_pct": round(threshold_pct, 4),
        "sensitivity": sensitivity,
        "anomalies": [
            {
                "merchant": record.merchant,
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
    }

    return AnalysisResult(
        title="Unusual Spending",
        summary=summary_lines,
        tables=[table],
        json_payload=json_payload,
    )


@dataclass(frozen=True)
class _MerchantMetrics:
    spend: float
    visits: int


def _merchant_metrics(frame: pd.DataFrame | None) -> dict[str, _MerchantMetrics]:
    if frame is None or frame.empty:
        return {}

    working = frame.copy()
    working["spend_amount"] = working["spend_amount"].astype(float)
    grouped = working.groupby("merchant", sort=False)
    metrics: dict[str, _MerchantMetrics] = {}
    for merchant, group in grouped:
        spend_total = safe_float(group["spend_amount"].sum())
        visits = int(len(group))
        if spend_total <= 0:
            continue
        metrics[merchant] = _MerchantMetrics(spend=spend_total, visits=visits)
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

