"""Build a lightweight categorization prompt for uncategorized transactions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import click

from fin_cli.fin_query import executor
from fin_cli.shared.config import AppConfig, load_config


@dataclass
class LeftoverTransaction:
    merchant: str
    date: str
    amount: float
    original_description: str
    account_name: str


def _read_leftovers(path: Path) -> list[LeftoverTransaction]:
    leftovers: list[LeftoverTransaction] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            category = (row.get("category") or "").strip()
            subcategory = (row.get("subcategory") or "").strip()
            if category or subcategory:
                continue
            leftovers.append(
                LeftoverTransaction(
                    merchant=(row.get("merchant") or "").strip(),
                    date=(row.get("date") or "").strip(),
                    amount=float(row.get("amount") or 0.0),
                    original_description=(row.get("original_description") or "").strip(),
                    account_name=(row.get("account_name") or "").strip(),
                )
            )
    return leftovers


def _load_categories(config: AppConfig) -> list[str]:
    result = executor.run_saved_query(config=config, name="categories")
    category_idx = result.columns.index("category")
    subcategory_idx = result.columns.index("subcategory")
    return [
        f"{row[category_idx]} > {row[subcategory_idx]}"
        for row in result.rows
    ]


def _format_transactions(transactions: Sequence[LeftoverTransaction]) -> str:
    lines: list[str] = []
    for idx, txn in enumerate(transactions, start=1):
        lines.append(
            f"{idx}. Date: {txn.date}, Merchant: {txn.merchant}, Amount: ${txn.amount:.2f}, "
            f"Account: {txn.account_name}, Original: {txn.original_description}"
        )
    return "\n".join(lines)


def build_prompt(
    *,
    leftovers: Sequence[LeftoverTransaction],
    categories: Sequence[str],
) -> str:
    tx_section = _format_transactions(leftovers)
    categories_section = "\n".join(f"- {item}" for item in categories)
    return f"""
You are helping categorize a small set of transactions that existing merchant patterns did not handle.

PLEASE RUN THIS PROMPT WITH CLAUDE HAIKU 4.5.

## Available Categories
{categories_section}

## Remaining Transactions
{tx_section}

## Instructions
- For each transaction, first try to use the closest category > subcategory pair from the list above. If nothing fits, propose a sensible new category/subcategory (create only when needed).
- Return results as CSV with header: merchant,category,subcategory,confidence,notes.
- Normalize the merchant name into a clean, human-friendly form (it may differ from the transaction list when that improves clarity).
- Confidence must be between 0 and 1 (two decimal places). When you introduce a new category, note it in the `notes` column.
""".strip()


@click.command()
@click.option("--input", "input_paths", multiple=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option(
    "--workdir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Statement-processor workspace. Reads all CSVs under enriched/.",
)
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False), help="Optional path to write the prompt.")
def cli(
    input_paths: tuple[Path, ...],
    workdir: Path | None,
    output: Path | None,
) -> None:
    """Assemble a prompt for uncategorized transactions."""

    if not input_paths and workdir is None:
        raise click.ClickException("Provide --input or --workdir.")

    paths: list[Path] = list(input_paths)
    if workdir is not None:
        enriched_dir = workdir.expanduser().resolve() / "enriched"
        if not enriched_dir.exists():
            raise click.ClickException(f"{enriched_dir} does not exist. Run postprocess.py first.")
        paths.extend(sorted(enriched_dir.glob("*.csv")))

    leftovers: list[LeftoverTransaction] = []
    for csv_path in paths:
        leftovers.extend(_read_leftovers(csv_path))

    if not leftovers:
        click.echo("No uncategorized transactions found; nothing to prompt.")
        return

    config = load_config()
    categories = _load_categories(config)

    prompt = build_prompt(leftovers=leftovers, categories=categories)

    if output:
        Path(output).write_text(prompt, encoding="utf-8")
        click.echo(f"Wrote categorization prompt to {output}")
    else:
        click.echo(prompt)


if __name__ == "__main__":  # pragma: no cover
    cli()
