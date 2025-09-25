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
    working["canonical_raw"] = working["merchant"].apply(merchant_pattern_key)
    mask = working["canonical_raw"].eq("")
    if mask.any():
        working.loc[mask, "canonical_raw"] = working.loc[mask, "merchant"].apply(normalize_merchant)
    working["canonical"] = working["canonical_raw"].apply(_bucket_key)

    groups = working.groupby("canonical")
    stats: dict[str, _MerchantStats] = {}
    for canonical, group in groups:
        visits = int(len(group))
        spend_total = safe_float(group["spend_amount"].sum())
        average = spend_total / visits if visits else 0.0
        variants = set(group["merchant"].unique())
        metadata_displays: list[str] = []
        if "transaction_metadata" in group:
            for value in group["transaction_metadata"]:
                if isinstance(value, Mapping):
                    display = value.get("merchant_display") or value.get("merchant")
                    if display:
                        metadata_displays.append(str(display))
        display_name = friendly_display_name(canonical, metadata_displays or variants)
        stats[canonical] = _MerchantStats(
            canonical=canonical,
            display_name=display_name,
            variants=variants,
            visits=visits,
            total_spend=spend_total,
            average_spend=average,
        )
    return stats

def _bucket_key(canonical: str) -> str:
    tokens = canonical.split()
    generic = {"THE", "STORE", "MARKET", "SHOP", "LLC", "INC", "CO", "COMPANY"}
    for token in tokens:
        if len(token) > 2 and token not in generic and not token.isdigit():
            if token.startswith("AMZN") or token.startswith("AMAZON"):
                return "AMAZON"
            return token
    return canonical or "UNKNOWN"





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

