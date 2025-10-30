"""Build a categorization prompt for uncategorized transactions."""

from __future__ import annotations

import csv
import json
from io import StringIO
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

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


def _coerce_amount(value: Any) -> float:
    """Convert the amount field to a float for prompt formatting."""
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    try:
        return float(str(value).strip().replace("$", ""))
    except (TypeError, ValueError):
        return 0.0


def _normalise_transaction(txn: Mapping[str, Any]) -> dict[str, Any]:
    """Ensure transaction fields are ready for prompt rendering."""
    record = dict(txn)
    record["amount"] = _coerce_amount(record.get("amount"))
    return record


def _parse_csv(content: str) -> list[dict[str, Any]]:
    """Parse CSV content into a list of transaction dicts."""
    reader = csv.DictReader(StringIO(content))
    rows: list[dict[str, Any]] = []
    for row in reader:
        if not row:
            continue
        if not any(value.strip() for value in row.values() if isinstance(value, str)):
            continue
        rows.append(_normalise_transaction(row))
    return rows


def _parse_json(content: str) -> list[dict[str, Any]]:
    """Parse JSON content into a list of transaction dicts."""
    payload = json.loads(content)
    transactions: list[Mapping[str, Any]]
    if isinstance(payload, list):
        transactions = payload  # type: ignore[assignment]
    elif isinstance(payload, Mapping):
        # Handle fin-query's structured output formats
        if "rows" in payload and "columns" in payload:
            columns = payload["columns"]
            rows = payload["rows"]
            transactions = [dict(zip(columns, row)) for row in rows]
        else:
            raise click.ClickException("Unsupported JSON structure for transactions.")
    else:
        raise click.ClickException("Unsupported JSON payload for transactions.")

    return [_normalise_transaction(txn) for txn in transactions]


def _load_transactions_from_source(data: str, hint: str | None = None) -> list[dict[str, Any]]:
    """Load transactions from serialized CSV or JSON data."""
    stripped = data.lstrip()
    if not stripped:
        return []
    if hint and hint.lower().endswith(".csv"):
        return _parse_csv(data)
    if hint and hint.lower().endswith(".json"):
        return _parse_json(data)
    if stripped[0] in ("{", "["):
        return _parse_json(data)
    return _parse_csv(data)


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
- Use high confidence (≥0.75) when you're fairly certain about the categorization, including when creating appropriate new categories.
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
    help="CSV or JSON file with uncategorized transactions (from fin-query). If omitted, reads from stdin.",
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
        fin-query saved uncategorized --format csv --limit 500 | python build_prompt.py
        fin-query saved uncategorized --format csv --limit 500 > /tmp/uncategorized.csv
        python build_prompt.py --input /tmp/uncategorized.csv --output /tmp/prompt.txt
    """
    # Load transactions
    if input_path:
        raw = input_path.read_text(encoding="utf-8")
        transactions = _load_transactions_from_source(raw, hint=input_path.suffix)
    else:
        raw = sys.stdin.read()
        transactions = _load_transactions_from_source(raw)

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
