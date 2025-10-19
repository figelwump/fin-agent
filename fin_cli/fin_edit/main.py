"""fin-edit CLI: safe, explicit mutations for the finance DB.

Default behaviour is dry-run (preview only). Use --apply to perform writes.

We intentionally keep fin-query read-only; fin-edit holds write operations.
"""

from __future__ import annotations

from typing import Optional

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


if __name__ == "__main__":  # pragma: no cover
    main()
