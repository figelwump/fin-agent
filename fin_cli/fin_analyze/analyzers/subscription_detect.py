"""Subscription detection analyzer."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ...shared.dataframe import load_recurring_candidates
from ..metrics import percentage_change, safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries

CADENCE_MIN_DAYS = 20
CADENCE_MAX_DAYS = 365
VARIANCE_LIMIT_DEFAULT = 0.3
VARIANCE_LIMIT_RELAXED = 0.6
SMALL_AMOUNT_VARIANCE_LIMIT = 0.5
SMALL_AMOUNT_THRESHOLD = 60.0
RELAXED_CATEGORY_HINTS = {
    "bills & utilities",
    "insurance",
    "security & services",
}
DIAGNOSTIC_LIMIT = 25


@dataclass(frozen=True)
class SubscriptionRecord:
    merchant: str
    canonical: str
    average_amount: float
    total_amount: float
    occurrences: int
    cadence_days: float | None
    last_charge: pd.Timestamp
    status: str
    confidence: float
    change_pct: float | None
    notes: str


@dataclass(frozen=True)
class _MetadataSignals:
    platforms: tuple[str, ...]
    services: tuple[str, ...]


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

    comparison_stats = (
        _summarise_merchants(comparison_frame) if comparison_frame is not None else {}
    )
    current_stats = _summarise_merchants(current)
    combined_stats = _build_combined_stats(current, comparison_frame)

    if not current_stats:
        raise AnalysisError("No subscription-like merchants detected in the selected window.")

    records: list[SubscriptionRecord] = []
    new_merchants: list[dict[str, Any]] = []
    price_increases: list[dict[str, Any]] = []
    skipped_counter: Counter[str] = Counter()
    skipped_samples: list[dict[str, Any]] = []

    window_end = pd.Timestamp(context.window.end)

    def record_skip(
        reasons: Sequence[str],
        *,
        stats: _MerchantStats,
        combined: _CombinedStats | None,
    ) -> None:
        if not reasons:
            return
        skipped_counter.update(reasons)
        if len(skipped_samples) < DIAGNOSTIC_LIMIT:
            skipped_samples.append(
                {
                    "merchant": stats.display_name,
                    "canonical": stats.canonical,
                    "reasons": list(reasons),
                    "occurrences": stats.occurrences,
                    "cadence_days": None if combined is None else combined.cadence_days,
                    "average_amount": round(stats.average_amount, 2),
                    "category": stats.category,
                    "subcategory": stats.subcategory,
                }
            )

    for canonical, stats in current_stats.items():
        combined = combined_stats.get(canonical)
        if combined is None:
            record_skip(("missing_combined_stats",), stats=stats, combined=None)
            continue

        baseline = comparison_stats.get(canonical)
        total_occurrences = combined.occurrences
        cadence = combined.cadence_days

        if total_occurrences < 2:
            record_skip(("occurrences_lt_2",), stats=stats, combined=combined)
            continue

        if cadence is None or cadence <= 0:
            record_skip(("cadence_missing",), stats=stats, combined=combined)
            continue

        if cadence < CADENCE_MIN_DAYS:
            record_skip(("cadence_below_min",), stats=stats, combined=combined)
            continue

        if cadence > CADENCE_MAX_DAYS:
            record_skip(("cadence_above_max",), stats=stats, combined=combined)
            continue

        if _is_incidental_charge(stats):
            context.cli_ctx.logger.debug(
                f"Skipping incidental recurring charge for merchant '{stats.display_name}'"
            )
            record_skip(("incidental_category",), stats=stats, combined=combined)
            continue

        if _looks_like_domain_service(stats):
            context.cli_ctx.logger.debug(
                f"Skipping domain/registration pattern for merchant '{stats.display_name}'"
            )
            record_skip(("domain_pattern",), stats=stats, combined=combined)
            continue

        if combined.average_amount == 0:
            record_skip(("zero_average_amount",), stats=stats, combined=combined)
            continue

        variance_limit = _variance_limit(stats)
        rel_std = combined.amount_std / combined.average_amount if combined.average_amount else 0.0
        if rel_std > variance_limit:
            record_skip(("high_amount_variance",), stats=stats, combined=combined)
            continue

        change_pct = None
        notes: list[str] = []
        if baseline:
            change_pct = percentage_change(stats.average_amount, baseline.average_amount)
            if change_pct and change_pct > price_threshold:
                notes.append(f"price +{change_pct * 100:.1f}%")
                price_increases.append(
                    {
                        "merchant": stats.display_name,
                        "change_pct": round(change_pct, 4),
                        "previous_average": round(baseline.average_amount, 2),
                        "current_average": round(stats.average_amount, 2),
                    }
                )
        else:
            notes.append("new")
            new_merchants.append(
                {
                    "merchant": stats.display_name,
                    "average_amount": round(stats.average_amount, 2),
                    "occurrences": stats.occurrences,
                }
            )

        status = _resolve_status(stats.last_charge, window_end)
        if status != "active" and not include_inactive:
            record_skip(("inactive_status",), stats=stats, combined=combined)
            continue

        confidence = _estimate_confidence(total_occurrences=total_occurrences, cadence=cadence)
        confidence = _apply_confidence_penalties(
            confidence,
            rel_std=rel_std,
            cadence_jitter=combined.cadence_jitter,
        )
        if confidence < min_confidence:
            record_skip(("below_confidence_threshold",), stats=stats, combined=combined)
            continue

        records.append(
            SubscriptionRecord(
                merchant=stats.display_name,
                canonical=canonical,
                average_amount=stats.average_amount,
                total_amount=stats.total_amount,
                occurrences=stats.occurrences,
                cadence_days=cadence,
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
        for canonical in missing:
            stats = comparison_stats[canonical]
            cancelled.append(
                {
                    "merchant": stats.display_name,
                    "last_seen": stats.last_charge.date().isoformat(),
                    "average_amount": round(stats.average_amount, 2),
                }
            )

    fallback_recommended = len(records) == 0
    if fallback_recommended:
        context.cli_ctx.logger.info(
            "subscription_detect: heuristics produced no matches; recommend LLM fallback."
        )

    table = _build_table(records)
    summary_lines = _build_summary(records, new_merchants, price_increases)
    if fallback_recommended:
        summary_lines.append("No subscriptions met heuristic filters; LLM fallback recommended.")

    diagnostics = {
        "evaluated_merchants": len(current_stats),
        "selected_merchants": len(records),
        "skipped_total": sum(skipped_counter.values()),
        "skipped_summary": [
            {"reason": reason, "count": count} for reason, count in skipped_counter.most_common()
        ],
        "skipped_samples": skipped_samples,
        "filters": {
            "cadence_min_days": CADENCE_MIN_DAYS,
            "cadence_max_days": CADENCE_MAX_DAYS,
            "variance_limit_default": VARIANCE_LIMIT_DEFAULT,
            "variance_limit_relaxed": VARIANCE_LIMIT_RELAXED,
            "small_amount_threshold": SMALL_AMOUNT_THRESHOLD,
            "min_confidence": min_confidence,
            "include_inactive": include_inactive,
        },
        "fallback_recommended": fallback_recommended,
    }

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
        "diagnostics": diagnostics,
        "fallback_recommended": fallback_recommended,
    }

    return AnalysisResult(
        title="Subscription Detection",
        summary=summary_lines,
        tables=[table],
        json_payload=json_payload,
    )


@dataclass(frozen=True)
class _MerchantStats:
    canonical: str
    display_name: str
    average_amount: float
    total_amount: float
    occurrences: int
    cadence_days: float | None
    last_charge: pd.Timestamp
    amount_std: float
    amount_min: float
    amount_max: float
    category: str | None
    subcategory: str | None
    metadata: _MetadataSignals


@dataclass(frozen=True)
class _CombinedStats:
    occurrences: int
    cadence_days: float | None
    average_amount: float
    amount_std: float
    cadence_jitter: float | None


def _summarise_merchants(frame: pd.DataFrame | None) -> dict[str, _MerchantStats]:
    if frame is None or frame.empty:
        return {}

    working = frame.copy()
    working["amount"] = working["amount"].astype(float).abs()
    working.sort_values(["merchant", "date"], inplace=True)

    stats: dict[str, _MerchantStats] = {}
    canonical_col = "merchant_canonical" if "merchant_canonical" in working.columns else "merchant"
    display_col = "merchant_display" if "merchant_display" in working.columns else "merchant"

    for canonical, group in working.groupby(canonical_col):
        occurrences = int(len(group))

        amounts = group["amount"]
        total = safe_float(amounts.sum())
        avg = safe_float(amounts.mean())
        cadence = None
        if occurrences > 1:
            diffs = group["date"].diff().dt.days.dropna()
            if not diffs.empty:
                cadence = float(diffs.median())
        last_charge = group["date"].max()
        display_series = group[display_col].dropna().astype(str)
        if not display_series.empty:
            mode_values = display_series.mode()
            display_name = mode_values.iloc[0] if not mode_values.empty else display_series.iloc[0]
        else:
            display_name = str(canonical)

        category_value = None
        category_series = group.get("category")
        if category_series is not None:
            category_series = category_series.dropna().astype(str)
            if not category_series.empty:
                category_modes = category_series.mode()
                category_value = (
                    category_modes.iloc[0] if not category_modes.empty else category_series.iloc[0]
                )

        subcategory_value = None
        subcategory_series = group.get("subcategory")
        if subcategory_series is not None:
            subcategory_series = subcategory_series.dropna().astype(str)
            if not subcategory_series.empty:
                subcategory_modes = subcategory_series.mode()
                subcategory_value = (
                    subcategory_modes.iloc[0]
                    if not subcategory_modes.empty
                    else subcategory_series.iloc[0]
                )

        metadata_signals = _collect_metadata_signals(group.get("transaction_metadata"))

        stats[str(canonical)] = _MerchantStats(
            canonical=str(canonical),
            display_name=display_name,
            average_amount=avg,
            total_amount=total,
            occurrences=occurrences,
            cadence_days=cadence,
            last_charge=last_charge,
            amount_std=float(amounts.std(ddof=0) or 0.0),
            amount_min=safe_float(amounts.min()),
            amount_max=safe_float(amounts.max()),
            category=category_value,
            subcategory=subcategory_value,
            metadata=metadata_signals,
        )
    return stats


def _build_combined_stats(
    current: pd.DataFrame, comparison: pd.DataFrame | None
) -> dict[str, _CombinedStats]:
    frames = [current]
    if comparison is not None and not comparison.empty:
        frames.append(comparison)
    combined = pd.concat(frames, ignore_index=True)
    if combined.empty:
        return {}

    canonical_col = "merchant_canonical" if "merchant_canonical" in combined.columns else "merchant"
    combined["amount"] = combined["amount"].astype(float).abs()
    combined.sort_values([canonical_col, "date"], inplace=True)

    stats: dict[str, _CombinedStats] = {}
    for canonical, group in combined.groupby(canonical_col):
        occurrences = int(len(group))
        if occurrences < 2:
            continue

        diffs = group["date"].diff().dt.days.dropna()
        cadence = float(diffs.median()) if not diffs.empty else None
        cadence_jitter = float(diffs.std(ddof=0) or 0.0) if not diffs.empty else None
        avg = safe_float(group["amount"].mean())
        amount_std = float(group["amount"].std(ddof=0) or 0.0)
        stats[str(canonical)] = _CombinedStats(
            occurrences=occurrences,
            cadence_days=cadence,
            average_amount=avg,
            amount_std=amount_std,
            cadence_jitter=cadence_jitter,
        )
    return stats


def _resolve_status(last_charge: pd.Timestamp, window_end: pd.Timestamp) -> str:
    delta = window_end - last_charge
    if delta <= timedelta(days=45):
        return "active"
    return "inactive"


def _estimate_confidence(*, total_occurrences: int, cadence: float | None) -> float:
    if cadence is None or cadence <= 0:
        return 0.0
    base = min(1.0, total_occurrences / 6)
    deviation = abs(cadence - 30)
    cadence_boost = max(0.0, 1 - min(deviation, 30) / 30)
    confidence = (base * 0.6) + (cadence_boost * 0.4)
    return round(min(1.0, confidence), 3)


def _apply_confidence_penalties(
    confidence: float,
    *,
    rel_std: float,
    cadence_jitter: float | None,
) -> float:
    variance_penalty = max(0.0, rel_std - 0.05)
    variance_penalty = min(0.4, variance_penalty)

    jitter_penalty = 0.0
    if cadence_jitter is not None and cadence_jitter > 2:
        jitter_penalty = min(0.3, cadence_jitter / 30)

    adjusted = confidence - (variance_penalty + jitter_penalty)
    return round(max(0.0, adjusted), 3)


def _variance_limit(stats: _MerchantStats) -> float:
    category = (stats.category or "").casefold()
    amount_ceiling = stats.amount_max
    if amount_ceiling <= SMALL_AMOUNT_THRESHOLD:
        return SMALL_AMOUNT_VARIANCE_LIMIT
    if category in RELAXED_CATEGORY_HINTS:
        return VARIANCE_LIMIT_RELAXED
    return VARIANCE_LIMIT_DEFAULT


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


def _collect_metadata_signals(raw_series: Any) -> _MetadataSignals:
    if raw_series is None:
        return _MetadataSignals(platforms=(), services=())

    if isinstance(raw_series, pd.Series):
        iterable = raw_series.tolist()
    elif isinstance(raw_series, Sequence):
        iterable = list(raw_series)
    else:
        iterable = [raw_series]

    platforms: set[str] = set()
    services: set[str] = set()

    for item in iterable:
        metadata: Mapping[str, Any] | None = item if isinstance(item, Mapping) else None
        if not metadata:
            continue
        merchant_meta = metadata.get("merchant_metadata") if isinstance(metadata, Mapping) else None
        if isinstance(merchant_meta, Mapping):
            platform = merchant_meta.get("platform")
            if isinstance(platform, str) and platform.strip():
                platforms.add(platform.strip())
            service = merchant_meta.get("service")
            if isinstance(service, str) and service.strip():
                services.add(service.strip())

    return _MetadataSignals(
        platforms=tuple(sorted(platforms, key=str.casefold)),
        services=tuple(sorted(services, key=str.casefold)),
    )


NON_SUBSCRIPTION_CATEGORY_RULES = {
    ("transportation", "parking"),
    ("transportation", "tolls"),
    ("transportation", "reimbursable"),
}


DOMAIN_PLATFORM_HINTS = {
    "NAMECHEAP",
    "GO DADDY",
    "GODADDY",
    "DOMAIN.COM",
    "GOOGLE DOMAINS",
    "HOVER",
    "DYNADOT",
}


DOMAIN_KEYWORDS = ("DOMAIN", "REGISTRAR", "WHOIS", "DNS")


def _is_incidental_charge(stats: _MerchantStats) -> bool:
    category = (stats.category or "").casefold()
    subcategory = (stats.subcategory or "").casefold()
    if (category, subcategory) in NON_SUBSCRIPTION_CATEGORY_RULES:
        return True

    canonical_upper = stats.canonical.upper()
    if "PARKING" in canonical_upper and stats.amount_max <= 20:
        return True

    return False


def _looks_like_domain_service(stats: _MerchantStats) -> bool:
    canonical_upper = stats.canonical.upper()
    if any(keyword in canonical_upper for keyword in DOMAIN_KEYWORDS):
        return True

    for platform in stats.metadata.platforms:
        normalized = platform.strip().upper()
        if normalized in DOMAIN_PLATFORM_HINTS:
            return True
        if any(keyword in normalized for keyword in DOMAIN_KEYWORDS):
            return True

    for service in stats.metadata.services:
        normalized = service.strip().upper()
        if any(keyword in normalized for keyword in DOMAIN_KEYWORDS):
            return True

    return False
