"""Output rendering helpers for fin-query."""

from __future__ import annotations

import csv
import json
import sys
from typing import IO, Iterable, Mapping, Sequence

from fin_cli.shared.logging import Logger

from .types import QueryResult, SchemaOverview, SavedQuerySummary

try:  # Rich is an optional runtime dependency in some contexts
    from rich.console import Console
    from rich.table import Table
    from rich import box
except ImportError:  # pragma: no cover - should not occur in standard installs
    Console = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    box = None  # type: ignore[assignment]


def render_query_result(
    result: QueryResult,
    *,
    output_format: str,
    logger: Logger,
    stream=None,
) -> None:
    """Render a query result set to the desired format."""
    output_stream = stream or sys.stdout
    fmt = (output_format or "table").lower()

    if fmt == "table":
        _render_table(result, logger=logger, stream=output_stream)
    elif fmt == "csv":
        _render_delimited(result, stream=output_stream, delimiter=",")
    elif fmt == "tsv":
        _render_delimited(result, stream=output_stream, delimiter="\t")
    elif fmt == "json":
        _render_json(result, stream=output_stream)
    else:  # pragma: no cover - Click validation should prevent this
        raise ValueError(f"Unsupported output format '{output_format}'.")

    if result.truncated:
        # Warn via logger so callers honour the safety limit in interactive sessions.
        logger.warning(
            f"Result truncated to {result.limit_value} rows. Re-run with --limit or --format csv/json for full output."
        )


def render_saved_query_catalog(
    catalog: Sequence[SavedQuerySummary],
    *,
    logger: Logger,
    stream=None,
) -> None:
    """Render the saved query catalog for display."""
    output_stream = stream or sys.stdout
    if not catalog:
        print("No saved queries defined.", file=output_stream)
        return

    if Console and Table:
        console = Console(file=output_stream, highlight=False, force_terminal=False)
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Name", style="bold")
        table.add_column("Description")
        table.add_column("Parameters")
        for summary in catalog:
            table.add_row(summary.name, summary.description, _format_parameters(summary.parameters))
        console.print(table)
    else:  # pragma: no cover - Rich missing fallback
        writer = csv.writer(output_stream)
        writer.writerow(["name", "description", "parameters"])
        for summary in catalog:
            writer.writerow(
                [
                    summary.name,
                    summary.description,
                    _format_parameters(summary.parameters),
                ]
            )


def render_schema_overview(
    overview: SchemaOverview,
    *,
    output_format: str,
    logger: Logger,
    stream=None,
) -> None:
    """Render schema metadata to the output stream."""
    output_stream = stream or sys.stdout
    fmt = (output_format or "table").lower()

    if fmt == "json":
        payload = {
            "database": str(overview.database_path),
            "tables": [
                {
                    "name": table.name,
                    "columns": [
                        {"name": name, "type": column_type, "not_null": not_null}
                        for name, column_type, not_null in table.columns
                    ],
                    "indexes": list(table.indexes),
                    "foreign_keys": [
                        {"from": column, "table": target_table, "to": target_column}
                        for column, target_table, target_column in table.foreign_keys
                    ],
                    "estimated_rows": table.estimated_row_count,
                }
                for table in overview.tables
            ],
        }
        json.dump(payload, output_stream, indent=2)
        output_stream.write("\n")
        return

    if Console and Table:
        console = Console(file=output_stream, highlight=False, force_terminal=False)
        for table in overview.tables:
            console.print(f"[bold]{table.name}[/bold]")
            column_table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            column_table.add_column("Column")
            column_table.add_column("Type")
            column_table.add_column("Not Null")
            for name, column_type, not_null in table.columns:
                column_table.add_row(name, column_type, "✅" if not_null else "")
            console.print(column_table)

            if table.indexes:
                idx_table = Table(box=box.MINIMAL_DOUBLE_HEAD, show_header=False)
                idx_table.add_column("Indexes")
                for index in table.indexes:
                    idx_table.add_row(index)
                console.print(idx_table)

            if table.foreign_keys:
                fk_table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
                fk_table.add_column("From")
                fk_table.add_column("References")
                for column, ref_table, ref_column in table.foreign_keys:
                    fk_table.add_row(column, f"{ref_table}.{ref_column}")
                console.print(fk_table)

            if table.estimated_row_count is not None:
                console.print(f"~{table.estimated_row_count} rows\n")
    else:  # pragma: no cover - Rich missing fallback
        for table in overview.tables:
            print(f"Table: {table.name}", file=output_stream)
            for name, column_type, not_null in table.columns:
                print(f"  {name:<24} {column_type:<12} {'NOT NULL' if not_null else ''}", file=output_stream)
            if table.indexes:
                print("  Indexes:", ", ".join(table.indexes), file=output_stream)
            if table.foreign_keys:
                print("  Foreign Keys:", file=output_stream)
                for column, ref_table, ref_column in table.foreign_keys:
                    print(f"    {column} -> {ref_table}.{ref_column}", file=output_stream)
            if table.estimated_row_count is not None:
                print(f"  ~{table.estimated_row_count} rows", file=output_stream)
            print("", file=output_stream)

    if not overview.tables:
        logger.info(f"No tables found in database {overview.database_path}.")


def _render_table(result: QueryResult, *, logger: Logger, stream: IO[str]) -> None:
    if Console and Table:
        console = Console(file=stream, highlight=False, force_terminal=False)
        if result.description:
            console.print(f"[bold]{result.description}[/bold]")

        table = Table(box=box.SIMPLE_HEAVY if box else None, show_header=bool(result.columns), header_style="bold")
        for column in result.columns:
            table.add_column(column or "")

        if result.rows:
            for row in result.rows:
                table.add_row(*[_stringify(cell) for cell in row])
        else:
            logger.info("Query returned zero rows.")

        console.print(table)
    else:  # pragma: no cover - Rich missing fallback
        if result.description:
            print(result.description, file=stream)
        writer = csv.writer(stream)
        if result.columns:
            writer.writerow(result.columns)
        writer.writerows(result.rows)


def _render_delimited(result: QueryResult, *, stream: IO[str], delimiter: str) -> None:
    writer = csv.writer(stream, delimiter=delimiter)
    if result.columns:
        writer.writerow(result.columns)
    for row in result.rows:
        writer.writerow(_stringify(cell) for cell in row)


def _render_json(result: QueryResult, *, stream: IO[str]) -> None:
    records: list[dict[str, object]] = []
    if result.columns:
        for row in result.rows:
            records.append({column: _convert_json_value(value) for column, value in zip(result.columns, row)})
    else:
        for row in result.rows:
            records.append({"values": list(row)})
    json.dump(records, stream, indent=2)
    stream.write("\n")


def _format_parameters(params: Mapping[str, object]) -> str:
    if not params:
        return "—"
    formatted: list[str] = []
    for key, meta in params.items():
        if isinstance(meta, Mapping):
            pieces = [key]
            if "type" in meta:
                pieces.append(f"[{meta['type']}]")
            if "default" in meta:
                pieces.append(f"default={meta['default']}")
            if "description" in meta:
                pieces.append(meta["description"])
            formatted.append(" ".join(str(part) for part in pieces if part))
        else:
            formatted.append(str(key))
    return "\n".join(formatted)


def _stringify(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _convert_json_value(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value
