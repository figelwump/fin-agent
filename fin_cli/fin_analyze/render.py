"""Rendering helpers for fin-analyze results."""

from __future__ import annotations

import json
import sys
from typing import IO, Sequence

from fin_cli.fin_analyze.types import AnalysisResult, TableSeries
from fin_cli.shared.logging import Logger

try:  # Rich is optional
    from rich.console import Console
    from rich.table import Table
    from rich import box
except ImportError:  # pragma: no cover
    Console = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    box = None  # type: ignore[assignment]


def render_result(
    result: AnalysisResult,
    *,
    output_format: str,
    logger: Logger,
    stream: IO[str] | None = None,
) -> None:
    stream = stream or sys.stdout
    fmt = (output_format or "text").lower()
    if fmt == "json":
        _render_json(result, stream=stream)
        return
    if fmt == "text":
        _render_text(result, logger=logger, stream=stream)
        return
    raise ValueError(f"Unsupported output format '{output_format}'.")


def _render_text(result: AnalysisResult, *, logger: Logger, stream: IO[str]) -> None:
    if Console and Table:
        console = Console(file=stream, highlight=False, force_terminal=False)
        console.print(f"[bold]{result.title}[/bold]")
        for line in result.summary:
            console.print(f"• {line}")
        if result.tables:
            for table_series in result.tables:
                console.print(_build_rich_table(table_series))
        elif not result.summary:
            logger.info("Analysis returned no data to display.")
        return

    # Fallback: plain text
    print(result.title, file=stream)
    for line in result.summary:
        print(f"- {line}", file=stream)
    for table_series in result.tables:
        print(f"\n{table_series.name}", file=stream)
        header = " | ".join(table_series.columns)
        print(header, file=stream)
        print("-" * len(header), file=stream)
        for row in table_series.rows:
            print(" | ".join(str(cell) for cell in row), file=stream)


def _render_json(result: AnalysisResult, *, stream: IO[str]) -> None:
    payload = {
        "title": result.title,
        "summary": list(result.summary),
        "tables": [
            {
                "name": table.name,
                "columns": list(table.columns),
                "rows": [list(row) for row in table.rows],
                "metadata": dict(table.metadata),
            }
            for table in result.tables
        ],
        "payload": dict(result.json_payload),
    }
    json.dump(payload, stream, indent=2, sort_keys=True)
    stream.write("\n")


def _build_rich_table(table_series: TableSeries) -> Table:
    rich_table = Table(
        title=table_series.name,
        box=box.SIMPLE if box else None,
        show_header=True,
        header_style="bold",
    )
    for column in table_series.columns:
        rich_table.add_column(column or "")
    for row in table_series.rows:
        rich_table.add_row(*["" if cell is None else str(cell) for cell in row])
    return rich_table

