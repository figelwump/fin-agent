"""Rendering helpers for fin-analyze results."""

from __future__ import annotations

import csv
import json
import sys
from typing import IO

from fin_cli.fin_analyze.types import AnalysisResult, TableSeries
from fin_cli.shared.logging import Logger

try:  # Rich is optional
    from rich import box
    from rich.console import Console
    from rich.table import Table
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
    if fmt == "csv":
        _render_csv(result, stream=stream)
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


def _render_csv(result: AnalysisResult, *, stream: IO[str]) -> None:
    """Emit a CSV representation that stays agent- and script-friendly."""

    writer = csv.writer(stream)

    # Always include the title as the first row so parsers retain analysis context.
    writer.writerow(["title", result.title])

    if result.summary:
        for line in result.summary:
            writer.writerow(["summary", line])

    if result.tables:
        # Separate the narrative block from table sections with a blank row.
        writer.writerow([])

    for index, table in enumerate(result.tables):
        if index > 0:
            writer.writerow([])

        writer.writerow(["table", table.name])

        if table.metadata:
            for key, value in sorted(table.metadata.items()):
                writer.writerow(
                    [
                        "metadata",
                        key,
                        json.dumps(value, sort_keys=True, default=str),
                    ]
                )

        if table.columns:
            writer.writerow(list(table.columns))
        else:
            writer.writerow([])

        for row in table.rows:
            writer.writerow(["" if cell is None else cell for cell in row])


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
