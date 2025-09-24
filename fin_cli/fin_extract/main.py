"""fin-extract CLI entrypoint."""

from __future__ import annotations

import csv
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Iterable

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors
from fin_cli.shared.models import compute_account_key

from .extractors import detect_extractor
from .parsers.pdf_loader import load_pdf_document
from .types import ExtractionResult, ExtractedTransaction, StatementMetadata


@click.command(help="Extract transactions from financial PDFs.")
@click.argument("pdf_file", type=click.Path(path_type=str), required=True)
@click.option("--output", "output_path", type=click.Path(path_type=str), help="Output CSV to file.")
@click.option("--stdout", is_flag=True, help="Output CSV to stdout.")
@click.option("--account-name", type=str, help="Override auto-detected account name.")
@common_cli_options(run_migrations_on_start=False)
@handle_cli_errors
def main(
    pdf_file: str,
    output_path: str | None,
    stdout: bool,
    account_name: str | None,
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

    if not output_path and not stdout:
        raise click.UsageError("Specify either --output <file> or --stdout for CSV output.")
    if output_path and stdout:
        raise click.UsageError("Cannot use both --output and --stdout simultaneously.")

    use_stdout = stdout and not output_path
    _write_csv_output(result, output_path if not use_stdout else None, cli_ctx)
    destination = "sent to stdout" if use_stdout else f"written to {output_path}"
    cli_ctx.logger.success(f"Extraction complete. Output {destination}.")


def _emit_dry_run_summary(
    cli_ctx: CLIContext,
    extractor_name: str,
    result: ExtractionResult,
) -> None:
    cli_ctx.logger.info("Dry run summary:")
    cli_ctx.logger.info(f"  Format detected: {extractor_name}")
    cli_ctx.logger.info(f"  Account name: {result.metadata.account_name}")
    cli_ctx.logger.info(f"  Institution: {result.metadata.institution}")
    cli_ctx.logger.info(f"  Account type: {result.metadata.account_type}")
    cli_ctx.logger.info(f"  Transactions: {len(result.transactions)}")
    if result.metadata.start_date and result.metadata.end_date:
        cli_ctx.logger.info(
            f"  Date range: {result.metadata.start_date.isoformat()} to {result.metadata.end_date.isoformat()}"
        )


def _write_csv_output(
    result: ExtractionResult,
    output_path: str | None,
    cli_ctx: CLIContext,
) -> None:
    rows = _render_csv_rows(result.transactions, result.metadata)
    header = [
        "date",
        "merchant",
        "amount",
        "original_description",
        "account_name",
        "institution",
        "account_type",
        "account_key",
    ]
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


def _render_csv_rows(
    transactions: Iterable[ExtractedTransaction],
    metadata: StatementMetadata,
) -> list[list[str]]:
    rows: list[list[str]] = []
    account_key = compute_account_key(metadata.account_name, metadata.institution, metadata.account_type)
    for txn in transactions:
        rows.append(
            [
                txn.date.isoformat(),
                txn.merchant,
                f"{txn.amount:.2f}",
                txn.original_description,
                metadata.account_name,
                metadata.institution,
                metadata.account_type,
                account_key,
            ]
        )
    return rows


if __name__ == "__main__":  # pragma: no cover
    main()
