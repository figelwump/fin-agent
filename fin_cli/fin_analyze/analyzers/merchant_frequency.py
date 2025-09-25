"""Merchant frequency analyzer with canonicalized merchant names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    pd = None  # type: ignore[assignment]

from fin_cli.shared.merchants import friendly_display_name, merchant_pattern_key, normalize_merchant
from typing import Mapping

from ..metrics import percentage_change, safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries
from ...shared.dataframe import build_window_frames


@dataclass(frozen=True)
class MerchantRecord:
    canonical: str
    display_name: str
    visits: int
    total_spend: float
    average_spend: float
    previous_visits: int
    previous_spend: float
    change_pct: float | None
    notes: str


@dataclass(frozen=True)
class _MerchantStats:
    canonical: str
    display_name: str
    variants: set[str]
    visits: int
    total_spend: float
    average_spend: float


def analyze(context: AnalysisContext) -> AnalysisResult:
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    frames = build_window_frames(context)
    frame = frames.frame
    if frame.empty:
        raise AnalysisError("No transactions available for the selected window.")

    min_visits = max(int(context.options.get("min_visits", 1) or 1), 1)

    current_stats = _aggregate_merchants(frame)
    if not current_stats:
        raise AnalysisError("No merchants matched the provided filters.")

    comparison_stats = (
        _aggregate_merchants(frames.comparison_frame)
        if frames.comparison_frame is not None and not frames.comparison_empty()
        else {}
    )

    threshold = context.threshold if context.threshold is not None else 0.10

    records: list[MerchantRecord] = []
    new_merchants: list[str] = []
    dropped_merchants: list[str] = []

    for canonical, stats in current_stats.items():
        if stats.visits < min_visits:
            continue
        previous = comparison_stats.get(canonical)
        change = percentage_change(stats.total_spend, previous.total_spend if previous else None)
        notes: list[str] = []
        if previous is None:
            notes.append("new")
            new_merchants.append(stats.display_name)
        elif change is not None and change > threshold:
            notes.append(f"spend +{change * 100:.1f}%")
        record = MerchantRecord(
            canonical=canonical,
            display_name=stats.display_name,
            visits=stats.visits,
            total_spend=stats.total_spend,
            average_spend=stats.average_spend,
            previous_visits=previous.visits if previous else 0,
            previous_spend=previous.total_spend if previous else 0.0,
            change_pct=change,
            notes=", ".join(notes),
        )
        records.append(record)

    if comparison_stats:
        for canonical, stats in comparison_stats.items():
            if canonical not in current_stats:
                dropped_merchants.append(stats.display_name)

    if not records and not dropped_merchants:
        raise AnalysisError("No merchants met the minimum visit criteria.")

    records.sort(key=lambda r: (r.visits, r.total_spend), reverse=True)
    dropped_merchants.sort()

    table = _build_table(records)
    summary_lines = _build_summary(records, new_merchants, dropped_merchants)

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "min_visits": min_visits,
        "merchants": [
            {
                "canonical": record.canonical,
                "merchant": record.display_name,
                "visits": record.visits,
                "total_spend": round(record.total_spend, 2),
                "average_spend": round(record.average_spend, 2),
                "previous_visits": record.previous_visits,
                "previous_spend": round(record.previous_spend, 2),
                "change_pct": None if record.change_pct is None else round(record.change_pct, 4),
                "notes": record.notes,
            }
            for record in records
        ],
        "new_merchants": sorted(set(new_merchants)),
        "dropped_merchants": dropped_merchants,
    }

    return AnalysisResult(
        title="Merchant Frequency",
        summary=summary_lines,
        tables=[table],
        json_payload=json_payload,
    )


def _aggregate_merchants(frame: pd.DataFrame | None) -> dict[str, _MerchantStats]:
    if frame is None or frame.empty:
        return {}

    working = frame.copy()
    working["merchant"] = working["merchant"].fillna("").astype(str)

    # Extract canonical key and display name from metadata when available
    canonical_keys = []
    display_names = []

    for idx, row in working.iterrows():
        merchant = row["merchant"]
        metadata = row.get("transaction_metadata")

        # Option 1: Use LLM-enriched metadata when available
        if isinstance(metadata, Mapping):
            # Check for platform metadata first - these should be grouped together
            merchant_meta = metadata.get("merchant_metadata", {})
            platform = merchant_meta.get("platform") if isinstance(merchant_meta, dict) else None
            pattern_display = metadata.get("merchant_pattern_display")

            if platform:
                # Group all platform transactions together (e.g., all Lyft, all DoorDash)
                canonical_keys.append(platform.upper())
                # For certain types of merchants, just use the platform name without location details
                if any(keyword in platform.upper() for keyword in ["AIRLINE", "HOTEL", "RENTAL"]):
                    display_names.append(platform)
                else:
                    display_names.append(pattern_display or platform)
            elif metadata.get("merchant_pattern_key"):
                # Use the LLM-provided canonical key
                pattern_key = metadata.get("merchant_pattern_key")
                # Check if this looks like a platform abbreviation that should be expanded
                if pattern_key == "IC CA" and "INSTACART" in merchant.upper():
                    canonical_keys.append("INSTACART")
                    display_names.append("Instacart")
                else:
                    canonical_keys.append(pattern_key)
                    display_names.append(pattern_display or merchant)
            else:
                # Fallback to rule-based normalization
                canonical = merchant_pattern_key(merchant)
                if not canonical:
                    canonical = normalize_merchant(merchant)
                canonical_keys.append(canonical)
                display_names.append(merchant)
        else:
            # No metadata, use rule-based normalization
            canonical = merchant_pattern_key(merchant)
            if not canonical:
                canonical = normalize_merchant(merchant)
            canonical_keys.append(canonical)
            display_names.append(merchant)

    working["canonical"] = canonical_keys
    working["display_name_hint"] = display_names

    # Group by canonical key
    groups = working.groupby("canonical")
    stats: dict[str, _MerchantStats] = {}

    for canonical, group in groups:
        visits = int(len(group))
        spend_total = safe_float(group["spend_amount"].sum())
        average = spend_total / visits if visits else 0.0
        variants = set(group["merchant"].unique())

        # Prefer display names from metadata
        display_hints = list(group["display_name_hint"].unique())

        # For platforms and airlines, use simple names without location details
        known_platforms = ["LYFT", "DOORDASH", "INSTACART", "UBER", "GRUBHUB"]
        known_airlines = ["UNITED AIRLINES", "AMERICAN AIRLINES", "DELTA", "SOUTHWEST", "ALASKA AIRLINES", "JETBLUE", "SPIRIT"]

        if canonical in known_platforms:
            display_name = canonical.title()
        elif canonical in known_airlines or "AIRLINES" in canonical:
            # For airlines, strip location information from display hints
            clean_hints = []
            for hint in display_hints:
                if "•" in hint:
                    # Take only the part before the bullet (e.g., "United Airlines" from "United Airlines • Houston")
                    clean_hints.append(hint.split("•")[0].strip())
                else:
                    clean_hints.append(hint)
            display_name = clean_hints[0] if clean_hints else canonical.title()
        elif display_hints:
            # Filter out raw merchant names to prefer enriched display names
            enriched_names = [h for h in display_hints if h not in variants and "•" in h]
            if enriched_names:
                # For platform transactions with restaurant names, show them
                display_name = enriched_names[0]
            elif any("•" not in h and h not in variants for h in display_hints):
                # Use clean display names without bullet points
                clean_names = [h for h in display_hints if "•" not in h and h not in variants]
                display_name = clean_names[0] if clean_names else display_hints[0]
            else:
                display_name = display_hints[0]
        else:
            # Fallback to friendly display name logic
            display_name = friendly_display_name(canonical, variants)

        stats[canonical] = _MerchantStats(
            canonical=canonical,
            display_name=display_name,
            variants=variants,
            visits=visits,
            total_spend=spend_total,
            average_spend=average,
        )

    return stats



def _build_table(records: Sequence[MerchantRecord]) -> TableSeries:
    rows: list[list[Any]] = []
    for record in records:
        rows.append(
            [
                record.display_name,
                record.visits,
                round(record.total_spend, 2),
                round(record.average_spend, 2),
                record.previous_visits,
                round(record.previous_spend, 2),
                None if record.change_pct is None else round(record.change_pct * 100, 2),
                record.notes,
            ]
        )
    return TableSeries(
        name="merchant_frequency",
        columns=[
            "Merchant",
            "Visits",
            "Spend",
            "Avg / Visit",
            "Prev Visits",
            "Prev Spend",
            "Change %",
            "Notes",
        ],
        rows=rows,
        metadata={"unit": "USD"},
    )


def _build_summary(
    records: Sequence[MerchantRecord],
    new_merchants: Sequence[str],
    dropped_merchants: Sequence[str],
) -> list[str]:
    lines = [f"Top merchants listed: {len(records)} (min visits applied)."]
    if new_merchants:
        lines.append(f"Newly active merchants: {len(new_merchants)}.")
    if dropped_merchants:
        lines.append(f"Merchants missing this window: {len(dropped_merchants)}.")
    return lines

