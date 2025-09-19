"""fin-query CLI entrypoint (stub)."""

import click


@click.group(help="Query the financial database (implementation pending).")
def cli() -> None:
    """Primary Click group for fin-query commands."""


@cli.command("sql")
@click.argument("query", type=str)
@click.option("--format", "output_format", default="table", show_default=True, type=click.Choice(["table", "tsv", "csv", "json"]))
@click.option("--db", type=click.Path(path_type=str))
def run_sql(query: str, output_format: str, db: str | None) -> None:
    """Execute ad-hoc SQL against the database (stub)."""
    raise click.ClickException("fin-query SQL execution is not yet implemented. Phase 7 will deliver this feature.")


@cli.command("saved")
@click.argument("name", type=str)
@click.option("--month", type=str, help="Month filter for saved queries (YYYY-MM).")
@click.option("--limit", type=int, help="Limit results for saved queries.")
@click.option("--format", "output_format", default="table", show_default=True, type=click.Choice(["table", "tsv", "csv", "json"]))
@click.option("--db", type=click.Path(path_type=str))
def run_saved(name: str, month: str | None, limit: int | None, output_format: str, db: str | None) -> None:
    """Run a named saved query (stub)."""
    raise click.ClickException("fin-query saved queries will arrive in Phase 7.")


@cli.command("list")
def list_saved() -> None:
    """List available saved queries (stub)."""
    raise click.ClickException("Saved query catalog not yet available. See Phase 7 of the implementation plan.")


@cli.command("schema")
@click.option("--db", type=click.Path(path_type=str))
def show_schema(db: str | None) -> None:
    """Display database schema details (stub)."""
    raise click.ClickException("Schema introspection lands in Phase 7.")


def main() -> None:
    """Entry point for console_scripts."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
