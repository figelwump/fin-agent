"""fin-analyze CLI entrypoint (stub)."""

import click


@click.command(help="Run financial analyses (implementation pending).")
@click.argument("analysis_type", type=str, required=False)
@click.option("--month", type=str, help="Analyze a specific month (YYYY-MM).")
@click.option("--period", type=str, help="Analyze a period, e.g., 3m, 2w, 30d.")
@click.option("--format", "output_format", default="text", show_default=True, type=click.Choice(["text", "json"]))
@click.option("--compare", is_flag=True, help="Compare results to previous period.")
@click.option("--threshold", type=float, help="Minimum inclusion threshold for certain analyses.")
@click.option("--db", type=click.Path(path_type=str))
@click.option("--help-list", is_flag=True, help="List available analysis types (temporary placeholder).")
def main(analysis_type: str | None, month: str | None, period: str | None, output_format: str, compare: bool, threshold: float | None, db: str | None, help_list: bool) -> None:
    """Temporary CLI stub until Phase 8 analyzers are implemented."""
    if help_list or analysis_type is None:
        click.echo("Available analysis types will mirror the product spec once Phase 8 is complete.")
        return
    raise click.ClickException("fin-analyze functionality is pending Phase 8 of the implementation plan.")


if __name__ == "__main__":  # pragma: no cover
    main()
