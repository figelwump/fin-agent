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
    merchant_types = []  # Track the type of each merchant for better display logic

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
                platform_upper = platform.upper()

                # For hotels, use the hotel name as canonical if available
                if platform_upper == "HOTEL" and merchant_meta.get("hotel_name"):
                    hotel_name = merchant_meta["hotel_name"]
                    canonical_keys.append(hotel_name.upper())
                    merchant_type = "hotel"
                    # Use the pattern display but strip location for aggregation
                    if pattern_display and "•" in pattern_display:
                        display_names.append(pattern_display.split("•")[0].strip())
                    else:
                        display_names.append(hotel_name)
                # For generic or non-meaningful platforms, use pattern key
                elif platform_upper in ["N/A", "AIRPORT DINING", "TST", "SQ", "SQUARE"]:
                    # These are too generic or just payment processors, use the pattern key instead
                    if pattern_display:
                        # Extract a sensible canonical from the display name
                        canonical = pattern_display.split("•")[0].strip().upper() if "•" in pattern_display else pattern_display.upper()
                        canonical_keys.append(canonical)
                        display_names.append(pattern_display)
                    elif metadata.get("merchant_pattern_key"):
                        canonical_keys.append(metadata["merchant_pattern_key"])
                        display_names.append(merchant)
                    else:
                        canonical = merchant_pattern_key(merchant) or normalize_merchant(merchant)
                        canonical_keys.append(canonical)
                        display_names.append(merchant)
                    merchant_type = "merchant"
                else:
                    # Group all platform transactions together (e.g., all Lyft, all DoorDash)
                    canonical_keys.append(platform.upper())

                    # Detect merchant type from platform name or metadata
                    if any(word in platform_upper for word in ["AIRLINE", "AIRWAYS", "JET", "FLIGHT"]):
                        merchant_type = "airline"
                        display_names.append(platform)  # Just the airline name, no location
                    elif any(word in platform_upper for word in ["HOTEL", "INN", "RESORT", "SUITES"]):
                        merchant_type = "hotel"
                        display_names.append(platform)  # Just the hotel brand
                    elif any(word in platform_upper for word in ["RENTAL", "HERTZ", "AVIS", "ENTERPRISE"]):
                        merchant_type = "rental"
                        display_names.append(platform)  # Just the rental company
                    elif merchant_meta.get("restaurant_name"):
                        merchant_type = "food_delivery"
                        display_names.append(pattern_display or platform)  # Keep restaurant info
                    else:
                        merchant_type = "platform"
                        display_names.append(pattern_display or platform)
                merchant_types.append(merchant_type)
            elif metadata.get("merchant_pattern_key"):
                # Use the LLM-provided canonical key
                pattern_key = metadata.get("merchant_pattern_key")
                # Check if this looks like a platform abbreviation that should be expanded
                if pattern_key == "IC CA" and "INSTACART" in merchant.upper():
                    canonical_keys.append("INSTACART")
                    display_names.append("Instacart")
                    merchant_types.append("platform")
                else:
                    canonical_keys.append(pattern_key)
                    display_names.append(pattern_display or merchant)
                    merchant_types.append("merchant")
            else:
                # Fallback to rule-based normalization
                canonical = merchant_pattern_key(merchant)
                if not canonical:
                    canonical = normalize_merchant(merchant)
                canonical_keys.append(canonical)
                display_names.append(merchant)
                merchant_types.append("merchant")
        else:
            # No metadata, use rule-based normalization
            canonical = merchant_pattern_key(merchant)
            if not canonical:
                canonical = normalize_merchant(merchant)
            canonical_keys.append(canonical)
            display_names.append(merchant)
            merchant_types.append("merchant")

    working["canonical"] = canonical_keys
    working["display_name_hint"] = display_names
    working["merchant_type"] = merchant_types

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
        merchant_types = group["merchant_type"].unique()

        # Determine the dominant merchant type for this group
        # (should usually be consistent, but take the first if mixed)
        merchant_type = merchant_types[0] if len(merchant_types) > 0 else "merchant"

        if merchant_type in ["airline", "hotel", "rental"]:
            # For travel-related merchants, strip location details
            clean_hints = []
            for hint in display_hints:
                if "•" in hint:
                    # Take only the part before the bullet (e.g., "United Airlines" from "United Airlines • Houston")
                    clean_hints.append(hint.split("•")[0].strip())
                else:
                    clean_hints.append(hint)
            display_name = clean_hints[0] if clean_hints else canonical.title().replace("_", " ")
        elif merchant_type == "food_delivery":
            # For food delivery aggregation, just show the platform name
            # (individual restaurant details would be misleading when aggregated)
            platform_names = []
            for hint in display_hints:
                if "•" in hint:
                    # Extract platform name from "DoorDash • Restaurant"
                    platform_names.append(hint.split("•")[0].strip())
                else:
                    platform_names.append(hint)
            # Get the most common platform name or use canonical
            display_name = platform_names[0] if platform_names else canonical.title()
        elif merchant_type == "platform":
            # For other platforms (ride-sharing, etc.), use simple platform name
            clean_names = [h for h in display_hints if "•" not in h]
            display_name = clean_names[0] if clean_names else display_hints[0] if display_hints else canonical.title()
        else:
            # For regular merchants
            if display_hints:
                # Prefer enriched display names
                enriched_names = [h for h in display_hints if h not in variants]
                display_name = enriched_names[0] if enriched_names else display_hints[0]
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

