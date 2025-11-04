"""Category suggestion analyzer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

try:
    import pandas as pd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    pd = None  # type: ignore[assignment]

from ...shared.dataframe import load_transactions_frame
from ..metrics import jaccard_similarity, safe_float
from ..types import AnalysisContext, AnalysisError, AnalysisResult, TableSeries


@dataclass(frozen=True)
class CategoryProfile:
    merchants: set[str]
    total_spend: float
    transaction_count: int


@dataclass(frozen=True)
class Suggestion:
    source: str
    target: str
    overlap: float
    shared_merchants: int
    source_spend: float
    target_spend: float


def analyze(context: AnalysisContext) -> AnalysisResult:
    if pd is None:
        raise AnalysisError("pandas is required for fin-analyze; install the 'analysis' extra.")

    frame = load_transactions_frame(context)
    if frame.empty:
        raise AnalysisError(
            "No transactions available for the selected window. Suggestion: Try using a longer time period (e.g., 6m, 12m, 24m, 36m, or all) or ask the user if they have imported any transactions yet."
        )

    min_overlap = float(context.options.get("min_overlap", 0.8) or 0.8)
    min_transactions = 3

    profiles = _build_profiles(frame)
    if len(profiles) < 2:
        raise AnalysisError(
            "Not enough categories to evaluate suggestions. Suggestion: Try using a longer time period (e.g., 6m, 12m, 24m, 36m, or all) or inform the user of the error."
        )

    suggestions: list[Suggestion] = []
    keys = list(profiles.keys())
    for a, b in combinations(keys, 2):
        profile_a = profiles[a]
        profile_b = profiles[b]
        if (
            profile_a.transaction_count < min_transactions
            or profile_b.transaction_count < min_transactions
        ):
            continue
        overlap = jaccard_similarity(profile_a.merchants, profile_b.merchants)
        if overlap >= min_overlap:
            shared = len(profile_a.merchants & profile_b.merchants)
            if profile_a.total_spend <= profile_b.total_spend:
                source, target = a, b
                source_profile, target_profile = profile_a, profile_b
            else:
                source, target = b, a
                source_profile, target_profile = profile_b, profile_a
            suggestions.append(
                Suggestion(
                    source=source,
                    target=target,
                    overlap=overlap,
                    shared_merchants=shared,
                    source_spend=source_profile.total_spend,
                    target_spend=target_profile.total_spend,
                )
            )

    suggestions.sort(key=lambda s: s.overlap, reverse=True)

    if not suggestions:
        raise AnalysisError("No category suggestions met the overlap threshold.")

    table = _build_table(suggestions)
    summary_lines = _build_summary(suggestions)

    json_payload = {
        "window": {
            "label": context.window.label,
            "start": context.window.start.isoformat(),
            "end": context.window.end.isoformat(),
        },
        "min_overlap": min_overlap,
        "suggestions": [
            {
                "from": suggestion.source,
                "to": suggestion.target,
                "overlap_pct": round(suggestion.overlap * 100, 2),
                "shared_merchants": suggestion.shared_merchants,
                "from_spend": round(suggestion.source_spend, 2),
                "to_spend": round(suggestion.target_spend, 2),
            }
            for suggestion in suggestions
        ],
    }

    return AnalysisResult(
        title="Category Suggestions",
        summary=summary_lines,
        tables=[table],
        json_payload=json_payload,
    )


def _build_profiles(frame: pd.DataFrame) -> dict[str, CategoryProfile]:
    working = frame.copy()
    working["category"] = working["category"].fillna("Uncategorized")
    working["subcategory"] = working["subcategory"].fillna("Uncategorized")
    working["category_key"] = working["category"] + " > " + working["subcategory"]
    grouped = working.groupby("category_key")

    profiles: dict[str, CategoryProfile] = {}
    for key, group in grouped:
        merchants = set(group["merchant"].dropna().astype(str))
        profiles[key] = CategoryProfile(
            merchants=merchants,
            total_spend=safe_float(group["spend_amount"].sum()),
            transaction_count=int(len(group)),
        )
    return profiles


def _build_table(suggestions: Sequence[Suggestion]) -> TableSeries:
    rows = []
    for suggestion in suggestions:
        rows.append(
            [
                suggestion.source,
                suggestion.target,
                round(suggestion.overlap * 100, 2),
                suggestion.shared_merchants,
                round(suggestion.source_spend, 2),
                round(suggestion.target_spend, 2),
            ]
        )
    return TableSeries(
        name="category_suggestions",
        columns=[
            "From",
            "To",
            "Overlap %",
            "Shared Merchants",
            "From Spend",
            "To Spend",
        ],
        rows=rows,
        metadata={"unit": "USD"},
    )


def _build_summary(suggestions: Sequence[Suggestion]) -> list[str]:
    return [f"Suggested merges: {len(suggestions)} based on merchant overlap."]
