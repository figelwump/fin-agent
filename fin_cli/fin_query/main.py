"""fin-query CLI entrypoint."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors, pass_cli_context
from fin_cli.shared.config import AppConfig
from fin_cli.shared.database import connect
from fin_cli.shared.exceptions import QueryError
from fin_cli.shared.utils import compute_file_sha256

from . import executor, render
from .types import QueryResult, SavedQuerySummary

OUTPUT_FORMAT_CHOICES = ("table", "tsv", "csv", "json")
SCHEMA_FORMAT_CHOICES = ("table", "json")


@click.group(help="Query the financial database.")
@common_cli_options(run_migrations_on_start=False)
@handle_cli_errors
def cli(cli_ctx: CLIContext) -> None:
    """Primary Click group for fin-query commands."""
    cli_ctx.logger.debug("fin-query group initialised in read-only mode.")


@cli.command("sql")
@click.argument("query", type=str)
@click.option(
    "-p",
    "--param",
    "params",
    multiple=True,
    metavar="KEY=VALUE",
    help="Bind a named parameter for the SQL query.",
)
@click.option("--limit", type=int, help="Override the default row limit.")
@click.option(
    "--format",
    "output_format",
    default="table",
    show_default=True,
    type=click.Choice(OUTPUT_FORMAT_CHOICES),
)
@click.option(
    "--db",
    "db_override",
    type=click.Path(path_type=str),
    help="Use an alternate database path just for this command.",
)
@pass_cli_context
def run_sql(
    cli_ctx: CLIContext,
    query: str,
    params: Iterable[str],
    limit: int | None,
    output_format: str,
    db_override: str | None,
) -> None:
    """Execute ad-hoc SQL against the database."""
    _log_subcommand_entry(cli_ctx, "sql", db_override)
    if not query.strip():
        raise click.ClickException("Query text must not be empty.")

    try:
        bound_params = _parse_params(params)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    target_config = _config_for_command(cli_ctx, db_override)
    try:
        result = executor.execute_sql(
            config=target_config,
            query=query,
            params=bound_params,
            limit=limit,
        )
    except QueryError as exc:
        raise click.ClickException(str(exc)) from exc
    except NotImplementedError as exc:
        if cli_ctx.verbose:
            raise
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net for unexpected errors
        if cli_ctx.verbose:
            raise
        raise click.ClickException(f"Failed to execute SQL: {exc}") from exc

    _render_query_output(cli_ctx, result, output_format)


@cli.command("saved")
@click.argument("name", type=str)
@click.option("--month", type=str, help="Month filter for saved queries (YYYY-MM).")
@click.option("--limit", type=int, help="Limit results for saved queries.")
@click.option(
    "--min-count",
    "min_count",
    type=int,
    help="Minimum frequency filter for queries that expose :min_count (e.g., merchants).",
)
@click.option(
    "-p",
    "--param",
    "params",
    multiple=True,
    metavar="KEY=VALUE",
    help="Bind an ad-hoc parameter (overrides defaults from the manifest).",
)
@click.option(
    "--format",
    "output_format",
    default="table",
    show_default=True,
    type=click.Choice(OUTPUT_FORMAT_CHOICES),
)
@click.option(
    "--db",
    "db_override",
    type=click.Path(path_type=str),
    help="Use an alternate database path just for this command.",
)
@pass_cli_context
def run_saved(
    cli_ctx: CLIContext,
    name: str,
    month: str | None,
    limit: int | None,
    min_count: int | None,
    params: Iterable[str],
    output_format: str,
    db_override: str | None,
) -> None:
    """Run a named saved query."""
    _log_subcommand_entry(cli_ctx, "saved", db_override)
    if not name:
        raise click.ClickException("Saved query name is required.")

    try:
        bound_params = _parse_params(params)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if month:
        bound_params.setdefault("month", month)
    if min_count is not None:
        bound_params.setdefault("min_count", min_count)

    target_config = _config_for_command(cli_ctx, db_override)
    try:
        result = executor.run_saved_query(
            config=target_config,
            name=name,
            runtime_params=bound_params,
            limit=limit,
        )
    except QueryError as exc:
        raise click.ClickException(str(exc)) from exc
    except NotImplementedError as exc:
        if cli_ctx.verbose:
            raise
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        if cli_ctx.verbose:
            raise
        raise click.ClickException(f"Failed to execute saved query '{name}': {exc}") from exc

    _render_query_output(cli_ctx, result, output_format)


@cli.command("list")
@click.option(
    "--db",
    "db_override",
    type=click.Path(path_type=str),
    help="Use an alternate database path just for this command.",
)
@pass_cli_context
def list_saved(cli_ctx: CLIContext, db_override: str | None) -> None:
    """List available saved queries."""
    _log_subcommand_entry(cli_ctx, "list", db_override)
    target_config = _config_for_command(cli_ctx, db_override)
    try:
        catalog = executor.list_saved_queries(config=target_config)
    except QueryError as exc:
        raise click.ClickException(str(exc)) from exc
    except NotImplementedError as exc:
        if cli_ctx.verbose:
            raise
        raise click.ClickException(str(exc)) from exc
    _render_saved_query_catalog(cli_ctx, catalog)


@cli.command("schema")
@click.option("--table", "table_filter", type=str, help="Inspect a specific table only.")
@click.option(
    "--format",
    "output_format",
    default="table",
    show_default=True,
    type=click.Choice(SCHEMA_FORMAT_CHOICES),
)
@click.option(
    "--db",
    "db_override",
    type=click.Path(path_type=str),
    help="Use an alternate database path just for this command.",
)
@pass_cli_context
def show_schema(
    cli_ctx: CLIContext,
    table_filter: str | None,
    output_format: str,
    db_override: str | None,
) -> None:
    """Display database schema details."""
    _log_subcommand_entry(cli_ctx, "schema", db_override)
    target_config = _config_for_command(cli_ctx, db_override)
    try:
        overview = executor.describe_schema(
            config=target_config,
            table_filter=table_filter,
            as_json=output_format == "json",
        )
    except QueryError as exc:
        raise click.ClickException(str(exc)) from exc
    except NotImplementedError as exc:
        if cli_ctx.verbose:
            raise
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        if cli_ctx.verbose:
            raise
        raise click.ClickException(f"Failed to inspect schema: {exc}") from exc

    try:
        render.render_schema_overview(
            overview,
            output_format=output_format,
            logger=cli_ctx.logger,
        )
    except NotImplementedError as exc:
        if cli_ctx.verbose:
            raise
        raise click.ClickException(str(exc)) from exc


@cli.command("unimported")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    help="Recursively scan subdirectories for PDFs.",
)
@click.option(
    "--format",
    "output_format",
    default="table",
    show_default=True,
    type=click.Choice(OUTPUT_FORMAT_CHOICES),
)
@click.option(
    "--db",
    "db_override",
    type=click.Path(path_type=str),
    help="Use an alternate database path just for this command.",
)
@pass_cli_context
def unimported(
    cli_ctx: CLIContext,
    directory: Path,
    recursive: bool,
    output_format: str,
    db_override: str | None,
) -> None:
    """List PDF files in a directory that haven't been imported yet.

    Compares SHA256 hashes of PDF files against the source_file_hash column
    in the documents table to identify files not yet imported.

    Note: Only works for files imported after the source_file_hash feature
    was added. Older imports without this hash will not be detected.
    """
    _log_subcommand_entry(cli_ctx, "unimported", db_override)

    # Gather PDF files
    if recursive:
        pdf_files = list(directory.rglob("*.pdf")) + list(directory.rglob("*.PDF"))
    else:
        pdf_files = list(directory.glob("*.pdf")) + list(directory.glob("*.PDF"))

    # Dedupe (in case of overlapping globs)
    pdf_files = sorted(set(pdf_files))

    if not pdf_files:
        click.echo(f"No PDF files found in {directory}")
        return

    # Compute hashes for all PDFs
    file_hashes: dict[str, Path] = {}
    for pdf_path in pdf_files:
        try:
            file_hash = compute_file_sha256(pdf_path)
            file_hashes[file_hash] = pdf_path
        except OSError as exc:
            cli_ctx.logger.warning(f"Could not read {pdf_path}: {exc}")

    if not file_hashes:
        click.echo("Could not compute hashes for any PDF files.")
        return

    # Query database for known source_file_hashes
    target_config = _config_for_command(cli_ctx, db_override)
    with connect(target_config, read_only=True, apply_migrations=False) as conn:
        # Get all known source_file_hashes
        rows = conn.execute(
            "SELECT source_file_hash FROM documents WHERE source_file_hash IS NOT NULL"
        ).fetchall()
        known_hashes = {row["source_file_hash"] for row in rows}

    # Find unimported files
    unimported_files = [
        (path, file_hash)
        for file_hash, path in file_hashes.items()
        if file_hash not in known_hashes
    ]

    if not unimported_files:
        click.echo(f"All {len(pdf_files)} PDF file(s) in {directory} have been imported.")
        return

    # Sort by path for consistent output
    unimported_files.sort(key=lambda x: x[0])

    # Output results
    imported_count = len(pdf_files) - len(unimported_files)
    click.echo(f"Found {len(unimported_files)} unimported file(s) out of {len(pdf_files)} total:")
    click.echo()

    if output_format == "table":
        for path, _ in unimported_files:
            click.echo(f"  {path}")
    elif output_format == "csv":
        click.echo("path,hash")
        for path, file_hash in unimported_files:
            click.echo(f"{path},{file_hash}")
    elif output_format == "tsv":
        click.echo("path\thash")
        for path, file_hash in unimported_files:
            click.echo(f"{path}\t{file_hash}")
    elif output_format == "json":
        import json

        result = [{"path": str(path), "hash": file_hash} for path, file_hash in unimported_files]
        click.echo(json.dumps(result, indent=2))

    if imported_count > 0:
        click.echo()
        click.echo(f"({imported_count} file(s) already imported)")


def _log_subcommand_entry(cli_ctx: CLIContext, command: str, db_override: str | None) -> None:
    message = f"fin-query {command} invoked"
    if db_override:
        message += f" (db override: {db_override})"
    cli_ctx.logger.debug(message)


def _parse_params(pairs: Iterable[str]) -> dict[str, str]:
    """Convert KEY=VALUE CLI options into a dictionary."""
    parsed: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Parameter '{pair}' must be in KEY=VALUE format.")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("Parameter keys cannot be empty.")
        parsed[key] = value
    return parsed


def _config_for_command(cli_ctx: CLIContext, db_override: str | None) -> AppConfig:
    """Return the effective config, applying a db override if provided."""
    if not db_override:
        return cli_ctx.config
    return cli_ctx.config.with_database_path(db_override)


def _render_query_output(cli_ctx: CLIContext, result: QueryResult, output_format: str) -> None:
    try:
        render.render_query_result(
            result,
            output_format=output_format,
            logger=cli_ctx.logger,
        )
    except NotImplementedError as exc:
        if cli_ctx.verbose:
            raise
        raise click.ClickException(str(exc)) from exc


def _render_saved_query_catalog(cli_ctx: CLIContext, catalog: Iterable[SavedQuerySummary]) -> None:
    try:
        render.render_saved_query_catalog(
            list(catalog),
            logger=cli_ctx.logger,
        )
    except NotImplementedError as exc:
        if cli_ctx.verbose:
            raise
        raise click.ClickException(str(exc)) from exc


def main() -> None:
    """Entry point for console_scripts."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
