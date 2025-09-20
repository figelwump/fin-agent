"""fin-enhance CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors
from fin_cli.shared.database import connect

from .importer import CSVImportError
from .pipeline import ImportPipeline, ImportStats, dry_run_preview


@click.command(help="Import transactions with rules-based categorization.")
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
    if apply_review:
        raise click.ClickException("--apply-review will be available after review workflows land in Phase 4.")
    if not csv_files:
        raise click.UsageError("Provide one or more CSV files exported via fin-extract.")
    if review_mode and review_mode != "auto":
        raise click.ClickException("Interactive and JSON review modes are coming soon. Use --review-mode auto for now.")
    if review_output:
        cli_ctx.logger.warning("Review output is not yet generated; this will be implemented alongside review workflows.")
    if not skip_llm:
        cli_ctx.logger.info("LLM categorization is disabled by default in v0.1; continuing with rules-only categorization.")
    if confidence != 0.8:
        cli_ctx.logger.warning("Confidence overrides are ignored until LLM-based categorization is introduced.")

    csv_paths = [Path(p) for p in csv_files]

    if cli_ctx.dry_run:
        _handle_dry_run(csv_paths, cli_ctx)
    else:
        _handle_import(csv_paths, cli_ctx, skip_dedupe=force)


def _handle_dry_run(csv_paths: Sequence[Path], cli_ctx: CLIContext) -> None:
    with connect(cli_ctx.config) as connection:
        pipeline = ImportPipeline(connection, cli_ctx.logger, track_usage=False)
        try:
            transactions = pipeline.load_transactions(csv_paths)
        except CSVImportError as exc:
            raise click.ClickException(str(exc)) from exc
        stats = dry_run_preview(connection, cli_ctx.logger, transactions)
    _print_summary(cli_ctx, stats, dry_run=True)


def _handle_import(csv_paths: Sequence[Path], cli_ctx: CLIContext, *, skip_dedupe: bool) -> None:
    with connect(cli_ctx.config) as connection:
        pipeline = ImportPipeline(connection, cli_ctx.logger)
        try:
            transactions = pipeline.load_transactions(csv_paths)
        except CSVImportError as exc:
            raise click.ClickException(str(exc)) from exc
        stats = pipeline.import_transactions(transactions, skip_dedupe=skip_dedupe)
    _print_summary(cli_ctx, stats, dry_run=False)


def _print_summary(cli_ctx: CLIContext, stats: ImportStats, dry_run: bool) -> None:
    action = "Preview" if dry_run else "Import"
    cli_ctx.logger.info(f"{action} summary:")
    processed = stats.inserted if dry_run else stats.inserted + stats.duplicates
    cli_ctx.logger.info(f"  Transactions processed: {processed}")
    if not dry_run:
        cli_ctx.logger.info(f"  Inserted: {stats.inserted}")
        cli_ctx.logger.info(f"  Duplicates skipped: {stats.duplicates}")
    cli_ctx.logger.info(f"  Categorized via rules: {stats.categorized}")
    cli_ctx.logger.info(f"  Needs review: {stats.needs_review}")
    if stats.needs_review:
        cli_ctx.logger.info("Use review workflows (coming later in Phase 4) to resolve remaining transactions.")


if __name__ == "__main__":  # pragma: no cover
    main()
