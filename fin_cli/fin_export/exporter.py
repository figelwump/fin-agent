"""Report assembly and rendering helpers for ``fin-export``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from jinja2 import Environment, FileSystemLoader

from fin_cli.fin_analyze import registry, temporal
from fin_cli.fin_analyze.metrics import percentage_change, safe_float
from fin_cli.fin_analyze.types import (
    AnalysisContext,
    AnalysisError,
    AnalysisResult,
    TableSeries,
    TimeWindow,
)
from fin_cli.shared.cli import CLIContext
from fin_cli.shared.dataframe import load_transactions_frame
from fin_cli.shared.exceptions import FinAgentError


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_TEMPLATE_NAME = "standard.md.j2"


class ExportError(FinAgentError):
    """Raised when export orchestration fails."""


@dataclass(frozen=True)
class SectionSpec:
    """Declarative export section configuration."""

    slug: str
    title: str
    analyzer_slug: str | None
    analyzer_options: Mapping[str, Any] = field(default_factory=dict)
    post_process: str | None = None


@dataclass(frozen=True)
class SectionOutput:
    """Rendered data for an export section."""

    slug: str
    title: str
    summary: list[str]
    tables_markdown: list[str]
    tables_structured: list[dict[str, Any]]
    extra_markdown: list[str]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class ExportMetadata:
    """Metadata describing the generated report."""

    generated_at: str
    report_title: str
    window: Mapping[str, Any]
    comparison_window: Mapping[str, Any] | None
    sections: list[str]


DEFAULT_SECTION_ORDER: list[SectionSpec] = [
    SectionSpec(slug="summary", title="Summary", analyzer_slug=None),
    SectionSpec(
        slug="categories",
        title="Spending by Category",
        analyzer_slug="category-breakdown",
        analyzer_options={},
    ),
    SectionSpec(
        slug="subscriptions",
        title="Active Subscriptions",
        analyzer_slug="subscription-detect",
        analyzer_options={"include_inactive": True},
        post_process="subscriptions",
    ),
    SectionSpec(
        slug="patterns",
        title="Spending Patterns",
        analyzer_slug="spending-patterns",
        analyzer_options={"group_by": "day"},
    ),
    SectionSpec(
        slug="unusual",
        title="Unusual Spending",
        analyzer_slug="unusual-spending",
        analyzer_options={"sensitivity": 3},
        post_process="unusual",
    ),
    SectionSpec(
        slug="merchants",
        title="Top Merchants",
        analyzer_slug="merchant-frequency",
        analyzer_options={"min_visits": 1},
    ),
    SectionSpec(
        slug="trends",
        title="Spending Trends",
        analyzer_slug="spending-trends",
        analyzer_options={"show_categories": False},
    ),
    SectionSpec(
        slug="evolution",
        title="Category Evolution",
        analyzer_slug="category-evolution",
        analyzer_options={},
    ),
]

SECTION_INDEX: dict[str, SectionSpec] = {spec.slug: spec for spec in DEFAULT_SECTION_ORDER}


INDICATORS: dict[str, tuple[str, str]] = {
    "warning": ("⚠️", "[!]"),
    "positive": ("✅", "[OK]"),
    "negative": ("❌", "[x]"),
    "increase": ("↑", "[UP]"),
    "decrease": ("↓", "[DOWN]"),
    "flat": ("→", "[=]"),
}


def resolve_section_specs(section_slugs: Sequence[str] | None) -> list[SectionSpec]:
    """Return SectionSpec instances for the requested section order."""

    if not section_slugs:
        return list(DEFAULT_SECTION_ORDER)

    normalized = [slug.strip().lower() for slug in section_slugs if slug.strip()]
    if not normalized or "all" in normalized:
        return list(DEFAULT_SECTION_ORDER)

    specs: list[SectionSpec] = []
    seen: set[str] = set()
    for slug in normalized:
        if slug in seen:
            continue
        seen.add(slug)
        try:
            specs.append(SECTION_INDEX[slug])
        except KeyError as exc:  # pragma: no cover - validated in CLI tests
            raise ExportError(f"Unknown section '{slug}'.") from exc

    return specs


def infer_format(output_path: Path | None, explicit_format: str | None) -> str:
    """Infer the export format based on CLI input and output extension."""

    if explicit_format:
        return explicit_format
    if output_path is None:
        return "markdown"
    suffix = output_path.suffix.lower()
    if suffix == ".json":
        return "json"
    return "markdown"


def build_report(
    cli_ctx: CLIContext,
    *,
    sections: Sequence[SectionSpec],
    month: str | None,
    period: str | None,
    compare: bool,
    threshold: float | None,
) -> tuple[ExportMetadata, list[SectionOutput]]:
    """Assemble section outputs for the configured window."""

    window_resolution = temporal.resolve_windows(
        month=month,
        period=period,
        year=None,
        last_twelve_months=False,
        compare=compare,
        app_config=cli_ctx.config,
    )

    builder = _ReportBuilder(
        cli_ctx=cli_ctx,
        window=window_resolution.window,
        comparison=window_resolution.comparison,
        compare=compare,
        threshold=threshold,
    )
    section_outputs = builder.build_sections(sections)

    metadata = ExportMetadata(
        generated_at=_utc_now_iso(),
        report_title=_report_title(window_resolution.window),
        window=_window_payload(window_resolution.window),
        comparison_window=_window_payload(window_resolution.comparison)
        if window_resolution.comparison
        else None,
        sections=[section.slug for section in section_outputs],
    )
    return metadata, section_outputs


def render_markdown(
    metadata: ExportMetadata,
    section_outputs: Sequence[SectionOutput],
    *,
    template_path: Path | None = None,
) -> str:
    """Render the collected sections through the Markdown template."""

    search_paths = [str(TEMPLATE_DIR)]
    if template_path:
        search_paths.insert(0, str(template_path.parent))

    env = Environment(
        loader=FileSystemLoader(search_paths),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    if template_path:
        template = env.from_string(template_path.read_text())
    else:
        template = env.get_template(DEFAULT_TEMPLATE_NAME)

    context_sections = [
        {
            "slug": section.slug,
            "title": section.title,
            "summary": section.summary,
            "tables": section.tables_markdown,
            "extra_markdown": section.extra_markdown,
        }
        for section in section_outputs
    ]
    output = template.render(metadata=_metadata_dict(metadata), sections=context_sections)
    if not output.endswith("\n"):
        output += "\n"
    return output


def render_json(
    metadata: ExportMetadata,
    section_outputs: Sequence[SectionOutput],
) -> str:
    """Render structured JSON for downstream tooling."""

    payload = {
        "version": "1.0",
        "generated_at": metadata.generated_at,
        "report_title": metadata.report_title,
        "window": metadata.window,
        "comparison_window": metadata.comparison_window,
        "sections": {
            section.slug: {
                "title": section.title,
                "summary": section.summary,
                "tables": section.tables_structured,
                "payload": section.payload,
                "extra_markdown": section.extra_markdown,
            }
            for section in section_outputs
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


class _ReportBuilder:
    """Internal helper constructing sections for the export."""

    def __init__(
        self,
        *,
        cli_ctx: CLIContext,
        window: TimeWindow,
        comparison: TimeWindow | None,
        compare: bool,
        threshold: float | None,
    ) -> None:
        self.cli_ctx = cli_ctx
        self.window = window
        self.comparison = comparison
        self.compare = compare and comparison is not None
        self.threshold = threshold

    def build_sections(self, specs: Sequence[SectionSpec]) -> list[SectionOutput]:
        sections: list[SectionOutput] = []
        for spec in specs:
            if spec.slug == "summary":
                sections.append(self._summary_section())
                continue
            sections.append(self._analyzer_section(spec))
        return sections

    # ----- Section builders -----------------------------------------------------------------

    def _summary_section(self) -> SectionOutput:
        context = AnalysisContext(
            cli_ctx=self.cli_ctx,
            app_config=self.cli_ctx.config,
            window=self.window,
            comparison_window=self.comparison if self.compare else None,
            output_format="json",
            compare=self.compare,
            threshold=self.threshold,
            options={},
        )

        try:
            frame = load_transactions_frame(context, window=self.window)
        except ImportError as exc:  # pragma: no cover - handled in CLI tests
            raise ExportError(str(exc)) from exc

        if frame.empty:
            raise ExportError("No transactions found for the selected window.")

        total_spend = safe_float(frame["spend_amount"].sum())
        total_income = safe_float(frame["income_amount"].sum())
        transaction_count = int(len(frame))
        window_days = max(1, self.window.days)
        daily_average = total_spend / window_days

        comparison_payload: Mapping[str, Any] | None = None
        change_indicator: dict[str, Any] | None = None
        if self.compare and self.comparison is not None:
            comparison_frame = load_transactions_frame(context, window=self.comparison)
            comparison_spend = safe_float(comparison_frame["spend_amount"].sum())
            change_pct = percentage_change(total_spend, comparison_spend)
            change_indicator = _change_indicator(change_pct)
            comparison_payload = {
                "label": _window_display_name(self.comparison),
                "total_spent": round(comparison_spend, 2),
                "change_pct": None if change_pct is None else round(change_pct, 4),
                "indicator": change_indicator,
            }

        summary_lines = [
            f"Total spent: {_currency(total_spend)}",
            f"Transactions: {transaction_count}",
            f"Daily average spend: {_currency(daily_average)}",
        ]
        if total_income > 0:
            summary_lines.append(f"Total income: {_currency(total_income)}")
        net_cash = total_income - total_spend
        summary_lines.append(f"Net cash flow: {_currency(net_cash)}")

        interest_metrics = _interest_charge_metrics(frame)
        if interest_metrics["count"] > 0 and interest_metrics["total"] > 0:
            indicator = _indicator_markup("warning")
            summary_lines.append(
                f"{indicator} Interest charges: {interest_metrics['count']} transaction(s) totaling "
                f"{_currency(interest_metrics['total'])}"
            )

        if comparison_payload is not None and change_indicator is not None:
            indicator_markup = _indicator_markup(change_indicator["code"])
            change_pct_val = change_indicator["percent_display"]
            summary_lines.append(
                f"vs {comparison_payload['label']}: {indicator_markup} {change_pct_val}"
            )

        payload = {
            "window": _window_payload(self.window),
            "metrics": {
                "total_spent": round(total_spend, 2),
                "transaction_count": transaction_count,
                "daily_average_spend": round(daily_average, 2),
                "total_income": round(total_income, 2),
                "net_cash_flow": round(net_cash, 2),
            },
            "interest_charges": interest_metrics,
            "comparison": comparison_payload,
        }

        return SectionOutput(
            slug="summary",
            title="Summary",
            summary=summary_lines,
            tables_markdown=[],
            tables_structured=[],
            extra_markdown=[],
            payload=payload,
        )

    def _analyzer_section(self, spec: SectionSpec) -> SectionOutput:
        if spec.analyzer_slug is None:
            raise ExportError(f"Section '{spec.slug}' is missing analyzer configuration.")

        analyzer_spec = registry.get_spec(spec.analyzer_slug)
        context = AnalysisContext(
            cli_ctx=self.cli_ctx,
            app_config=self.cli_ctx.config,
            window=self.window,
            comparison_window=self.comparison if self.compare else None,
            output_format="json",
            compare=self.compare,
            threshold=self.threshold,
            options=dict(spec.analyzer_options),
        )
        try:
            result = analyzer_spec.factory(context)
        except AnalysisError as exc:
            # Treat analyzer-level user/data errors as non-fatal so the export can
            # continue. We surface the message in the section summary and payload
            # to keep the report informative for downstream LLMs/consumers.
            message = str(exc) or "Analyzer returned an error."
            title = spec.title if spec.title else analyzer_spec.title
            if self.cli_ctx.logger:
                self.cli_ctx.logger.debug(
                    f"Analyzer '{analyzer_spec.slug}' returned non-fatal AnalysisError: {message}"
                )
            return SectionOutput(
                slug=spec.slug,
                title=title,
                summary=[message],
                tables_markdown=[],
                tables_structured=[],
                extra_markdown=[],
                payload={
                    "analyzer": analyzer_spec.slug,
                    "status": "unavailable",
                    "error": message,
                    "window": _window_payload(self.window),
                    "comparison_window": _window_payload(self.comparison)
                    if self.compare
                    else None,
                },
            )
        except FinAgentError:
            raise
        except Exception as exc:  # pragma: no cover - analyzer errors
            raise ExportError(str(exc)) from exc

        tables_markdown = [_table_to_markdown(table) for table in result.tables]
        tables_structured = [_table_to_structured(table) for table in result.tables]
        extra_markdown = _post_process(spec.post_process, result.json_payload)

        return SectionOutput(
            slug=spec.slug,
            title=spec.title if spec.title else result.title,
            summary=list(result.summary),
            tables_markdown=tables_markdown,
            tables_structured=tables_structured,
            extra_markdown=extra_markdown,
            payload=dict(result.json_payload),
        )


# ----- Rendering helpers --------------------------------------------------------------------


def _table_to_markdown(table: TableSeries) -> str:
    if not table.columns:
        return ""
    header = "| " + " | ".join(str(column) for column in table.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(table.columns)) + " |"
    rows = [
        "| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |"
        for row in table.rows
    ]
    blocks = [f"### {table.name}"] if table.name else []
    blocks.extend([header, separator, *rows])
    return "\n".join(blocks)


def _table_to_structured(table: TableSeries) -> dict[str, Any]:
    return {
        "name": table.name,
        "columns": list(table.columns),
        "rows": [list(row) for row in table.rows],
        "metadata": dict(table.metadata),
    }


def _post_process(kind: str | None, payload: Mapping[str, Any]) -> list[str]:
    if kind == "subscriptions":
        return _subscriptions_markdown(payload)
    if kind == "unusual":
        return _unusual_markdown(payload)
    return []


def _subscriptions_markdown(payload: Mapping[str, Any]) -> list[str]:
    blocks: list[str] = []
    price_increases = payload.get("price_increases", [])
    new_merchants = payload.get("new_merchants", [])
    cancelled = payload.get("cancelled", [])

    lines: list[str] = []
    if price_increases:
        lines.append("### Detected Issues")
        for entry in price_increases:
            indicator = _indicator_markup("warning")
            change_pct = entry.get("change_pct")
            pct_display = f"+{change_pct * 100:.1f}%" if change_pct is not None else "change"
            prev_amount = safe_float(entry.get("previous_average"))
            current_amount = safe_float(entry.get("current_average"))
            lines.append(
                f"{indicator} {entry['merchant']}: {_currency(prev_amount)} → {_currency(current_amount)} ({pct_display})"
            )
    if new_merchants:
        if not lines:
            lines.append("### Detected Issues")
        for entry in new_merchants:
            indicator = _indicator_markup("positive")
            lines.append(
                f"{indicator} New subscription: {entry['merchant']} ({_currency(safe_float(entry.get('average_amount')))})"
            )
    if lines:
        blocks.append("\n".join(lines))

    if cancelled:
        cancelled_lines = ["### Recently Cancelled"]
        for entry in cancelled:
            indicator = _indicator_markup("negative")
            last_seen = entry.get("last_seen", "unknown")
            cancelled_lines.append(
                f"{indicator} {entry['merchant']} (last seen {last_seen})"
            )
        blocks.append("\n".join(cancelled_lines))

    return blocks


def _unusual_markdown(payload: Mapping[str, Any]) -> list[str]:
    anomalies = payload.get("anomalies", [])
    new_merchants = payload.get("new_merchants", [])
    if not anomalies and not new_merchants:
        return []

    lines = ["### Highlights"]
    for anomaly in anomalies[:5]:
        indicator = _indicator_markup("warning")
        change_pct = anomaly.get("spend_change_pct")
        if change_pct is not None:
            change = f"+{change_pct * 100:.1f}%"
        else:
            change = "notable"
        spend_amount = safe_float(anomaly.get("spend"))
        lines.append(
            f"{indicator} {anomaly['merchant']}: {_currency(spend_amount)} ({change})"
        )
    for merchant in new_merchants:
        indicator = _indicator_markup("positive")
        lines.append(f"{indicator} New merchant detected: {merchant}")
    return ["\n".join(lines)]


def _indicator_markup(code: str) -> str:
    emoji, fallback = INDICATORS.get(code, ("", ""))
    if not emoji and not fallback:
        return ""
    if not emoji:
        return fallback
    if not fallback:
        return emoji
    return f"{emoji} {fallback}"


def _change_indicator(change_pct: float | None) -> dict[str, Any] | None:
    if change_pct is None:
        return None
    if change_pct > 0:
        code = "increase"
    elif change_pct < 0:
        code = "decrease"
    else:
        code = "flat"
    percent_display = f"{abs(change_pct) * 100:.1f}%"
    return {
        "code": code,
        "emoji": INDICATORS.get(code, ("", ""))[0],
        "text": INDICATORS.get(code, ("", ""))[1],
        "percent_display": percent_display,
    }


def _window_payload(window: TimeWindow | None) -> Mapping[str, Any] | None:
    if window is None:
        return None
    return {
        "label": window.label,
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "display": _window_display_name(window),
    }


def _report_title(window: TimeWindow) -> str:
    return f"Financial Report — {_window_display_name(window)}"


def _window_display_name(window: TimeWindow) -> str:
    span = window.end - window.start
    inclusive_end = window.end - timedelta(days=1)
    if window.start.day == 1 and window.end.day == 1 and span.days in {28, 29, 30, 31}:
        return window.start.strftime("%B %Y")
    return f"{window.start:%Y-%m-%d} to {inclusive_end:%Y-%m-%d}"


def _currency(value: float) -> str:
    return f"${value:,.2f}"


def _interest_charge_metrics(frame) -> dict[str, Any]:
    interest_mask = _interest_charge_mask(frame)
    if interest_mask.sum() == 0:
        return {"count": 0, "total": 0.0}
    interest_frame = frame.loc[interest_mask]
    total = safe_float(interest_frame["spend_amount"].sum())
    return {
        "count": int(len(interest_frame)),
        "total": round(total, 2),
        "merchants": sorted({str(m) for m in interest_frame["merchant_display"]}),
    }


def _interest_charge_mask(frame) -> Any:
    columns = []
    for column in ("merchant", "merchant_display", "original_description"):
        if column in frame:
            columns.append(frame[column].astype(str).str.contains("interest", case=False, na=False))

    if not columns:
        return frame.assign(_interest=False)["_interest"]

    mask = columns[0]
    for candidate in columns[1:]:
        mask |= candidate

    if "spend_amount" in frame:
        mask &= frame["spend_amount"] > 0
    return mask


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _metadata_dict(metadata: ExportMetadata) -> dict[str, Any]:
    return {
        "generated_at": metadata.generated_at,
        "report_title": metadata.report_title,
        "window": metadata.window,
        "comparison_window": metadata.comparison_window,
        "sections": metadata.sections,
    }
