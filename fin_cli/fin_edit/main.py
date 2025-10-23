"""fin-edit CLI: safe, explicit mutations for the finance DB.

Default behaviour is dry-run (preview only). Use --apply to perform writes.

We intentionally keep fin-query read-only; fin-edit holds write operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

import json
import sqlite3

import click

from fin_cli.shared.cli import (
    CLIContext,
    common_cli_options,
    handle_cli_errors,
    pass_cli_context,
)
from fin_cli.shared.database import connect
from fin_cli.shared import models
from fin_cli.shared.merchants import merchant_pattern_key
from fin_cli.shared.importers import (
    CSVImportError,
    EnrichedCSVTransaction,
    load_enriched_transactions,
)


def _effective_dry_run(cli_ctx: CLIContext, apply: bool) -> bool:
    """Return True when we should avoid writes.

    - If user passes --apply, we respect that and allow writes unless --dry-run also passed.
    - If user does not pass --apply, we remain in dry-run preview mode by default.
    """

    return cli_ctx.dry_run or (not apply)


@click.group(help="Edit utilities for updating categories and merchant patterns.")
@click.option("--apply", is_flag=True, help="Perform writes (default is preview only).")
@common_cli_options()  # migrations run automatically for write-capable tool
@handle_cli_errors
def main(apply: bool, cli_ctx: CLIContext) -> None:
    # Stash apply flag for subcommands
    cli_ctx.state["apply_flag"] = bool(apply)
    mode = "APPLY" if apply and not cli_ctx.dry_run else "DRY-RUN"
    cli_ctx.logger.debug(f"fin-edit initialised (mode={mode}, db={cli_ctx.db_path})")


@main.command("set-category")
@click.option("--transaction-id", type=int, help="Target transaction id (mutually exclusive with --fingerprint).")
@click.option(
    "--fingerprint",
    type=str,
    help="Target transaction fingerprint (mutually exclusive with --transaction-id).",
)
@click.option("--category", required=True, type=str, help="Main category name.")
@click.option("--subcategory", required=True, type=str, help="Subcategory name.")
@click.option(
    "--confidence",
    type=float,
    default=1.0,
    show_default=True,
    help="Categorization confidence value to record.",
)
@click.option(
    "--method",
    type=str,
    default="claude:interactive",
    show_default=True,
    help="Attribution string for categorization method.",
)
@click.option(
    "--create-if-missing",
    is_flag=True,
    help="Create the category/subcategory if it does not exist.",
)
@pass_cli_context
def set_category(
    cli_ctx: CLIContext,
    transaction_id: Optional[int],
    fingerprint: Optional[str],
    category: str,
    subcategory: str,
    confidence: float,
    method: str,
    create_if_missing: bool,
) -> None:
    """Assign a category to a transaction by id or fingerprint."""

    if bool(transaction_id is not None) == bool(fingerprint):
        raise click.ClickException("Provide exactly one of --transaction-id or --fingerprint.")

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    with connect(cli_ctx.config, read_only=False) as connection:
        cat_id = models.find_category_id(connection, category=category, subcategory=subcategory)
        if cat_id is None:
            if not create_if_missing:
                raise click.ClickException(
                    f"Category does not exist: '{category} > {subcategory}'. Use --create-if-missing to create it."
                )
            if preview:
                cli_ctx.logger.info(
                    f"[dry-run] Would create category: {category} > {subcategory}"
                )
                # Simulate: fetch id after creation for logging clarity
                # We cannot know the id without writing; keep as None in preview output.
            else:
                cat_id = models.get_or_create_category(
                    connection,
                    category=category,
                    subcategory=subcategory,
                    auto_generated=False,
                    user_approved=True,
                )
                cli_ctx.logger.success(
                    f"Created category '{category} > {subcategory}' (id={cat_id})."
                )

        target_desc = (
            f"transaction id={transaction_id}" if transaction_id is not None else f"fingerprint={fingerprint}"
        )

        if preview:
            cli_ctx.logger.info(
                f"[dry-run] Would set {target_desc} -> '{category} > {subcategory}', confidence={confidence}, method='{method}'"
            )
            return

        # Apply update
        if transaction_id is not None:
            cursor = connection.execute(
                """
                UPDATE transactions
                SET category_id = ?,
                    categorization_confidence = ?,
                    categorization_method = ?
                WHERE id = ?
                """,
                (cat_id, confidence, method, transaction_id),
            )
            if cursor.rowcount != 1:
                raise click.ClickException(
                    f"Expected to update exactly 1 row, updated {cursor.rowcount or 0}."
                )
        else:
            # Reuse existing helper for fingerprint updates
            assert fingerprint is not None
            models.apply_review_decision(
                connection,
                fingerprint=fingerprint,
                category_id=int(cat_id) if cat_id is not None else 0,
                confidence=confidence,
                method=method,
            )

        cli_ctx.logger.success(
            f"Updated {target_desc} -> '{category} > {subcategory}' (confidence={confidence}, method='{method}')."
        )


@main.command("add-merchant-pattern")
@click.option("--pattern", required=True, type=str, help="SQL LIKE pattern, e.g., 'STARBUCKS%'.")
@click.option("--category", required=True, type=str, help="Main category name.")
@click.option("--subcategory", required=True, type=str, help="Subcategory name.")
@click.option(
    "--confidence",
    type=float,
    default=0.95,
    show_default=True,
    help="Confidence to associate with the pattern.",
)
@click.option("--display", type=str, help="Optional human-friendly merchant name.")
@click.option(
    "--metadata",
    type=str,
    help="Optional JSON metadata to store with the pattern.",
)
@click.option(
    "--create-if-missing",
    is_flag=True,
    help="Create the target category if it does not exist.",
)
@pass_cli_context
def add_merchant_pattern(
    cli_ctx: CLIContext,
    pattern: str,
    category: str,
    subcategory: str,
    confidence: float,
    display: str | None,
    metadata: str | None,
    create_if_missing: bool,
) -> None:
    """Upsert a learned merchant pattern mapping to a category.

    Patterns should be normalized keys used by fin-enhance rules, e.g., 'STARBUCKS%'.
    """

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    meta_obj: str | dict | None = None
    if metadata:
        try:
            meta_obj = json.loads(metadata)
        except json.JSONDecodeError:
            # Keep raw string if not valid JSON to allow simple notes
            meta_obj = metadata

    with connect(cli_ctx.config, read_only=False) as connection:
        cat_id = models.find_category_id(connection, category=category, subcategory=subcategory)
        if cat_id is None:
            if not create_if_missing:
                raise click.ClickException(
                    f"Category does not exist: '{category} > {subcategory}'. Use --create-if-missing to create it."
                )
            if preview:
                cli_ctx.logger.info(
                    f"[dry-run] Would create category: {category} > {subcategory}"
                )
            else:
                cat_id = models.get_or_create_category(
                    connection,
                    category=category,
                    subcategory=subcategory,
                    auto_generated=False,
                    user_approved=True,
                )
                cli_ctx.logger.success(
                    f"Created category '{category} > {subcategory}' (id={cat_id})."
                )

        if preview:
            cli_ctx.logger.info(
                f"[dry-run] Would upsert pattern '{pattern}' -> '{category} > {subcategory}' (confidence={confidence})."
            )
            return

        models.record_merchant_pattern(
            connection,
            pattern=pattern,
            category_id=int(cat_id) if cat_id is not None else 0,
            confidence=confidence,
            pattern_display=display,
            metadata=meta_obj,
        )
        cli_ctx.logger.success(
            f"Upserted pattern '{pattern}' -> '{category} > {subcategory}' (confidence={confidence})."
        )


@dataclass(slots=True)
class ImportSummary:
    total_rows: int
    inserted: int = 0
    duplicates: int = 0
    uncategorized: int = 0
    categories_created: set[tuple[str, str]] = field(default_factory=set)
    categories_missing: set[tuple[str, str]] = field(default_factory=set)
    accounts_created: set[tuple[str, str, str]] = field(default_factory=set)
    patterns_learned: set[tuple[str, str, str]] = field(default_factory=set)
    patterns_skipped_low_conf: int = 0
    learn_threshold: float | None = None


def _format_category(category: str, subcategory: str) -> str:
    return f"{category} > {subcategory}"


def _format_account(account: tuple[str, str, str]) -> str:
    name, institution, account_type = account
    return f"{name} ({institution}, {account_type})"


def _log_import_summary(logger, summary: ImportSummary, preview: bool) -> None:
    prefix = "[dry-run] " if preview else ""
    logger.success(
        f"{prefix}Processed {summary.total_rows} transaction row(s): "
        f"inserted {summary.inserted}, duplicates {summary.duplicates}."
    )
    if summary.uncategorized > 0:
        logger.warning(
            f"{prefix}Found {summary.uncategorized} uncategorized transaction{'s' if summary.uncategorized != 1 else ''}. "
            "Use fin-query to review or the transaction-categorizer skill to categorize them."
        )
    if summary.categories_created:
        action = "Would create" if preview else "Created"
        formatted = ", ".join(
            _format_category(*item) for item in sorted(summary.categories_created)
        )
        logger.info(f"{prefix}{action} {len(summary.categories_created)} categor{'y' if len(summary.categories_created) == 1 else 'ies'}: {formatted}.")
    if summary.accounts_created:
        action = "Would create" if preview else "Created"
        formatted = ", ".join(
            _format_account(item) for item in sorted(summary.accounts_created)
        )
        logger.info(
            f"{prefix}{action} {len(summary.accounts_created)} account{'s' if len(summary.accounts_created) != 1 else ''}: {formatted}."
        )
    if summary.patterns_learned:
        action = "Would learn" if preview else "Learned"
        formatted_list = sorted(summary.patterns_learned)
        preview_count = len(formatted_list)
        sample = ", ".join(
            f"{pattern} → {category} > {subcategory}"
            for pattern, category, subcategory in formatted_list[:5]
        )
        if preview_count > 5:
            sample = f"{sample}, …"
        details = f": {sample}" if sample else "."
        logger.info(
            f"{prefix}{action} {preview_count} merchant pattern{'s' if preview_count != 1 else ''}{details}"
        )
    elif summary.learn_threshold is not None:
        logger.info(
            f"{prefix}No merchant patterns met the learning criteria (threshold {summary.learn_threshold:.2f})."
        )
    if summary.patterns_skipped_low_conf:
        threshold_text = (
            f"below confidence {summary.learn_threshold:.2f}"
            if summary.learn_threshold is not None
            else "below confidence threshold"
        )
        logger.info(
            f"{prefix}Skipped {summary.patterns_skipped_low_conf} pattern candidate{'s' if summary.patterns_skipped_low_conf != 1 else ''} {threshold_text}."
        )


def _ensure_default_confidence(value: float) -> float:
    if value < 0 or value > 1:
        raise click.ClickException("--default-confidence must be between 0 and 1 inclusive.")
    return value


def _check_fingerprint(cli_ctx: CLIContext, row: EnrichedCSVTransaction, account_id: int | None) -> None:
    expected = models.compute_transaction_fingerprint(
        row.date,
        row.amount,
        row.merchant,
        account_id,
        row.account_key,
    )
    if expected != row.fingerprint:
        cli_ctx.logger.warning(
            (
                f"Fingerprint mismatch for merchant '{row.merchant}' on {row.date.isoformat()}. "
                f"Computed {expected} but CSV provided {row.fingerprint}."
            )
        )


def _import_enriched_transactions(
    cli_ctx: CLIContext,
    rows: Sequence[EnrichedCSVTransaction],
    *,
    method: str,
    preview: bool,
    allow_category_creation: bool,
    learn_patterns: bool,
    learn_threshold: float,
) -> ImportSummary:
    summary = ImportSummary(total_rows=len(rows))
    if learn_patterns:
        summary.learn_threshold = learn_threshold
    category_cache: dict[tuple[str, str], int | None] = {}
    account_cache: dict[tuple[str, str, str], int | None] = {}
    patterns_recorded: set[tuple[str, int]] = set()

    def _resolve_pattern(row: EnrichedCSVTransaction) -> tuple[str | None, str | None, Mapping[str, Any] | str | None]:
        pattern = (row.pattern_key or "").strip() if row.pattern_key else ""
        if not pattern:
            pattern = merchant_pattern_key(row.merchant) or ""
        pattern = pattern.strip()
        display = (row.pattern_display or "").strip() if row.pattern_display else ""
        if not display and pattern:
            display = row.merchant
        metadata = row.merchant_metadata
        return (pattern or None, display or None, metadata)

    with connect(
        cli_ctx.config,
        read_only=preview,
        apply_migrations=not preview,
    ) as connection:
        # Pre-flight: cache existing categories and accounts
        for row in rows:
            # Skip category lookup if both are empty (uncategorized transaction)
            if row.category or row.subcategory:
                category_key = (row.category, row.subcategory)
                if category_key not in category_cache:
                    cat_id = models.find_category_id(
                        connection,
                        category=row.category,
                        subcategory=row.subcategory,
                    )
                    if cat_id is None:
                        summary.categories_missing.add(category_key)
                    category_cache[category_key] = cat_id
            else:
                # Track uncategorized transactions
                summary.uncategorized += 1

            if row.account_id is None:
                account_key = (row.account_name, row.institution, row.account_type)
                if account_key not in account_cache:
                    result = connection.execute(
                        "SELECT id FROM accounts WHERE name = ? AND institution = ? AND account_type = ?",
                        account_key,
                    ).fetchone()
                    account_cache[account_key] = int(result[0]) if result else None
            else:
                account_cache[(row.account_name, row.institution, row.account_type)] = row.account_id

        if summary.categories_missing and not allow_category_creation:
            missing_formatted = ", ".join(
                _format_category(*item) for item in sorted(summary.categories_missing)
            )
            raise click.ClickException(
                "Missing categories: "
                f"{missing_formatted}. Re-run without --no-create-categories or create them manually first."
            )

        if preview:
            for row in rows:
                # Handle category lookups only if categorized
                if row.category or row.subcategory:
                    category_key = (row.category, row.subcategory)
                    if category_cache.get(category_key) is None:
                        summary.categories_created.add(category_key)

                if row.account_id is None:
                    account_key = (row.account_name, row.institution, row.account_type)
                    if account_cache.get(account_key) is None:
                        summary.accounts_created.add(account_key)

                _check_fingerprint(cli_ctx, row, account_cache.get((row.account_name, row.institution, row.account_type)))
                existing = connection.execute(
                    "SELECT 1 FROM transactions WHERE fingerprint = ? LIMIT 1",
                    (row.fingerprint,),
                ).fetchone()
                if existing:
                    summary.duplicates += 1
                else:
                    summary.inserted += 1
                if learn_patterns and (row.category and row.subcategory):
                    pattern_key, _, _ = _resolve_pattern(row)
                    if pattern_key:
                        if row.confidence >= learn_threshold:
                            summary.patterns_learned.add(
                                (pattern_key, row.category, row.subcategory)
                            )
                        else:
                            summary.patterns_skipped_low_conf += 1
            return summary

        # Apply mode: perform mutations
        for row in rows:
            # Handle category creation only if categorized
            cat_id = None
            if row.category or row.subcategory:
                category_key = (row.category, row.subcategory)
                cat_id = category_cache.get(category_key)
                if cat_id is None:
                    cat_id = models.get_or_create_category(
                        connection,
                        category=row.category,
                        subcategory=row.subcategory,
                        auto_generated=False,
                        user_approved=True,
                    )
                    category_cache[category_key] = cat_id
                    summary.categories_created.add(category_key)

            account_id = row.account_id
            account_key = (row.account_name, row.institution, row.account_type)
            if account_id is None:
                account_id = account_cache.get(account_key)
                if account_id is None:
                    account_id = models.upsert_account(
                        connection,
                        name=row.account_name,
                        institution=row.institution,
                        account_type=row.account_type,
                        auto_detected=False,
                    )
                    account_cache[account_key] = account_id
                    summary.accounts_created.add(account_key)
            else:
                account_cache[account_key] = account_id

            _check_fingerprint(cli_ctx, row, account_id)
            pattern_key, pattern_display, merchant_metadata = _resolve_pattern(row)
            txn_metadata = None
            if pattern_key or pattern_display or merchant_metadata is not None:
                payload: dict[str, Any] = {}
                if pattern_key:
                    payload["merchant_pattern_key"] = pattern_key
                if pattern_display:
                    payload["merchant_pattern_display"] = pattern_display
                if merchant_metadata is not None:
                    payload["merchant_metadata"] = merchant_metadata
                if payload:
                    txn_metadata = payload

            txn = models.Transaction(
                date=row.date,
                merchant=row.merchant,
                amount=row.amount,
                account_id=account_id,
                account_key=row.account_key,
                category_id=cat_id,
                original_description=row.original_description,
                categorization_confidence=row.confidence if cat_id else None,
                categorization_method=row.method or method,
                metadata=txn_metadata,
            )
            inserted = models.insert_transaction(
                connection,
                txn,
                allow_update=True,
            )
            if inserted:
                summary.inserted += 1
                if cat_id:
                    models.increment_category_usage(connection, cat_id)
            else:
                summary.duplicates += 1
            # Only learn patterns for categorized transactions
            if learn_patterns and pattern_key and cat_id is not None and (row.category and row.subcategory):
                if row.confidence >= learn_threshold:
                    cache_key = (pattern_key, cat_id)
                    if cache_key not in patterns_recorded:
                        models.record_merchant_pattern(
                            connection,
                            pattern=pattern_key,
                            category_id=cat_id,
                            confidence=row.confidence,
                            pattern_display=pattern_display,
                            metadata=merchant_metadata,
                        )
                        patterns_recorded.add(cache_key)
                    summary.patterns_learned.add(
                        (pattern_key, row.category, row.subcategory)
                    )
                else:
                    summary.patterns_skipped_low_conf += 1

        return summary


@main.command("import-transactions")
@click.argument("csv_path", type=click.Path(dir_okay=False, allow_dash=True))
@click.option(
    "--method",
    type=str,
    default="manual:fin-edit",
    show_default=True,
    help="Categorization method to use when CSV does not supply one.",
)
@click.option(
    "--default-confidence",
    type=float,
    default=1.0,
    show_default=True,
    help="Confidence to apply when CSV omits the confidence column.",
)
@click.option(
    "--no-create-categories",
    is_flag=True,
    help="Fail if a referenced category does not exist instead of creating it.",
)
@click.option(
    "--learn-patterns",
    is_flag=True,
    help="Automatically record merchant patterns for high-confidence rows.",
)
@click.option(
    "--learn-threshold",
    type=float,
    default=0.9,
    show_default=True,
    help="Minimum confidence required before --learn-patterns records a merchant pattern.",
)
@pass_cli_context
def import_transactions_command(
    cli_ctx: CLIContext,
    csv_path: str,
    method: str,
    default_confidence: float,
    no_create_categories: bool,
    learn_patterns: bool,
    learn_threshold: float,
) -> None:
    """Import enriched CSV transactions into the database."""

    default_conf = _ensure_default_confidence(default_confidence)
    learn_threshold = _ensure_default_confidence(learn_threshold)

    try:
        rows = load_enriched_transactions(csv_path, default_confidence=default_conf)
    except CSVImportError as exc:
        raise click.ClickException(str(exc)) from exc

    if not rows:
        cli_ctx.logger.info("No transactions found in CSV; nothing to import.")
        return

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    cli_ctx.logger.debug(
        f"Loaded {len(rows)} enriched row(s) from {csv_path} (preview={preview})."
    )

    summary = _import_enriched_transactions(
        cli_ctx,
        rows,
        method=method,
        preview=preview,
        allow_category_creation=not no_create_categories,
        learn_patterns=learn_patterns,
        learn_threshold=learn_threshold,
    )
    _log_import_summary(cli_ctx.logger, summary, preview)


if __name__ == "__main__":  # pragma: no cover
    main()
