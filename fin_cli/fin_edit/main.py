"""fin-edit CLI: safe, explicit mutations for the finance DB.

Default behaviour is dry-run (preview only). Use --apply to perform writes.

We intentionally keep fin-query read-only; fin-edit holds write operations.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import click

from fin_cli.shared import models
from fin_cli.shared.cli import (
    CLIContext,
    common_cli_options,
    handle_cli_errors,
    pass_cli_context,
)
from fin_cli.shared.database import connect
from fin_cli.shared.importers import (
    CSVImportError,
    EnrichedCSVTransaction,
    load_enriched_transactions,
)
from fin_cli.shared.merchants import merchant_pattern_key


def _format_transaction_summary(row: sqlite3.Row) -> str:
    category = row["category"] if row["category"] else "(uncategorized)"
    subcategory = row["subcategory"]
    if subcategory:
        category_display = f"{category} > {subcategory}"
    else:
        category_display = category

    account_name = row["account_name"] or "(unknown account)"
    institution = row["institution"]
    account_display = f"{account_name} ({institution})" if institution else account_name

    amount = float(row["amount"]) if row["amount"] is not None else 0.0
    return (
        f"id={row['id']}: {row['date']} {row['merchant']} "
        f"${amount:,.2f} [{category_display}] @ {account_display}"
    )


def _effective_dry_run(cli_ctx: CLIContext, apply: bool) -> bool:
    """Return True when we should avoid writes.

    - If user passes --apply, we respect that and allow writes unless --dry-run also passed.
    - If user does not pass --apply, we remain in dry-run preview mode by default.
    """

    return cli_ctx.dry_run or (not apply)


def _sanitize_where_clause(where_clause: str) -> str:
    clause = where_clause.strip()
    if not clause:
        raise click.ClickException("--where clause cannot be empty.")
    if ";" in clause:
        raise click.ClickException("Semicolons are not allowed in --where clauses.")
    return clause


def _fetch_transactions_for_where(
    connection: sqlite3.Connection, where_clause: str
) -> list[sqlite3.Row]:
    query = f"""
        SELECT
            t.id,
            t.date,
            t.merchant,
            t.amount,
            c.category,
            c.subcategory,
            a.name AS account_name,
            a.institution AS institution
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        LEFT JOIN accounts a ON a.id = t.account_id
        WHERE {where_clause}
        ORDER BY t.date ASC, t.id ASC
    """
    return connection.execute(query).fetchall()


# ---------------------------------------------------------------------------
# Asset tracking helpers


def _load_json(path: str | Path) -> Mapping[str, Any]:
    try:
        content = Path(path).read_text()
    except OSError as exc:  # pragma: no cover - surfaced via Click
        raise click.ClickException(f"Unable to read file '{path}': {exc}") from exc
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"File '{path}' is not valid JSON: {exc}") from exc


def _resolve_source(connection: sqlite3.Connection, source: str) -> int:
    """Map logical source strings to asset_sources rows."""
    normalized = source.lower()
    if normalized == "statement":
        return models.get_or_create_asset_source(
            connection, name="Statement Import", source_type="statement", priority=1
        )
    if normalized == "manual":
        return models.get_or_create_asset_source(
            connection, name="Manual Entry", source_type="manual", priority=2
        )
    if normalized == "api":
        return models.get_or_create_asset_source(
            connection, name="API Sync", source_type="api", priority=3
        )
    if normalized == "upload":
        return models.get_or_create_asset_source(
            connection, name="Statement Import", source_type="upload", priority=1
        )
    raise click.ClickException(f"Unknown source '{source}'. Expected statement/manual/api/upload.")


def _resolve_account_id(connection: sqlite3.Connection, holding: Mapping[str, Any]) -> int:
    account_id = holding.get("account_id")
    if account_id is not None:
        return int(account_id)
    account_key = holding.get("account_key")
    if not account_key:
        raise click.ClickException("Holding entry requires either 'account_id' or 'account_key'.")
    account_id = models.find_account_id_by_key(connection, account_key)
    if account_id is None:
        raise click.ClickException(
            f"Unknown account key '{account_key}'. Create the account first."
        )
    return account_id


def _resolve_instrument_id(connection: sqlite3.Connection, symbol: str) -> int:
    row = connection.execute(
        "SELECT id FROM instruments WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    if row:
        return int(row["id"])
    raise click.ClickException(
        f"Instrument with symbol '{symbol}' not found. Run 'fin-edit instruments-upsert' first."
    )


def _validate_currency(value: str) -> str:
    if not value or len(value) != 3 or not value.isalpha():
        raise click.ClickException(f"Invalid currency '{value}'. Expected 3-letter code.")
    return value.upper()


def _validate_vehicle_type(vehicle_type: str | None) -> str | None:
    allowed = {"stock", "ETF", "mutual_fund", "bond", "MMF", "fund_LP", "note", "option", "crypto"}
    if vehicle_type is None:
        return None
    if vehicle_type not in allowed:
        raise click.ClickException(
            f"Invalid vehicle_type '{vehicle_type}'. Allowed: {', '.join(sorted(allowed))}"
        )
    return vehicle_type


def _infer_asset_class(inst: Mapping[str, Any]) -> tuple[str, str] | None:
    """Lightweight heuristic to map an instrument to an asset class.

    Prefers explicit hints in the payload (asset_class/main/sub) and falls back to
    name/symbol/vehicle_type keyword checks. This is intentionally conservative and
    defaults to leaving instruments unclassified when uncertain.
    """

    explicit = inst.get("asset_class") or inst.get("classification")
    if isinstance(explicit, Mapping):
        main = explicit.get("main_class") or explicit.get("main")
        sub = explicit.get("sub_class") or explicit.get("sub")
        if main and sub:
            return str(main).lower(), str(sub).lower()

    name = (inst.get("name") or "").lower()
    symbol = (inst.get("symbol") or "").upper()
    vehicle = inst.get("vehicle_type")

    def has_keyword(*candidates: str) -> bool:
        lowered = name
        for cand in candidates:
            if cand.lower() in lowered or cand.upper() in symbol:
                return True
        return False

    if vehicle == "MMF" or has_keyword("sweep", "mmf"):
        return ("cash", "cash sweep")

    if vehicle in {"bond", "note"}:
        if has_keyword("tips"):
            return ("bonds", "TIPS")
        if has_keyword("treasury", "t-bill", "ust", "govt"):
            return ("bonds", "treasury")
        if has_keyword("muni", "municipal"):
            return ("bonds", "muni")
        if has_keyword("high yield", "hy"):
            return ("bonds", "corporate HY")
        if has_keyword("corp", "corporate"):
            return ("bonds", "corporate IG")
        return ("bonds", "treasury")

    if vehicle == "crypto" or has_keyword("bitcoin", "ethereum", "crypto", "btc", "eth"):
        return ("alternatives", "crypto")

    if has_keyword("reit"):
        return ("alternatives", "REIT")

    if vehicle == "fund_LP":
        if has_keyword("vc", "venture", "angel"):
            return ("alternatives", "VC/Angel")
        if has_keyword("real estate"):
            return ("alternatives", "real estate fund")
        return ("alternatives", "private equity")

    if vehicle == "option":
        return ("other", "options")

    if vehicle in {"stock", "ETF", "mutual_fund"}:
        if has_keyword("emerging") or symbol.startswith("EEM"):
            return ("equities", "emerging markets")
        if has_keyword("intl", "international", "ex-us", "ex us", "global ex us"):
            return ("equities", "intl equity")
        if has_keyword("small cap", "smallcap") or "SC" in symbol:
            return ("equities", "small cap")
        if has_keyword("large cap", "largecap"):
            return ("equities", "large cap")
        sector_words = (
            "technology",
            "health",
            "energy",
            "utilities",
            "financial",
            "industrial",
            "consumer",
            "communications",
        )
        if any(has_keyword(word) for word in sector_words):
            return ("equities", "sector fund")
        return ("equities", "US equity")

    # Fallback: leave unclassified; downstream queries surface missing rows.
    return None


def _autoclassify_instruments(
    connection: sqlite3.Connection,
    *,
    instrument_payloads: Mapping[str, Mapping[str, Any]],
    preview: bool,
    logger,
) -> None:
    """Attach inferred asset classes to instruments when unambiguous."""

    for symbol, inst in instrument_payloads.items():
        inferred = _infer_asset_class(inst)
        if inferred is None:
            logger.debug(f"No classification inference for {symbol}; leaving unclassified.")
            continue

        class_id = models.find_asset_class_id(
            connection, main_class=inferred[0], sub_class=inferred[1]
        )
        if class_id is None:
            logger.warning(
                f"Inferred asset class {inferred[0]}/{inferred[1]} not found; skipping classification for {symbol}."
            )
            continue

        if preview:
            logger.info(
                f"[dry-run] Would classify instrument {symbol} -> {inferred[0]}/{inferred[1]} (asset_class_id={class_id})."
            )
            continue

        instr_id = _resolve_instrument_id(connection, symbol)
        models.ensure_instrument_classification(
            connection,
            instrument_id=instr_id,
            asset_class_id=class_id,
            is_primary=True,
        )


def _normalize_holding_value(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    """Ensure required fields and derive price/market_value when one is missing."""

    required = ["account_key", "symbol", "as_of_date", "quantity"]
    missing = [field for field in required if field not in entry]
    if missing:
        raise click.ClickException(f"holding_value missing required field(s): {', '.join(missing)}")

    try:
        date.fromisoformat(entry["as_of_date"])
    except Exception as exc:
        raise click.ClickException(f"Invalid as_of_date '{entry['as_of_date']}': {exc}") from exc

    try:
        quantity = float(entry["quantity"])
    except Exception as exc:  # pragma: no cover - click error path
        raise click.ClickException(f"Invalid quantity '{entry['quantity']}': {exc}") from exc
    if quantity < 0:
        raise click.ClickException(
            "Quantity must be non-negative. Use position_side on holding for shorts."
        )

    price = entry.get("price")
    market_value = entry.get("market_value")
    if price is None and market_value is None:
        raise click.ClickException("holding_value requires at least one of price or market_value.")
    if price is None and market_value is not None:
        price = float(market_value) / quantity if quantity != 0 else 0.0
    if market_value is None and price is not None:
        market_value = float(price) * quantity

    valuation_currency = _validate_currency(entry.get("valuation_currency", "USD"))
    fx_rate_used = float(entry.get("fx_rate_used", 1.0))
    if fx_rate_used <= 0:
        raise click.ClickException("fx_rate_used must be positive.")

    return {
        **entry,
        "quantity": quantity,
        "price": float(price) if price is not None else None,
        "market_value": float(market_value) if market_value is not None else None,
        "valuation_currency": valuation_currency,
        "fx_rate_used": fx_rate_used,
    }


def _process_asset_payload(
    connection: sqlite3.Connection,
    *,
    payload: Mapping[str, Any],
    preview: bool,
    logger,
) -> int:
    """Shared logic for holding-values upserts and asset-import shortcut."""

    # Optional instruments bootstrap
    instruments = payload.get("instruments") or []
    instrument_by_symbol: dict[str, Mapping[str, Any]] = {}
    for inst in instruments:
        if "name" not in inst:
            raise click.ClickException("Instrument entry missing 'name'.")
        if not inst.get("symbol") and not inst.get("identifiers"):
            raise click.ClickException("Instrument requires either 'symbol' or 'identifiers'.")

        currency = _validate_currency(inst.get("currency", "USD"))
        vehicle_type = _validate_vehicle_type(inst.get("vehicle_type"))

        symbol = inst.get("symbol")
        if symbol:
            instrument_by_symbol[str(symbol)] = inst

        if preview:
            logger.info(
                f"[dry-run] Would upsert instrument {inst.get('name')} ({inst.get('symbol')})"
            )
            continue
        models.upsert_instrument(
            connection,
            name=inst["name"],
            symbol=inst.get("symbol"),
            exchange=inst.get("exchange"),
            currency=currency,
            vehicle_type=vehicle_type,
            identifiers=inst.get("identifiers"),
            metadata=inst.get("metadata"),
        )

    if instrument_by_symbol:
        _autoclassify_instruments(
            connection,
            instrument_payloads=instrument_by_symbol,
            preview=preview,
            logger=logger,
        )

    # Optional holdings bootstrap
    holdings_payload = payload.get("holdings") or []
    holding_id_cache: dict[tuple[int, int], int] = {}
    for h in holdings_payload:
        if preview:
            logger.info(
                f"[dry-run] Would ensure holding for account_key={h.get('account_key')} symbol={h.get('symbol')}"
            )
            continue
        acct_id = _resolve_account_id(connection, h)
        instr_id = _resolve_instrument_id(connection, h.get("symbol"))
        holding_id = models.get_or_create_holding(
            connection,
            account_id=acct_id,
            instrument_id=instr_id,
            status=h.get("status", "active"),
            position_side=h.get("position_side", "long"),
            opened_at=h.get("opened_at"),
            closed_at=h.get("closed_at"),
            metadata=h.get("metadata"),
        )
        holding_id_cache[(acct_id, instr_id)] = holding_id

    document_block = payload.get("document")
    document_id = None
    document_hash = None
    if document_block:
        document_hash = document_block.get("document_hash")
        if document_hash:
            source_id = _resolve_source(connection, document_block.get("source_type", "statement"))
            if preview:
                logger.info(
                    f"[dry-run] Would register document hash={document_hash} via source={source_id}"
                )
            else:
                document_id = models.register_document(
                    connection,
                    document_hash=document_hash,
                    source_id=source_id,
                    broker=document_block.get("broker"),
                    period_end_date=document_block.get("period_end_date"),
                    file_path=document_block.get("file_path"),
                    source_file_hash=document_block.get("source_file_hash"),
                    metadata=document_block.get("metadata"),
                )

    inserted = 0
    holding_values = payload.get("holding_values") or []
    for value in holding_values:
        value = _normalize_holding_value(value)
        account_key = value.get("account_key")
        symbol = value.get("symbol")

        if preview:
            logger.info(
                f"[dry-run] Would upsert holding_value {account_key}/{symbol} {value.get('as_of_date')}"
            )
            continue

        acct_id = _resolve_account_id(connection, value)
        instr_id = _resolve_instrument_id(connection, symbol)
        holding_id = holding_id_cache.get((acct_id, instr_id))
        if holding_id is None:
            holding_id = models.get_or_create_holding(
                connection,
                account_id=acct_id,
                instrument_id=instr_id,
                status="active",
            )

        source_value = value.get("source", "statement")
        source_id = _resolve_source(connection, source_value)

        doc_id = document_id
        if value.get("document_hash") and value.get("document_hash") != document_hash:
            doc_id = models.register_document(
                connection,
                document_hash=value["document_hash"],
                source_id=source_id,
                broker=document_block.get("broker") if document_block else None,
                period_end_date=document_block.get("period_end_date") if document_block else None,
            )

        models.upsert_holding_value(
            connection,
            holding_id=holding_id,
            as_of_date=value["as_of_date"],
            as_of_datetime=value.get("as_of_datetime"),
            quantity=float(value["quantity"]),
            price=float(value["price"]) if value.get("price") is not None else None,
            market_value=(
                float(value["market_value"]) if value.get("market_value") is not None else None
            ),
            accrued_interest=value.get("accrued_interest"),
            fees=value.get("fees"),
            source_id=source_id,
            document_id=doc_id,
            valuation_currency=value.get("valuation_currency", "USD"),
            fx_rate_used=float(value.get("fx_rate_used", 1.0)),
            metadata=value.get("metadata"),
        )
        inserted += 1

    return inserted


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
@click.option(
    "--transaction-id",
    type=int,
    help="Target transaction id (mutually exclusive with --fingerprint).",
)
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
@click.option(
    "--where",
    type=str,
    help="SQL WHERE clause to target multiple transactions (mutually exclusive with --transaction-id/--fingerprint).",
)
@pass_cli_context
def set_category(
    cli_ctx: CLIContext,
    transaction_id: int | None,
    fingerprint: str | None,
    where: str | None,
    category: str,
    subcategory: str,
    confidence: float,
    method: str,
    create_if_missing: bool,
) -> None:
    """Assign a category to a transaction by id or fingerprint."""

    selectors = [transaction_id is not None, fingerprint is not None, bool(where)]
    if sum(selectors) != 1:
        raise click.ClickException(
            "Provide exactly one of --transaction-id, --fingerprint, or --where."
        )

    where_clause = _sanitize_where_clause(where) if where else None

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
                cli_ctx.logger.info(f"[dry-run] Would create category: {category} > {subcategory}")
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

        if where_clause:
            target_desc = f"transactions matching WHERE ({where_clause})"
        elif transaction_id is not None:
            target_desc = f"transaction id={transaction_id}"
        else:
            target_desc = f"fingerprint={fingerprint}"

        matched_rows: list[sqlite3.Row] | None = None
        if where_clause is not None:
            matched_rows = _fetch_transactions_for_where(connection, where_clause)
            if not matched_rows:
                raise click.ClickException("No transactions matched the provided --where clause.")
            cli_ctx.logger.info(f"Matched {len(matched_rows)} transaction(s) via --where filter:")
            for row in matched_rows:
                cli_ctx.logger.info(_format_transaction_summary(row))

        if preview:
            cli_ctx.logger.info(
                f"[dry-run] Would set {target_desc} -> '{category} > {subcategory}', confidence={confidence}, method='{method}'"
            )
            return

        # Apply update
        if where_clause is not None:
            cursor = connection.execute(
                f"""
                UPDATE transactions
                SET category_id = ?,
                    categorization_confidence = ?,
                    categorization_method = ?
                WHERE {where_clause}
                """,
                (cat_id, confidence, method),
            )
            if cursor.rowcount == 0:
                raise click.ClickException("No rows were updated. Check your --where clause.")
            cli_ctx.logger.success(
                f"Updated {cursor.rowcount} transaction(s) -> '{category} > {subcategory}' (confidence={confidence}, method='{method}')."
            )
        elif transaction_id is not None:
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
                cli_ctx.logger.info(f"[dry-run] Would create category: {category} > {subcategory}")
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


@main.command("delete-transactions")
@click.option(
    "--id",
    "transaction_ids",
    type=int,
    multiple=True,
    help="Transaction id to delete (use multiple --id flags).",
)
@pass_cli_context
def delete_transactions(
    cli_ctx: CLIContext,
    transaction_ids: Sequence[int],
) -> None:
    """Safely delete transactions by id."""

    if not transaction_ids:
        raise click.ClickException("Provide at least one --id value.")

    unique_ids = sorted(set(int(txn_id) for txn_id in transaction_ids))

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    with connect(cli_ctx.config, read_only=False) as connection:
        placeholders = ",".join("?" for _ in unique_ids)
        cursor = connection.execute(
            f"""
            SELECT
                t.id,
                t.date,
                t.merchant,
                t.amount,
                c.category,
                c.subcategory,
                a.name AS account_name,
                a.institution
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN accounts a ON t.account_id = a.id
            WHERE t.id IN ({placeholders})
            ORDER BY t.date, t.id
            """,
            unique_ids,
        )
        rows = cursor.fetchall()

        found_ids = {int(row["id"]) for row in rows}
        missing = [str(txn_id) for txn_id in unique_ids if txn_id not in found_ids]
        if missing:
            raise click.ClickException("Transactions not found: " + ", ".join(missing))

        for row in rows:
            cli_ctx.logger.info(_format_transaction_summary(row))

        if preview:
            cli_ctx.logger.info(
                f"[dry-run] {len(rows)} transaction(s) matched. Re-run with --apply after user confirmation to delete."
            )
            return

        connection.execute(
            f"DELETE FROM transactions WHERE id IN ({placeholders})",
            unique_ids,
        )
        cli_ctx.logger.success(f"Deleted {len(rows)} transaction(s).")


# ---------------------------------------------------------------------------
# Asset tracking subcommands


@main.command("instruments-upsert")
@click.option(
    "--from",
    "from_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON file containing an 'instruments' array.",
)
@pass_cli_context
def instruments_upsert(cli_ctx: CLIContext, from_path: Path) -> None:
    """Upsert instrument records from a JSON payload."""

    payload = _load_json(from_path)
    instruments = payload.get("instruments")
    if not isinstance(instruments, list) or not instruments:
        raise click.ClickException("Input JSON must include a non-empty 'instruments' array.")

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    inserted = updated = 0
    with connect(cli_ctx.config, read_only=False) as connection:
        for inst in instruments:
            if "name" not in inst:
                raise click.ClickException("Instrument entry missing 'name'.")
            if not inst.get("symbol") and not inst.get("identifiers"):
                raise click.ClickException("Instrument requires either 'symbol' or 'identifiers'.")

            currency = _validate_currency(inst.get("currency", "USD"))
            vehicle_type = _validate_vehicle_type(inst.get("vehicle_type"))

            symbol = inst.get("symbol")
            exchange = inst.get("exchange")
            identifiers = inst.get("identifiers") or {}

            row = connection.execute(
                """
                SELECT id, identifiers FROM instruments
                WHERE symbol = ?
                  AND (exchange IS ? OR exchange = ? OR (exchange IS NULL AND ? IS NULL))
                """,
                (symbol, exchange, exchange, exchange),
            ).fetchone()
            if row is None and identifiers:
                candidates = connection.execute(
                    "SELECT id, identifiers FROM instruments WHERE identifiers IS NOT NULL"
                ).fetchall()
                for cand in candidates:
                    if models._instrument_matches_identifiers(cand, identifiers):  # type: ignore[attr-defined]
                        row = cand
                        break

            if preview:
                action = "update" if row else "insert"
                cli_ctx.logger.info(
                    f"[dry-run] Would {action} instrument {inst.get('name')} ({symbol})"
                )
                continue

            models.upsert_instrument(
                connection,
                name=inst["name"],
                symbol=symbol,
                exchange=exchange,
                currency=currency,
                vehicle_type=vehicle_type,
                identifiers=identifiers,
                metadata=inst.get("metadata"),
            )
            if row:
                updated += 1
            else:
                inserted += 1

    if not preview:
        cli_ctx.logger.success(f"Upserted instruments: inserted={inserted}, updated={updated}")


@main.command("holdings-add")
@click.option(
    "--account-id",
    type=int,
    help="Target account id (optional if provided via JSON).",
)
@click.option(
    "--instrument-symbol",
    type=str,
    help="Instrument symbol (optional if provided via JSON).",
)
@click.option(
    "--status",
    type=click.Choice(["active", "closed"]),
    default="active",
    show_default=True,
)
@click.option(
    "--from",
    "from_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional JSON file containing a 'holdings' array.",
)
@pass_cli_context
def holdings_add(
    cli_ctx: CLIContext,
    account_id: int | None,
    instrument_symbol: str | None,
    status: str,
    from_path: Path | None,
) -> None:
    """Create holdings for account/instrument pairs (idempotent for active holdings)."""

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    items: list[Mapping[str, Any]] = []
    if from_path:
        payload = _load_json(from_path)
        holdings = payload.get("holdings")
        if not isinstance(holdings, list) or not holdings:
            raise click.ClickException("Input JSON must include a non-empty 'holdings' array.")
        items.extend(holdings)
    else:
        if account_id is None or not instrument_symbol:
            raise click.ClickException(
                "Provide --account-id and --instrument-symbol or --from JSON."
            )
        items.append(
            {
                "account_id": account_id,
                "symbol": instrument_symbol,
                "status": status,
            }
        )

    created = 0
    with connect(cli_ctx.config, read_only=False) as connection:
        for holding in items:
            acct_id = account_id or _resolve_account_id(connection, holding)
            symbol = holding.get("symbol") or instrument_symbol
            if not symbol:
                raise click.ClickException("Holding entry missing 'symbol'.")
            instr_id = _resolve_instrument_id(connection, symbol)
            if preview:
                cli_ctx.logger.info(
                    f"[dry-run] Would ensure holding account_id={acct_id} symbol={symbol} status={status}"
                )
                continue
            models.get_or_create_holding(
                connection,
                account_id=acct_id,
                instrument_id=instr_id,
                status=status,
                position_side=holding.get("position_side", "long"),
                opened_at=holding.get("opened_at"),
                closed_at=holding.get("closed_at"),
                metadata=holding.get("metadata"),
            )
            created += 1

    if not preview:
        cli_ctx.logger.success(f"Holdings processed: {created}")


@main.command("holdings-deactivate")
@click.option("--holding-id", required=True, type=int, help="Holding id to deactivate.")
@click.option(
    "--closed-at",
    type=str,
    default=None,
    help="Optional closure date (YYYY-MM-DD). Defaults to today.",
)
@pass_cli_context
def holdings_deactivate(cli_ctx: CLIContext, holding_id: int, closed_at: str | None) -> None:
    """Mark a holding as closed."""

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)
    closed_date = closed_at or date.today().isoformat()

    with connect(cli_ctx.config, read_only=False) as connection:
        row = connection.execute(
            "SELECT id, status FROM holdings WHERE id = ?", (holding_id,)
        ).fetchone()
        if row is None:
            raise click.ClickException(f"Holding id={holding_id} not found.")
        if preview:
            cli_ctx.logger.info(
                f"[dry-run] Would set holding id={holding_id} status=closed on {closed_date}"
            )
            return
        connection.execute(
            "UPDATE holdings SET status = 'closed', closed_at = ? WHERE id = ?",
            (closed_date, holding_id),
        )
    cli_ctx.logger.success(f"Holding id={holding_id} closed (closed_at={closed_date}).")


@main.command("holdings-move")
@click.option("--holding-id", required=True, type=int, help="Holding id to move.")
@click.option("--account-id", required=True, type=int, help="Destination account id.")
@pass_cli_context
def holdings_move(cli_ctx: CLIContext, holding_id: int, account_id: int) -> None:
    """Move a holding to a different account."""

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    with connect(cli_ctx.config, read_only=False) as connection:
        row = connection.execute(
            "SELECT instrument_id, account_id FROM holdings WHERE id = ?", (holding_id,)
        ).fetchone()
        if row is None:
            raise click.ClickException(f"Holding id={holding_id} not found.")
        instrument_id = int(row["instrument_id"])

        # Check for unique active constraint in destination.
        conflict = connection.execute(
            """
            SELECT 1 FROM holdings
            WHERE account_id = ? AND instrument_id = ? AND status = 'active'
            """,
            (account_id, instrument_id),
        ).fetchone()
        if conflict:
            raise click.ClickException(
                "Destination already has an active holding for this instrument; deactivate or close it first."
            )

        if preview:
            cli_ctx.logger.info(
                f"[dry-run] Would move holding id={holding_id} from account {row['account_id']} to {account_id}"
            )
            return

        connection.execute(
            "UPDATE holdings SET account_id = ? WHERE id = ?",
            (account_id, holding_id),
        )

    cli_ctx.logger.success(f"Holding id={holding_id} moved to account {account_id}.")


@main.command("holdings-transfer")
@click.option("--symbol", required=True, type=str, help="Instrument symbol to transfer.")
@click.option(
    "--from",
    "from_account",
    required=True,
    type=str,
    help="Source account name or ID.",
)
@click.option(
    "--to",
    "to_account",
    required=True,
    type=str,
    help="Destination account name or ID.",
)
@click.option(
    "--transfer-date",
    type=str,
    default=None,
    help="Transfer date (YYYY-MM-DD). Defaults to today.",
)
@click.option(
    "--carry-cost-basis",
    is_flag=True,
    help="Copy cost basis from source holding to destination.",
)
@pass_cli_context
def holdings_transfer(
    cli_ctx: CLIContext,
    symbol: str,
    from_account: str,
    to_account: str,
    transfer_date: str | None,
    carry_cost_basis: bool,
) -> None:
    """Transfer a holding from one account to another.

    This closes the source holding and creates a new active holding at the
    destination. Use this for custodian transfers (e.g., moving shares from
    UBS to Schwab).

    Unlike holdings-move, this preserves the source holding's history and
    creates a proper audit trail with closed_at/opened_at dates.
    """

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)
    xfer_date = transfer_date or date.today().isoformat()

    # Validate transfer date format
    try:
        date.fromisoformat(xfer_date)
    except ValueError as exc:
        raise click.ClickException(f"Invalid transfer date '{xfer_date}': {exc}") from exc

    with connect(cli_ctx.config, read_only=False) as connection:
        # Resolve instrument
        instrument_row = connection.execute(
            "SELECT id, name FROM instruments WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if instrument_row is None:
            raise click.ClickException(f"Instrument with symbol '{symbol}' not found.")
        instrument_id = int(instrument_row["id"])
        instrument_name = instrument_row["name"]

        # Resolve source account (try as ID first, then as name)
        source_account_id: int | None = None
        if from_account.isdigit():
            source_account_id = int(from_account)
            source_row = connection.execute(
                "SELECT id, name FROM accounts WHERE id = ?",
                (source_account_id,),
            ).fetchone()
        else:
            source_row = connection.execute(
                "SELECT id, name FROM accounts WHERE name = ?",
                (from_account,),
            ).fetchone()
            if source_row:
                source_account_id = int(source_row["id"])

        if source_row is None:
            raise click.ClickException(f"Source account '{from_account}' not found.")
        source_account_name = source_row["name"]

        # Resolve destination account
        dest_account_id: int | None = None
        if to_account.isdigit():
            dest_account_id = int(to_account)
            dest_row = connection.execute(
                "SELECT id, name FROM accounts WHERE id = ?",
                (dest_account_id,),
            ).fetchone()
        else:
            dest_row = connection.execute(
                "SELECT id, name FROM accounts WHERE name = ?",
                (to_account,),
            ).fetchone()
            if dest_row:
                dest_account_id = int(dest_row["id"])

        if dest_row is None:
            raise click.ClickException(f"Destination account '{to_account}' not found.")
        dest_account_name = dest_row["name"]

        # Find active source holding
        source_holding = connection.execute(
            """
            SELECT id, status, cost_basis_total, cost_basis_method, position_side, metadata
            FROM holdings
            WHERE account_id = ? AND instrument_id = ? AND status = 'active'
            """,
            (source_account_id, instrument_id),
        ).fetchone()

        if source_holding is None:
            raise click.ClickException(
                f"No active holding for {symbol} found in account '{source_account_name}'."
            )

        source_holding_id = int(source_holding["id"])
        cost_basis_total = source_holding["cost_basis_total"]
        cost_basis_method = source_holding["cost_basis_method"]
        position_side = source_holding["position_side"] or "long"

        # Check if destination already has an active holding
        dest_holding = connection.execute(
            """
            SELECT id FROM holdings
            WHERE account_id = ? AND instrument_id = ? AND status = 'active'
            """,
            (dest_account_id, instrument_id),
        ).fetchone()

        if dest_holding:
            raise click.ClickException(
                f"Destination account '{dest_account_name}' already has an active holding for {symbol}. "
                "Close it first or use a different approach."
            )

        # Preview output
        cli_ctx.logger.info("Transfer Preview:")
        cli_ctx.logger.info(f"  Symbol: {symbol} ({instrument_name})")
        cli_ctx.logger.info(f"  From: {source_account_name} (holding #{source_holding_id})")
        cli_ctx.logger.info(f"    → Set status='closed', closed_at={xfer_date}")
        cli_ctx.logger.info(f"  To: {dest_account_name} (new holding)")
        cli_ctx.logger.info(f"    → Set status='active', opened_at={xfer_date}")
        if carry_cost_basis and cost_basis_total is not None:
            cli_ctx.logger.info(f"    → Cost basis: ${cost_basis_total:,.2f} (carried from source)")
        elif carry_cost_basis:
            cli_ctx.logger.info("    → Cost basis: None (source has no cost basis)")

        if preview:
            cli_ctx.logger.info("")
            cli_ctx.logger.info("Use --apply to execute this transfer.")
            return

        # Execute transfer
        # 1. Close source holding
        connection.execute(
            "UPDATE holdings SET status = 'closed', closed_at = ? WHERE id = ?",
            (xfer_date, source_holding_id),
        )

        # 2. Create destination holding
        new_cost_basis = cost_basis_total if carry_cost_basis else None
        new_cost_method = cost_basis_method if carry_cost_basis else None

        cursor = connection.execute(
            """
            INSERT INTO holdings (
                account_id, instrument_id, status, position_side,
                opened_at, cost_basis_total, cost_basis_method, created_date
            ) VALUES (?, ?, 'active', ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                dest_account_id,
                instrument_id,
                position_side,
                xfer_date,
                new_cost_basis,
                new_cost_method,
            ),
        )
        new_holding_id = cursor.lastrowid

    cli_ctx.logger.success(
        f"Transferred {symbol} from {source_account_name} to {dest_account_name}. "
        f"Source holding #{source_holding_id} closed, new holding #{new_holding_id} created."
    )


@main.command("holding-values-upsert")
@click.option(
    "--from",
    "from_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="JSON file with 'holding_values' (optionally also 'document', 'instruments', 'holdings').",
)
@pass_cli_context
def holding_values_upsert(cli_ctx: CLIContext, from_path: Path) -> None:
    """Upsert holding value rows from a normalized JSON payload."""

    payload = _load_json(from_path)
    holding_values = payload.get("holding_values")
    if not isinstance(holding_values, list) or not holding_values:
        raise click.ClickException("Input JSON must include a non-empty 'holding_values' array.")

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    with connect(cli_ctx.config, read_only=False) as connection:
        inserted = _process_asset_payload(
            connection, payload=payload, preview=preview, logger=cli_ctx.logger
        )

    if not preview:
        cli_ctx.logger.success(f"Upserted holding_values rows: {inserted}")


@main.command("documents-register")
@click.option("--hash", "doc_hash", required=True, type=str, help="Document SHA256 hash.")
@click.option("--source", "source_name", default="Statement Import", show_default=True, type=str)
@click.option("--source-type", default="statement", show_default=True, type=str)
@click.option("--priority", default=1, show_default=True, type=int)
@click.option("--broker", type=str, default=None)
@click.option("--period-end-date", type=str, default=None)
@click.option("--file-path", type=str, default=None)
@pass_cli_context
def documents_register(
    cli_ctx: CLIContext,
    doc_hash: str,
    source_name: str,
    source_type: str,
    priority: int,
    broker: str | None,
    period_end_date: str | None,
    file_path: str | None,
) -> None:
    """Register a document for idempotent imports."""

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    with connect(cli_ctx.config, read_only=False) as connection:
        source_id = models.get_or_create_asset_source(
            connection, name=source_name, source_type=source_type, priority=priority
        )
        if preview:
            cli_ctx.logger.info(
                f"[dry-run] Would register document hash={doc_hash} source_id={source_id}"
            )
            return
        doc_id = models.register_document(
            connection,
            document_hash=doc_hash,
            source_id=source_id,
            broker=broker,
            period_end_date=period_end_date,
            file_path=file_path,
        )
    cli_ctx.logger.success(f"Registered document hash={doc_hash} (id={doc_id}).")


@main.command("documents-delete")
@click.option("--hash", "doc_hash", required=True, type=str, help="Document SHA256 hash.")
@pass_cli_context
def documents_delete(cli_ctx: CLIContext, doc_hash: str) -> None:
    """Delete a document and clear linked holding_values (idempotent)."""

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    with connect(cli_ctx.config, read_only=False) as connection:
        row = connection.execute(
            "SELECT id FROM documents WHERE document_hash = ?",
            (doc_hash,),
        ).fetchone()
        if row is None:
            raise click.ClickException(f"Document hash '{doc_hash}' not found.")
        doc_id = int(row["id"])

        if preview:
            cli_ctx.logger.info(
                f"[dry-run] Would delete document id={doc_id} and null linked holding_values"
            )
            return

        connection.execute(
            "UPDATE holding_values SET document_id = NULL WHERE document_id = ?",
            (doc_id,),
        )
        connection.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    cli_ctx.logger.success(f"Deleted document hash={doc_hash} (id={doc_id}).")


@main.command("asset-import")
@click.option(
    "--from",
    "from_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Normalized asset JSON (document + instruments + holdings + holding_values).",
)
@pass_cli_context
def asset_import(cli_ctx: CLIContext, from_path: Path) -> None:
    """Convenience wrapper to import an entire asset payload in one step."""

    payload = _load_json(from_path)
    if "holding_values" not in payload:
        raise click.ClickException("Payload must include a 'holding_values' array.")

    apply_flag = bool(cli_ctx.state.get("apply_flag"))
    preview = _effective_dry_run(cli_ctx, apply_flag)

    with connect(cli_ctx.config, read_only=False) as connection:
        inserted = _process_asset_payload(
            connection, payload=payload, preview=preview, logger=cli_ctx.logger
        )

    if not preview:
        cli_ctx.logger.success(f"Imported asset payload rows: holding_values={inserted}")


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
        logger.info(
            f"{prefix}{action} {len(summary.categories_created)} categor{'y' if len(summary.categories_created) == 1 else 'ies'}: {formatted}."
        )
    if summary.accounts_created:
        action = "Would create" if preview else "Created"
        formatted = ", ".join(_format_account(item) for item in sorted(summary.accounts_created))
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


def _check_fingerprint(
    cli_ctx: CLIContext, row: EnrichedCSVTransaction, account_id: int | None
) -> None:
    expected = models.compute_transaction_fingerprint(
        row.date,
        row.amount,
        row.merchant,
        account_id,
        row.account_key,
    )
    if expected != row.fingerprint:
        cli_ctx.logger.warning(
            f"Fingerprint mismatch for merchant '{row.merchant}' on {row.date.isoformat()}. "
            f"Computed {expected} but CSV provided {row.fingerprint}."
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

    def _resolve_pattern(
        row: EnrichedCSVTransaction,
    ) -> tuple[str | None, str | None, Mapping[str, Any] | str | None]:
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
                # Prefer lookup by (institution, account_type, last_4_digits)
                account_key = (
                    row.account_name,
                    row.institution,
                    row.account_type,
                    row.last_4_digits,
                )
                if account_key not in account_cache:
                    result = None
                    if row.last_4_digits:
                        result = connection.execute(
                            "SELECT id FROM accounts WHERE institution = ? AND account_type = ? AND last_4_digits = ?",
                            (row.institution, row.account_type, row.last_4_digits),
                        ).fetchone()
                    if not result:
                        # Fallback to legacy triple including name
                        result = connection.execute(
                            "SELECT id FROM accounts WHERE name = ? AND institution = ? AND account_type = ?",
                            (row.account_name, row.institution, row.account_type),
                        ).fetchone()
                    account_cache[account_key] = int(result[0]) if result else None
            else:
                account_cache[
                    (row.account_name, row.institution, row.account_type, row.last_4_digits)
                ] = row.account_id

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
                    account_key = (
                        row.account_name,
                        row.institution,
                        row.account_type,
                        row.last_4_digits,
                    )
                    if account_cache.get(account_key) is None:
                        summary.accounts_created.add(
                            (row.account_name, row.institution, row.account_type)
                        )

                _check_fingerprint(
                    cli_ctx,
                    row,
                    account_cache.get((row.account_name, row.institution, row.account_type)),
                )
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
            account_key = (row.account_name, row.institution, row.account_type, row.last_4_digits)
            if account_id is None:
                account_id = account_cache.get(account_key)
                if account_id is None:
                    account_id = models.upsert_account(
                        connection,
                        name=row.account_name,
                        institution=row.institution,
                        account_type=row.account_type,
                        last_4_digits=row.last_4_digits,
                        auto_detected=False,
                    )
                    account_cache[account_key] = account_id
                    summary.accounts_created.add(
                        (row.account_name, row.institution, row.account_type)
                    )
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
            if (
                learn_patterns
                and pattern_key
                and cat_id is not None
                and (row.category and row.subcategory)
            ):
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
                    summary.patterns_learned.add((pattern_key, row.category, row.subcategory))
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

    cli_ctx.logger.debug(f"Loaded {len(rows)} enriched row(s) from {csv_path} (preview={preview}).")

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
