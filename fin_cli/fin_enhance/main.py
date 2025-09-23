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
        if csv_files:
            raise click.UsageError("--apply-review should be used without additional CSV arguments.")
        _handle_apply_review(Path(apply_review), cli_ctx)
        return

    if not csv_files:
        raise click.UsageError("Provide one or more CSV files exported via fin-extract.")
    if review_mode not in {None, "auto", "json"}:
        raise click.ClickException("Supported review modes: json, auto. Interactive mode arrives later in Phase 4.")
    if review_mode == "json" and not review_output:
        raise click.UsageError("--review-mode json requires --review-output <file>.")
    if review_mode != "json" and review_output:
        cli_ctx.logger.warning("--review-output is ignored unless --review-mode json is specified.")

    llm_enabled_config = cli_ctx.config.categorization.llm.enabled
    effective_skip_llm = skip_llm or not llm_enabled_config
    if effective_skip_llm:
        cli_ctx.logger.info("Running in rules-only mode (LLM categorization disabled).")

    auto_assign_threshold = None
    if review_mode == "auto":
        auto_assign_threshold = confidence
    elif confidence != 0.8:
        cli_ctx.logger.warning("--confidence applies only to --review-mode auto. Ignoring override.")

    csv_paths = [Path(p) for p in csv_files]

    if cli_ctx.dry_run:
        result = _handle_dry_run(
            csv_paths,
            cli_ctx,
            skip_llm=effective_skip_llm,
            auto_assign_threshold=auto_assign_threshold,
        )
    else:
        result = _handle_import(
            csv_paths,
            cli_ctx,
            skip_dedupe=force,
            skip_llm=effective_skip_llm,
            auto_assign_threshold=auto_assign_threshold,
        )

    if review_mode == "json":
        review_path = Path(review_output)
        write_review_file(review_path, result.review)
        cli_ctx.logger.info(
            f"Wrote {len(result.review.transactions)} transaction review item(s) to {review_path}. Use --apply-review to record decisions."
        )
    elif review_mode == "auto" and result.review.transactions:
        cli_ctx.logger.info(
            f"{len(result.review.transactions)} transaction(s) fell below the auto confidence threshold and require follow-up."
        )


def _handle_dry_run(
    csv_paths: Sequence[Path],
    cli_ctx: CLIContext,
    *,
    skip_llm: bool,
    auto_assign_threshold: float | None,
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
    auto_assign_threshold: float | None,
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
    cli_ctx.logger.info(f"  Needs review: {stats.needs_review}")
    if stats.needs_review:
        cli_ctx.logger.info(
            "Use --review-mode json to export unresolved items or --review-mode auto to adjust confidence thresholds."
        )


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
