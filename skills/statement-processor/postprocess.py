"""Post-processing helpers for LLM extracted transactions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

import click

from fin_cli.shared import models

_REQUIRED_COLUMNS = (
    "date",
    "merchant",
    "amount",
    "original_description",
    "account_name",
    "institution",
    "account_type",
    "category",
    "subcategory",
    "confidence",
)


@dataclass(slots=True)
class EnrichedTransaction:
    date: str
    merchant: str
    amount: float
    original_description: str
    account_name: str
    institution: str
    account_type: str
    category: str
    subcategory: str
    confidence: float
    account_key: str
    fingerprint: str

    def as_dict(self) -> dict[str, object]:
        return {
            "date": self.date,
            "merchant": self.merchant,
            "amount": f"{self.amount:.2f}",
            "original_description": self.original_description,
            "account_name": self.account_name,
            "institution": self.institution,
            "account_type": self.account_type,
            "category": self.category,
            "subcategory": self.subcategory,
            "confidence": f"{self.confidence:.4f}",
            "account_key": self.account_key,
            "fingerprint": self.fingerprint,
        }


def _normalise_merchant(value: str) -> str:
    return " ".join(value.strip().split())


def _normalise_description(value: str) -> str:
    return value.strip()


def _parse_amount(raw: object) -> float:
    if raw is None:
        raise ValueError("amount is required")
    text = str(raw).strip()
    if not text:
        raise ValueError("amount is required")
    amount = float(text)
    if amount < 0:
        amount = -amount
    return amount


def _parse_confidence(raw: object) -> float:
    if raw is None or str(raw).strip() == "":
        return 0.0
    value = float(str(raw))
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def _coerce_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{key} is required")
    return text


def enrich_rows(rows: Iterable[Mapping[str, object]]) -> list[EnrichedTransaction]:
    enriched: list[EnrichedTransaction] = []
    for row in rows:
        for column in _REQUIRED_COLUMNS:
            if column not in row:
                raise KeyError(f"Missing required column '{column}' in LLM output")

        date_text = _coerce_str(row, "date")
        date_obj = datetime.strptime(date_text, "%Y-%m-%d").date()
        merchant = _normalise_merchant(_coerce_str(row, "merchant"))
        original_description = _normalise_description(_coerce_str(row, "original_description"))
        amount = _parse_amount(row.get("amount"))
        account_name = _coerce_str(row, "account_name")
        institution = _coerce_str(row, "institution")
        account_type = _coerce_str(row, "account_type").lower()
        category = _coerce_str(row, "category")
        subcategory = _coerce_str(row, "subcategory")
        confidence = _parse_confidence(row.get("confidence"))

        account_key = models.compute_account_key(account_name, institution, account_type)
        fingerprint = models.compute_transaction_fingerprint(
            date_obj,
            amount,
            merchant,
            None,
            account_key,
        )

        enriched.append(
            EnrichedTransaction(
                date=date_text,
                merchant=merchant,
                amount=amount,
                original_description=original_description,
                account_name=account_name,
                institution=institution,
                account_type=account_type,
                category=category,
                subcategory=subcategory,
                confidence=confidence,
                account_key=account_key,
                fingerprint=fingerprint,
            )
        )
    return enriched


def _read_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _write_csv(path: Path, rows: Sequence[EnrichedTransaction]) -> None:
    fieldnames = list(_REQUIRED_COLUMNS) + ["account_key", "fingerprint"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for txn in rows:
            writer.writerow(txn.as_dict())


@click.command()
@click.option("--input", "input_path", type=click.Path(path_type=Path, exists=True, dir_okay=False), required=True)
@click.option("--output", "output_path", type=click.Path(path_type=Path, dir_okay=False), help="Optional destination for enriched CSV.")
@click.option("--stdout", is_flag=True, help="Emit enriched CSV to stdout instead of writing a file.")
def cli(input_path: Path, output_path: Path | None, stdout: bool) -> None:
    """Enrich LLM CSV output with account_key and fingerprint columns."""

    if stdout and output_path is not None:
        raise click.UsageError("Use either --stdout or --output, not both.")

    rows = _read_csv(input_path)
    enriched = enrich_rows(rows)

    if stdout:
        writer = csv.DictWriter(click.get_text_stream("stdout"), fieldnames=list(_REQUIRED_COLUMNS) + ["account_key", "fingerprint"])
        writer.writeheader()
        for txn in enriched:
            writer.writerow(txn.as_dict())
    else:
        destination = output_path or input_path.with_name(f"{input_path.stem}-enriched.csv")
        _write_csv(destination, enriched)
        click.echo(f"Wrote enriched CSV to {destination}")


if __name__ == "__main__":  # pragma: no cover
    cli()
