"""Build a categorization prompt for uncategorized transactions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

import click

from fin_cli.fin_query import executor
from fin_cli.shared.config import load_config


def _load_categories() -> list[str]:
    """Load existing categories from the database."""
    config = load_config()
    result = executor.run_saved_query(config=config, name="categories")
    category_idx = result.columns.index("category")
    subcategory_idx = result.columns.index("subcategory")
    return [
        f"{row[category_idx]} > {row[subcategory_idx]}"
        for row in result.rows
    ]


def _format_transactions(transactions: Sequence[dict[str, Any]]) -> str:
    """Format transactions for the prompt."""
    lines: list[str] = []
    for txn in transactions:
        txn_id = txn.get("id", "")
        date = txn.get("date", "")
        merchant = txn.get("merchant", "")
        amount = txn.get("amount", 0.0)
        description = txn.get("original_description", "")
        account = txn.get("account_name", "")

        lines.append(
            f"ID: {txn_id}, Date: {date}, Merchant: {merchant}, Amount: ${amount:.2f}, "
            f"Account: {account}, Description: {description}"
        )
    return "\n".join(lines)


def build_prompt(
    *,
    transactions: Sequence[dict[str, Any]],
    categories: Sequence[str],
) -> str:
    """Build the categorization prompt."""
    tx_section = _format_transactions(transactions)
    categories_section = "\n".join(f"- {item}" for item in categories)

    return f"""You are helping categorize uncategorized transactions from a personal finance database.

## Instructions
- For each transaction, categorize them into a category > subcategory pair
- If possible, use the closest category > subcategory pair from the list of Existing Categories below.
- **Creating New Categories**: When existing categories don't fit well, create new category/subcategory pairs. Common scenarios where you SHOULD create new categories:
  - Obvious missing subcategories that would apply to multiple transactions
  - Don't force transactions into loosely-related categories just to avoid creating new ones
- **IMPORTANT**: We want to minimize how many transactions a user has to manually review, so think hard about how to categorize as many transactions as you can.
- Normalize the merchant name into a clean, human-friendly canonical form (e.g., "AMZN MKTP US" → "Amazon", "STARBUCKS #1234" → "Starbucks").
- Confidence must be between 0 and 1 (use two decimal places: 0.85, 0.95, etc.).
- When you introduce a new category, explain why in the `notes` column.
- Use high confidence (≥0.9) when you're fairly certain about the categorization, including when creating appropriate new categories.
- **IMPORTANT**: Include the transaction ID from the input for each row so we can match your categorization back to the correct transaction.

## Output Format
Return your response as a CSV with EXACTLY this header (no extra text before or after):
transaction_id,canonical_merchant,category,subcategory,confidence,notes

Example:
transaction_id,canonical_merchant,category,subcategory,confidence,notes
123,Amazon,Shopping,Online,0.95,
124,Starbucks,Food & Dining,Coffee,0.98,
125,Target,Shopping,General,0.90,
126,Uber,Transportation,Rideshare,0.92,

## Existing Categories
{categories_section}

## Uncategorized Transactions
{tx_section}
""".strip()


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="JSON file with uncategorized transactions (from fin-query). If omitted, reads from stdin.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Optional path to write the prompt. If omitted, prints to stdout.",
)
def cli(
    input_path: Path | None,
    output_path: Path | None,
) -> None:
    """Build a categorization prompt for uncategorized transactions.

    Example usage:
        fin-query saved uncategorized --format json | python build_prompt.py
        fin-query saved uncategorized --format json > /tmp/uncategorized.json
        python build_prompt.py --input /tmp/uncategorized.json --output /tmp/prompt.txt
    """
    # Load transactions
    if input_path:
        with input_path.open("r", encoding="utf-8") as f:
            transactions = json.load(f)
    else:
        transactions = json.load(sys.stdin)

    if not transactions:
        click.echo("No uncategorized transactions found.", err=True)
        sys.exit(0)

    # Load categories
    categories = _load_categories()

    # Build prompt
    prompt = build_prompt(transactions=transactions, categories=categories)

    # Output
    if output_path:
        output_path.write_text(prompt, encoding="utf-8")
        click.echo(f"Wrote categorization prompt to {output_path}", err=True)
        click.echo(f"Found {len(transactions)} uncategorized transactions.", err=True)
    else:
        click.echo(prompt)


if __name__ == "__main__":
    cli()
