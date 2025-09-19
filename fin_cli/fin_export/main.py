"""fin-export CLI entrypoint (stub)."""

from __future__ import annotations

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors, pass_cli_context


@click.group(help="Export financial data (implementation pending).")
@common_cli_options
@handle_cli_errors
def cli(cli_ctx: CLIContext) -> None:
    """Top-level command group."""
    cli_ctx.logger.debug("fin-export group initialised (stub).")


@cli.command("markdown")
@click.option("--month", type=str, help="Month to export (YYYY-MM).")
@click.option("--output", type=click.Path(path_type=str), help="Output file path (default stdout).")
@click.option("--sections", type=str, help="Comma-separated sections to include.")
@click.option("--period", type=str, help="Include multi-period trends (e.g., 6m).")
@click.option("--template", type=click.Path(path_type=str), help="Custom Markdown template path.")
@pass_cli_context
def export_markdown(
    cli_ctx: CLIContext,
    month: str | None,
    output: str | None,
    sections: str | None,
    period: str | None,
    template: str | None,
) -> None:
    """Placeholder for Markdown export functionality."""
    cli_ctx.logger.debug("fin-export markdown invoked (stub).")
    raise click.ClickException("fin-export markdown generation arrives in Phase 9.")


def main() -> None:
    """Entry point for console_scripts."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
