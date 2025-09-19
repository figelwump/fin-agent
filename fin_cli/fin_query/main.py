"""fin-query CLI entrypoint (stub)."""

from __future__ import annotations

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors, pass_cli_context


@click.group(help="Query the financial database (implementation pending).")
@common_cli_options
@handle_cli_errors
def cli(cli_ctx: CLIContext) -> None:
    """Primary Click group for fin-query commands."""
    cli_ctx.logger.debug("fin-query group initialised (stub).")


@cli.command("sql")
@click.argument("query", type=str)
@click.option("--format", "output_format", default="table", show_default=True, type=click.Choice(["table", "tsv", "csv", "json"]))
@click.option("--db", "db_override", type=click.Path(path_type=str), help="Use an alternate database path just for this command.")
@pass_cli_context
def run_sql(cli_ctx: CLIContext, query: str, output_format: str, db_override: str | None) -> None:
    """Execute ad-hoc SQL against the database (stub)."""
    _log_subcommand_entry(cli_ctx, "sql", db_override)
    raise click.ClickException("fin-query SQL execution is not yet implemented. Phase 7 will deliver this feature.")


@cli.command("saved")
@click.argument("name", type=str)
@click.option("--month", type=str, help="Month filter for saved queries (YYYY-MM).")
@click.option("--limit", type=int, help="Limit results for saved queries.")
@click.option("--format", "output_format", default="table", show_default=True, type=click.Choice(["table", "tsv", "csv", "json"]))
@pass_cli_context
def run_saved(
    cli_ctx: CLIContext,
    name: str,
    month: str | None,
    limit: int | None,
    output_format: str,
) -> None:
    """Run a named saved query (stub)."""
    _log_subcommand_entry(cli_ctx, "saved", None)
    raise click.ClickException("fin-query saved queries will arrive in Phase 7.")


@cli.command("list")
@pass_cli_context
def list_saved(cli_ctx: CLIContext) -> None:
    """List available saved queries (stub)."""
    _log_subcommand_entry(cli_ctx, "list", None)
    raise click.ClickException("Saved query catalog not yet available. See Phase 7 of the implementation plan.")


@cli.command("schema")
@pass_cli_context
def show_schema(cli_ctx: CLIContext) -> None:
    """Display database schema details (stub)."""
    _log_subcommand_entry(cli_ctx, "schema", None)
    raise click.ClickException("Schema introspection lands in Phase 7.")


def _log_subcommand_entry(cli_ctx: CLIContext, command: str, db_override: str | None) -> None:
    message = f"fin-query {command} subcommand invoked (stub)."
    if db_override:
        message += f" Override DB: {db_override}"
    cli_ctx.logger.debug(message)


def main() -> None:
    """Entry point for console_scripts."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
