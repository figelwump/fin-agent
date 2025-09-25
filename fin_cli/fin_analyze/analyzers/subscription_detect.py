"""Subscription detection analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Sequence

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ..metrics import percentage_change, safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries
from ...shared.dataframe import load_recurring_candidates


@dataclass(frozen=True)
class SubscriptionRecord:
    merchant: str
    average_amount: float
    total_amount: float
    occurrences: int
    cadence_days: float | None
    last_charge: pd.Timestamp
    status: str
    confidence: float
    change_pct: float | None
    notes: str


def analyze(context: AnalysisContext) -> AnalysisResult:
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    include_inactive = bool(context.options.get("include_inactive"))
    min_confidence = float(context.options.get("min_confidence", 0.0) or 0.0)
    price_threshold = context.threshold if context.threshold is not None else 0.05

    current = load_recurring_candidates(context)
    if current.empty:
        raise AnalysisError("No recurring transactions found for the selected window.")

    comparison_frame = None
    if context.comparison_window is not None:
        comparison_frame = load_recurring_candidates(context, window=context.comparison_window)

    comparison_stats = _summarise_merchants(comparison_frame) if comparison_frame is not None else {}
    current_stats = _summarise_merchants(current)

    if not current_stats:
        raise AnalysisError("No subscription-like merchants detected in the selected window.")

    records: list[SubscriptionRecord] = []
    new_merchants: list[dict[str, Any]] = []
    price_increases: list[dict[str, Any]] = []

    window_end = pd.Timestamp(context.window.end)
    for merchant, stats in current_stats.items():
        baseline = comparison_stats.get(merchant)
        change_pct = None
        notes: list[str] = []
        if baseline:
            change_pct = percentage_change(stats.average_amount, baseline.average_amount)
            if change_pct and change_pct > price_threshold:
                notes.append(f"price +{change_pct * 100:.1f}%")
                price_increases.append(
                    {
                        "merchant": merchant,
                        "change_pct": round(change_pct, 4),
                        "previous_average": round(baseline.average_amount, 2),
                        "current_average": round(stats.average_amount, 2),
                    }
                )
        else:
            notes.append("new")
            new_merchants.append(
                {
                    "merchant": merchant,
                    "average_amount": round(stats.average_amount, 2),
                    "occurrences": stats.occurrences,
                }
            )

        status = _resolve_status(stats.last_charge, window_end)
        if status != "active" and not include_inactive:
            continue

        confidence = _estimate_confidence(stats)
        if confidence < min_confidence:
            continue

        records.append(
            SubscriptionRecord(
                merchant=merchant,
                average_amount=stats.average_amount,
                total_amount=stats.total_amount,
                occurrences=stats.occurrences,
                cadence_days=stats.cadence_days,
                last_charge=stats.last_charge,
                status=status,
                confidence=confidence,
                change_pct=change_pct,
                notes=", ".join(notes) if notes else "",
            )
        )

    cancelled: list[dict[str, Any]] = []
    if comparison_stats:
        missing = set(comparison_stats) - set(current_stats)
        for merchant in missing:
            stats = comparison_stats[merchant]
            cancelled.append(
                {
                    "merchant": merchant,
                    "last_seen": stats.last_charge.date().isoformat(),
                    "average_amount": round(stats.average_amount, 2),
                }
            )

    if not records and not cancelled:
        raise AnalysisError("No subscriptions matched the configured filters.")

    table = _build_table(records)
    summary_lines = _build_summary(records, new_merchants, price_increases)

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "threshold": price_threshold,
        "subscriptions": [
            {
                "merchant": record.merchant,
                "average_amount": round(record.average_amount, 2),
                "total_amount": round(record.total_amount, 2),
                "occurrences": record.occurrences,
                "cadence_days": record.cadence_days,
                "status": record.status,
                "confidence": round(record.confidence, 3),
                "change_pct": None if record.change_pct is None else round(record.change_pct, 4),
                "notes": record.notes,
            }
            for record in records
        ],
        "new_merchants": new_merchants,
        "price_increases": price_increases,
        "cancelled": cancelled,
    }

    return AnalysisResult(
        title="Subscription Detection",
        summary=summary_lines,
        tables=[table],
        json_payload=json_payload,
    )


@dataclass(frozen=True)
class _MerchantStats:
    average_amount: float
    total_amount: float
    occurrences: int
    cadence_days: float | None
    last_charge: pd.Timestamp


def _summarise_merchants(frame: pd.DataFrame | None) -> dict[str, _MerchantStats]:
    if frame is None or frame.empty:
        return {}

    working = frame.copy()
    working["amount"] = working["amount"].astype(float).abs()
    working.sort_values(["merchant", "date"], inplace=True)

    stats: dict[str, _MerchantStats] = {}
    for merchant, group in working.groupby("merchant"):
        amounts = group["amount"]
        total = safe_float(amounts.sum())
        avg = safe_float(amounts.mean())
        occurrences = int(len(group))
        cadence = None
        if occurrences > 1:
            diffs = group["date"].diff().dt.days.dropna()
            if not diffs.empty:
                cadence = float(diffs.median())
        last_charge = group["date"].max()
        stats[merchant] = _MerchantStats(
            average_amount=avg,
            total_amount=total,
            occurrences=occurrences,
            cadence_days=cadence,
            last_charge=last_charge,
        )
    return stats


def _resolve_status(last_charge: pd.Timestamp, window_end: pd.Timestamp) -> str:
    delta = window_end - last_charge
    if delta <= timedelta(days=45):
        return "active"
    return "inactive"


def _estimate_confidence(stats: _MerchantStats) -> float:
    base = min(1.0, stats.occurrences / 6)
    cadence_boost = 0.0
    if stats.cadence_days is not None:
        # Encourage near-monthly cadence (approx 25-35 days)
        deviation = abs(stats.cadence_days - 30)
        cadence_boost = max(0.0, 1 - min(deviation, 30) / 30)
    confidence = (base * 0.6) + (cadence_boost * 0.4)
    return round(min(1.0, confidence), 3)


def _build_table(records: Sequence[SubscriptionRecord]) -> TableSeries:
    rows: list[list[Any]] = []
    for record in records:
        rows.append(
            [
                record.merchant,
                round(record.average_amount, 2),
                round(record.total_amount, 2),
                record.occurrences,
                None if record.cadence_days is None else round(record.cadence_days, 1),
                record.status,
                round(record.confidence, 2),
                record.notes,
            ]
        )
    return TableSeries(
        name="subscriptions",
        columns=[
            "Merchant",
            "Avg Amount",
            "Total Amount",
            "Occurrences",
            "Cadence (days)",
            "Status",
            "Confidence",
            "Notes",
        ],
        rows=rows,
        metadata={"unit": "USD"},
    )


def _build_summary(
    records: Sequence[SubscriptionRecord],
    new_merchants: Sequence[dict[str, Any]],
    price_increases: Sequence[dict[str, Any]],
) -> list[str]:
    if not records and not new_merchants and not price_increases:
        return ["No subscriptions matched the configured filters."]

    active = sum(1 for rec in records if rec.status == "active")
    inactive = sum(1 for rec in records if rec.status == "inactive")

    lines = [
        f"Subscriptions detected: {len(records)} (active {active}, inactive {inactive}).",
    ]
    if new_merchants:
        lines.append(f"New subscriptions this window: {len(new_merchants)}.")
    if price_increases:
        lines.append(f"Price increases flagged: {len(price_increases)}.")
    return lines

