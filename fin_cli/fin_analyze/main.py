"""fin-analyze CLI entrypoint (stub)."""

from __future__ import annotations

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors


@click.command(help="Run financial analyses (implementation pending).")
@click.argument("analysis_type", type=str, required=False)
@click.option("--month", type=str, help="Analyze a specific month (YYYY-MM).")
@click.option("--period", type=str, help="Analyze a period, e.g., 3m, 2w, 30d.")
@click.option("--format", "output_format", default="text", show_default=True, type=click.Choice(["text", "json"]))
@click.option("--compare", is_flag=True, help="Compare results to previous period.")
@click.option("--threshold", type=float, help="Minimum inclusion threshold for certain analyses.")
@click.option("--help-list", is_flag=True, help="List available analysis types (temporary placeholder).")
@common_cli_options
@handle_cli_errors
def main(
    analysis_type: str | None,
    month: str | None,
    period: str | None,
    output_format: str,
    compare: bool,
    threshold: float | None,
    help_list: bool,
    cli_ctx: CLIContext,
) -> None:
    """Temporary CLI stub until Phase 8 analyzers are implemented."""
    if help_list or analysis_type is None:
        cli_ctx.logger.info("Available analysis types will mirror the product spec once Phase 8 is complete.")
        return
    cli_ctx.logger.debug("fin-analyze invoked (stub).")
    raise click.ClickException("fin-analyze functionality is pending Phase 8 of the implementation plan.")


if __name__ == "__main__":  # pragma: no cover
    main()
