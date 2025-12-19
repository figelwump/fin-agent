"""Analyzer registry and option parsing helpers for `fin-analyze`."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence

from .analyzers import (
    cash_mix,
    category_breakdown,
    category_timeline,
    merchant_frequency,
    portfolio_trend,
    rebalance_suggestions,
    spending_patterns,
    spending_trends,
    subscription_detect,
    unusual_spending,
)
from .types import (
    AnalysisConfigurationError,
    AnalysisContext,
    AnalysisNotImplementedError,
    AnalysisResult,
    AnalyzerCallable,
    AnalyzerHelpRequested,
    AnalyzerOption,
    AnalyzerSpec,
)

# Placeholder implementations will be replaced in later phases. Each currently raises
# `AnalysisNotImplementedError` so the CLI can ship before analyzers are complete.


def _placeholder_analyzer(name: str) -> AnalyzerCallable:
    def _inner(_: AnalysisContext) -> AnalysisResult:  # pragma: no cover - until analyzers land
        raise AnalysisNotImplementedError(f"Analyzer '{name}' is not yet implemented.")

    return _inner


_ANALYZER_SPECS: Sequence[AnalyzerSpec] = (
    AnalyzerSpec(
        slug="spending-trends",
        title="Spending Trends",
        summary="Show spending totals over time with optional category breakdowns.",
        factory=spending_trends.analyze,
        options=(
            AnalyzerOption(
                name="show_categories",
                flags=("--show-categories",),
                help="Include per-category breakdown in addition to overall trend.",
                is_flag=True,
            ),
        ),
    ),
    AnalyzerSpec(
        slug="category-breakdown",
        title="Category Breakdown",
        summary="Summarise spend by category/subcategory with optional comparison.",
        factory=category_breakdown.analyze,
        options=(
            AnalyzerOption(
                name="min_amount",
                flags=("--min-amount",),
                help="Minimum total amount to include a category.",
                type=float,
            ),
        ),
    ),
    AnalyzerSpec(
        slug="subscription-detect",
        title="Subscription Detection",
        summary="Identify recurring merchants and subscription changes.",
        factory=subscription_detect.analyze,
        options=(
            AnalyzerOption(
                name="include_inactive",
                flags=("--all",),
                help="Include inactive subscriptions in the output.",
                is_flag=True,
            ),
            AnalyzerOption(
                name="min_confidence",
                flags=("--min-confidence",),
                help="Minimum detection confidence (0-1).",
                type=float,
            ),
        ),
    ),
    AnalyzerSpec(
        slug="unusual-spending",
        title="Unusual Spending",
        summary="Detect anomalies and outliers for the selected window.",
        factory=unusual_spending.analyze,
        options=(
            AnalyzerOption(
                name="sensitivity",
                flags=("--sensitivity",),
                help="Detection sensitivity from 1 (low) to 5 (high).",
                type=int,
            ),
        ),
    ),
    AnalyzerSpec(
        slug="merchant-frequency",
        title="Merchant Frequency",
        summary="Rank merchants by visit count or spend volume.",
        factory=merchant_frequency.analyze,
        options=(
            AnalyzerOption(
                name="min_visits",
                flags=("--min-visits",),
                help="Minimum number of visits to include a merchant.",
                type=int,
            ),
            AnalyzerOption(
                name="category",
                flags=("--category",),
                help="Filter merchants to a specific category.",
                type=str,
            ),
            AnalyzerOption(
                name="subcategory",
                flags=("--subcategory",),
                help="Filter merchants to a specific subcategory.",
                type=str,
            ),
        ),
    ),
    AnalyzerSpec(
        slug="category-timeline",
        title="Category Timeline",
        summary="Aggregate spend for a category across months/quarters/years.",
        factory=category_timeline.analyze,
        options=(
            AnalyzerOption(
                name="interval",
                flags=("--interval",),
                help="Grouping interval: month, quarter, or year.",
                type=str,
                default="month",
            ),
            AnalyzerOption(
                name="category",
                flags=("--category",),
                help="Category to filter by (optional).",
                type=str,
            ),
            AnalyzerOption(
                name="subcategory",
                flags=("--subcategory",),
                help="Subcategory to filter by (optional).",
                type=str,
            ),
            AnalyzerOption(
                name="top_n",
                flags=("--top-n",),
                help="Limit output to the latest N intervals.",
                type=int,
            ),
            AnalyzerOption(
                name="include_merchants",
                flags=("--include-merchants",),
                help="Include merchant lists contributing to the totals.",
                is_flag=True,
            ),
        ),
    ),
    AnalyzerSpec(
        slug="spending-patterns",
        title="Spending Patterns",
        summary="Analyse spending by day of week, week index, or specific date.",
        factory=spending_patterns.analyze,
        options=(
            AnalyzerOption(
                name="group_by",
                flags=("--by",),
                help="Grouping strategy: day, week, or date.",
                type=str,
                choices=("day", "week", "date"),
            ),
        ),
    ),
    AnalyzerSpec(
        slug="portfolio-trend",
        title="Portfolio Trend",
        summary="Time-series of portfolio market value across the window.",
        factory=portfolio_trend.analyze,
        aliases=("asset-trend", "trend"),
        options=(
            AnalyzerOption(
                name="account_id",
                flags=("--account-id",),
                help="Optional account filter.",
                type=int,
            ),
        ),
    ),
    AnalyzerSpec(
        slug="cash-mix",
        title="Cash Mix",
        summary="Cash vs non-cash split with spending runway context.",
        factory=cash_mix.analyze,
        options=(
            AnalyzerOption(
                name="as_of_date",
                flags=("--as-of-date",),
                help="Use a specific as-of date (YYYY-MM-DD).",
                type=str,
            ),
        ),
    ),
    AnalyzerSpec(
        slug="rebalance-suggestions",
        title="Rebalance Suggestions",
        summary="Compare allocations to targets and suggest shifts.",
        factory=rebalance_suggestions.analyze,
        options=(
            AnalyzerOption(
                name="target",
                flags=("--target",),
                help="Override targets inline (main/sub:pct). Can be passed multiple times.",
                multiple=True,
            ),
            AnalyzerOption(
                name="as_of_date",
                flags=("--as-of-date",),
                help="Use a specific as-of date (YYYY-MM-DD).",
                type=str,
            ),
            AnalyzerOption(
                name="account_id",
                flags=("--account-id",),
                help="Optional account scope for targets.",
                type=int,
            ),
        ),
    ),
)


_SPEC_BY_SLUG: Mapping[str, AnalyzerSpec] = {spec.slug: spec for spec in _ANALYZER_SPECS}
for spec in _ANALYZER_SPECS:
    for alias in spec.aliases:
        _SPEC_BY_SLUG[alias] = spec


# ----- Public helpers -----------------------------------------------------------------------


def available_specs() -> Sequence[AnalyzerSpec]:
    """Return available analyzer specs."""

    return _ANALYZER_SPECS


def get_spec(name: str) -> AnalyzerSpec:
    """Lookup an analyzer spec by slug or alias."""

    normalized = name.lower().strip()
    try:
        return _SPEC_BY_SLUG[normalized]
    except KeyError as exc:
        raise AnalysisConfigurationError(f"Unknown analysis type '{name}'.") from exc


def format_catalog() -> str:
    """Return a formatted listing of available analyzers for --help-list."""

    lines = ["Available analyses:"]
    for spec in available_specs():
        lines.append(f"  - {spec.slug}: {spec.summary}")
    return "\n".join(lines)


def parse_analyzer_args(spec: AnalyzerSpec, args: Sequence[str]) -> Mapping[str, object]:
    """Parse analyzer-specific CLI args using a lightweight argparse parser."""

    if any(token in {"--help", "-h"} for token in args):
        raise AnalyzerHelpRequested(build_help_text(spec))

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    for option in spec.options:
        _add_option(parser, option)

    try:
        namespace, leftover = parser.parse_known_intermixed_args(list(args))
    except AttributeError:
        namespace, leftover = parser.parse_known_args(list(args))
    if leftover:
        raise AnalysisConfigurationError(
            f"Unexpected arguments for analyzer '{spec.slug}': {' '.join(leftover)}"
        )
    values = vars(namespace)
    return {key: value for key, value in values.items() if value is not None}


def build_help_text(spec: AnalyzerSpec) -> str:
    """Render analyzer-specific help text."""

    lines = [f"Analysis: {spec.title} ({spec.slug})", "", spec.summary, ""]
    if not spec.options:
        lines.append("This analysis does not accept additional options.")
        return "\n".join(lines)

    lines.append("Options:")
    for option in spec.options:
        flag_display = ", ".join(option.flags)
        metavar = f" {option.metavar}" if option.metavar else ""
        if option.is_flag:
            metavar = ""
        detail = option.help
        if option.choices:
            choice_text = ", ".join(str(choice) for choice in option.choices)
            detail = f"{detail} (choices: {choice_text})"
        default = option.default
        default_text = f" [default: {default}]" if default not in {None, False} else ""
        lines.append(f"  {flag_display}{metavar}\n      {detail}{default_text}")
    return "\n".join(lines)


# ----- Internal helpers ---------------------------------------------------------------------


def _add_option(parser: argparse.ArgumentParser, option: AnalyzerOption) -> None:
    kwargs: dict[str, object] = {
        "help": option.help,
        "dest": option.name,
    }
    if option.is_flag:
        kwargs["action"] = "store_true"
    else:
        kwargs["type"] = option.type or str
        if option.metavar:
            kwargs["metavar"] = option.metavar
        if option.multiple:
            kwargs["action"] = "append"
        if option.choices is not None:
            kwargs["choices"] = list(option.choices)
        if option.default is not None:
            kwargs["default"] = option.default
    parser.add_argument(*option.flags, **kwargs)
