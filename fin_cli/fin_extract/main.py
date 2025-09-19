"""fin-extract CLI entrypoint."""

from __future__ import annotations

import csv
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Iterable

import click

from fin_cli.shared import models
from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors
from fin_cli.shared.database import connect

from .extractors import detect_extractor
from .parsers.pdf_loader import load_pdf_document
from .types import ExtractionResult, ExtractedTransaction


@click.command(help="Extract transactions from financial PDFs.")
@click.argument("pdf_file", type=click.Path(path_type=str), required=True)
@click.option("--output", "output_path", type=click.Path(path_type=str), help="Optional output CSV path.")
@click.option("--account-name", type=str, help="Override auto-detected account name.")
@click.option("--no-db", is_flag=True, help="Do not update the database.")
@common_cli_options
@handle_cli_errors
def main(
    pdf_file: str,
    output_path: str | None,
    account_name: str | None,
    no_db: bool,
    cli_ctx: CLIContext,
) -> None:
    document = load_pdf_document(pdf_file)
    extractor = detect_extractor(document)
    if extractor is None:
        raise click.ClickException("Unsupported statement format. No extractor matched this PDF.")
    cli_ctx.logger.info(f"Detected format: {extractor.name}")

    result = extractor.extract(document)
    if not result.transactions:
        raise click.ClickException("No transactions were extracted from the document.")

    if account_name:
        result = replace(result, metadata=replace(result.metadata, account_name=account_name))

    cli_ctx.logger.info(
        f"Account: {result.metadata.account_name} ({result.metadata.institution}) | "
        f"Transactions: {len(result.transactions)}"
    )

    if cli_ctx.dry_run:
        _emit_dry_run_summary(cli_ctx, extractor.name, result)
        return

    account_id: int | None = None
    if not no_db:
        account_id = _persist_to_database(cli_ctx, result)

    _write_csv_output(result, output_path, account_id, cli_ctx)
    cli_ctx.logger.success(
        f"Extraction complete. Output {'written to ' + output_path if output_path else 'sent to stdout'}."
    )


def _emit_dry_run_summary(
    cli_ctx: CLIContext,
    extractor_name: str,
    result: ExtractionResult,
) -> None:
    cli_ctx.logger.info("Dry run summary:")
    cli_ctx.logger.info(f"  Format detected: {extractor_name}")
    cli_ctx.logger.info(f"  Account name: {result.metadata.account_name}")
    cli_ctx.logger.info(f"  Transactions: {len(result.transactions)}")
    if result.metadata.start_date and result.metadata.end_date:
        cli_ctx.logger.info(
            f"  Date range: {result.metadata.start_date.isoformat()} to {result.metadata.end_date.isoformat()}"
        )


def _persist_to_database(cli_ctx: CLIContext, result: ExtractionResult) -> int:
    with connect(cli_ctx.config) as connection:
        account_id = models.upsert_account(
            connection,
            name=result.metadata.account_name,
            institution=result.metadata.institution,
            account_type=result.metadata.account_type,
        )
        model_transactions = [
            models.Transaction(
                date=txn.date,
                merchant=txn.merchant,
                amount=txn.amount,
                account_id=account_id,
                original_description=txn.original_description,
            )
            for txn in result.transactions
        ]
        inserted, duplicates = models.bulk_insert_transactions(connection, model_transactions)
        cli_ctx.logger.info(
            f"Inserted {inserted} transactions (skipped {duplicates} duplicates) into account ID {account_id}."
        )
        return account_id


def _write_csv_output(
    result: ExtractionResult,
    output_path: str | None,
    account_id: int | None,
    cli_ctx: CLIContext,
) -> None:
    rows = _render_csv_rows(result.transactions, account_id)
    header = ["date", "merchant", "amount", "original_description", "account_id"]
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
    else:
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        writer.writerows(rows)
        click.echo(buffer.getvalue().strip())


def _render_csv_rows(transactions: Iterable[ExtractedTransaction], account_id: int | None) -> list[list[str]]:
    rows: list[list[str]] = []
    account_value = str(account_id) if account_id is not None else ""
    for txn in transactions:
        rows.append(
            [
                txn.date.isoformat(),
                txn.merchant,
                f"{txn.amount:.2f}",
                txn.original_description,
                account_value,
            ]
        )
    return rows


if __name__ == "__main__":  # pragma: no cover
    main()
