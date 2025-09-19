"""fin-extract CLI entrypoint (stub).

Provides Click command skeleton aligned with product spec. Implementation will
be filled in during Phase 3 once shared foundations are ready.
"""

import click


@click.command(help="Extract transactions from financial PDFs (implementation pending).")
@click.argument("pdf_file", type=click.Path(path_type=str), required=False)
@click.option("--output", "output_path", type=click.Path(path_type=str), help="Optional output CSV path.")
@click.option("--account-name", type=str, help="Override auto-detected account name.")
@click.option("--no-db", is_flag=True, help="Do not update the database.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.option("--dry-run", is_flag=True, help="Preview extraction without writing data.")
def main(pdf_file: str | None, output_path: str | None, account_name: str | None, no_db: bool, verbose: bool, dry_run: bool) -> None:
    """Temporary CLI stub that signals forthcoming implementation."""
    if verbose:
        click.echo("[stub] fin-extract invoked; implementation pending Phase 3.")
    raise click.ClickException("fin-extract is not yet implemented. Follow the Phase 3 plan to complete this tool.")


if __name__ == "__main__":  # pragma: no cover - direct execution convenience
    main()
