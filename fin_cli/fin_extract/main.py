"""fin-extract CLI entrypoint (stub)."""

from __future__ import annotations

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors


@click.command(help="Extract transactions from financial PDFs (implementation pending).")
@click.argument("pdf_file", type=click.Path(path_type=str), required=False)
@click.option("--output", "output_path", type=click.Path(path_type=str), help="Optional output CSV path.")
@click.option("--account-name", type=str, help="Override auto-detected account name.")
@click.option("--no-db", is_flag=True, help="Do not update the database.")
@common_cli_options
@handle_cli_errors
def main(
    pdf_file: str | None,
    output_path: str | None,
    account_name: str | None,
    no_db: bool,
    cli_ctx: CLIContext,
) -> None:
    """Temporary CLI stub that signals forthcoming implementation."""
    cli_ctx.logger.debug("fin-extract invoked with stub implementation pending Phase 3.")
    raise click.ClickException("fin-extract is not yet implemented. Follow Phase 3 to complete this tool.")


if __name__ == "__main__":  # pragma: no cover
    main()
