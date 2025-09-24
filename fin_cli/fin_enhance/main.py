"""fin-enhance CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors
from fin_cli.shared.database import connect

from .importer import CSVImportError
from .pipeline import ImportPipeline, ImportResult, ImportStats, ReviewQueue, dry_run_preview
from .review import ReviewApplicationError, apply_review_file, write_review_file


@click.command(help="Import transactions with intelligent categorization.")
@click.argument("csv_files", type=click.Path(path_type=str), nargs=-1)
@click.option("--stdin", is_flag=True, help="Read CSV input from stdin instead of files.")
@click.option("--review-output", type=click.Path(path_type=str), help="Write unresolved items to JSON for agent review.")
@click.option("--apply-review", type=click.Path(path_type=str), help="Apply review decisions from file.")
@click.option("--confidence", type=float, help="Override auto-categorization confidence threshold (default from config).")
@click.option("--skip-llm", is_flag=True, help="Use only rules-based categorization (no LLM calls).")
@click.option("--force", is_flag=True, help="Skip duplicate detection safeguards.")
@common_cli_options
@handle_cli_errors
def main(
    csv_files: tuple[str, ...],
    stdin: bool,
    review_output: str | None,
    apply_review: str | None,
    confidence: float | None,
    skip_llm: bool,
    force: bool,
    cli_ctx: CLIContext,
) -> None:
    if apply_review:
        if csv_files or stdin:
            raise click.UsageError("--apply-review should be used without CSV inputs or --stdin.")
        _handle_apply_review(Path(apply_review), cli_ctx)
        return

    if stdin and csv_files:
        raise click.UsageError("Cannot mix positional CSV arguments with --stdin.")
    if not csv_files and not stdin:
        raise click.UsageError("Provide CSV files exported via fin-extract, or use --stdin.")

    default_review_path: Path | None = None
    if not stdin and csv_files:
        default_review_path = _derive_default_review_path(Path(csv_files[0]))
    if stdin and review_output is None:
        cli_ctx.logger.info("Provide --review-output <file> to capture unresolved transactions when reading from stdin.")
    elif review_output is None and default_review_path is not None:
        review_output = str(default_review_path)
        cli_ctx.logger.info(f"No --review-output provided; defaulting to {review_output}.")

    llm_enabled_config = cli_ctx.config.categorization.llm.enabled
    effective_skip_llm = skip_llm or not llm_enabled_config
    if effective_skip_llm:
        cli_ctx.logger.info("Running in rules-only mode (LLM categorization disabled).")

    threshold = confidence if confidence is not None else cli_ctx.config.categorization.confidence.auto_approve

    csv_paths = [Path("-")] if stdin else [Path(p) for p in csv_files]

    if cli_ctx.dry_run:
        result = _handle_dry_run(
            csv_paths,
            cli_ctx,
            skip_llm=effective_skip_llm,
            auto_assign_threshold=threshold,
        )
    else:
        result = _handle_import(
            csv_paths,
            cli_ctx,
            skip_dedupe=force,
            skip_llm=effective_skip_llm,
            auto_assign_threshold=threshold,
        )

    if review_output:
        review_path = Path(review_output)
        if cli_ctx.dry_run:
            cli_ctx.logger.info(f"Dry-run: unresolved transactions would be written to {review_path}.")
        else:
            write_review_file(review_path, result.review)
            cli_ctx.logger.info(
                f"Wrote {len(result.review.transactions)} transaction review item(s) to {review_path}. Use --apply-review once decisions are ready."
            )
    elif result.review.transactions:
        cli_ctx.logger.warning(
            f"{len(result.review.transactions)} transaction(s) remain uncategorized. Re-run with --review-output to export them for review."
        )


def _derive_default_review_path(csv_path: Path) -> Path:
    if csv_path.suffix:
        base = csv_path.with_suffix("")
    else:
        base = csv_path
    return base.with_name(f"{base.name}-review.json")


def _handle_dry_run(
    csv_paths: Sequence[Path],
    cli_ctx: CLIContext,
    *,
    skip_llm: bool,
    auto_assign_threshold: float,
) -> ImportResult:
    with connect(cli_ctx.config) as connection:
        pipeline = ImportPipeline(connection, cli_ctx.logger, cli_ctx.config, track_usage=False)
        try:
            transactions = pipeline.load_transactions(csv_paths)
        except CSVImportError as exc:
            raise click.ClickException(str(exc)) from exc
        result = dry_run_preview(
            connection,
            cli_ctx.logger,
            cli_ctx.config,
            transactions,
            skip_llm=skip_llm,
            auto_assign_threshold=auto_assign_threshold,
        )
    _print_summary(cli_ctx, result.stats, dry_run=True)
    return result


def _handle_import(
    csv_paths: Sequence[Path],
    cli_ctx: CLIContext,
    *,
    skip_dedupe: bool,
    skip_llm: bool,
    auto_assign_threshold: float,
) -> ImportResult:
    with connect(cli_ctx.config) as connection:
        pipeline = ImportPipeline(connection, cli_ctx.logger, cli_ctx.config)
        try:
            transactions = pipeline.load_transactions(csv_paths)
        except CSVImportError as exc:
            raise click.ClickException(str(exc)) from exc
        result = pipeline.import_transactions(
            transactions,
            skip_dedupe=skip_dedupe,
            skip_llm=skip_llm,
            auto_assign_threshold=auto_assign_threshold,
        )
    _print_summary(cli_ctx, result.stats, dry_run=False)
    if result.auto_created_categories:
        created = ", ".join(f"{cat} > {sub}" for cat, sub in result.auto_created_categories)
        cli_ctx.logger.success(f"Auto-created categories: {created}")
    return result


def _print_summary(cli_ctx: CLIContext, stats: ImportStats, dry_run: bool) -> None:
    action = "Preview" if dry_run else "Import"
    cli_ctx.logger.info(f"{action} summary:")
    processed = stats.inserted if dry_run else stats.inserted + stats.duplicates
    cli_ctx.logger.info(f"  Transactions processed: {processed}")
    if not dry_run:
        cli_ctx.logger.info(f"  Inserted: {stats.inserted}")
        cli_ctx.logger.info(f"  Duplicates skipped: {stats.duplicates}")
    cli_ctx.logger.info(f"  Categorized automatically: {stats.categorized}")
    cli_ctx.logger.info(f"  Pending review: {stats.needs_review}")


def _handle_apply_review(decisions_path: Path, cli_ctx: CLIContext) -> None:
    with connect(cli_ctx.config) as connection:
        try:
            applied, skipped = apply_review_file(connection, decisions_path)
        except ReviewApplicationError as exc:
            raise click.ClickException(str(exc)) from exc
    cli_ctx.logger.info(
        f"Applied {applied} review decision(s). Skipped {skipped} invalid or missing entries."
    )


if __name__ == "__main__":  # pragma: no cover
    main()
