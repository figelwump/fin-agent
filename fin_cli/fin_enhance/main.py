"""fin-enhance CLI entrypoint (stub)."""

from __future__ import annotations

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors


@click.command(help="Import and categorize transactions (implementation pending).")
@click.argument("csv_files", type=click.Path(path_type=str), nargs=-1)
@click.option("--review-mode", type=click.Choice(["interactive", "json", "auto"]), help="Review mode for uncategorized transactions.")
@click.option("--review-output", type=click.Path(path_type=str), help="Write review items to file (JSON mode).")
@click.option("--apply-review", type=click.Path(path_type=str), help="Apply review decisions from file.")
@click.option("--confidence", type=float, default=0.8, show_default=True, help="Minimum confidence for auto-categorization.")
@click.option("--skip-llm", is_flag=True, help="Use only rules-based categorization.")
@click.option("--force", is_flag=True, help="Skip duplicate detection safeguards.")
@common_cli_options
@handle_cli_errors
def main(
    csv_files: tuple[str, ...],
    review_mode: str | None,
    review_output: str | None,
    apply_review: str | None,
    confidence: float,
    skip_llm: bool,
    force: bool,
    cli_ctx: CLIContext,
) -> None:
    """Temporary CLI stub signposting future Phase 4/5 functionality."""
    if not csv_files and not apply_review:
        raise click.UsageError("Provide CSV files to import or --apply-review for decisions.")
    cli_ctx.logger.debug("fin-enhance invoked with stub implementation pending Phases 4-5.")
    raise click.ClickException("fin-enhance is not yet implemented. Complete Phases 4-5 to enable functionality.")


if __name__ == "__main__":  # pragma: no cover
    main()
