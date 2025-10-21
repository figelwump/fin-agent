"""Post-processing helpers for LLM extracted transactions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

import click

from fin_cli.shared import models
from fin_cli.shared.config import AppConfig, load_config

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


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    slug = slug.strip("-_")
    return slug or "statement"


def _strip_suffix(value: str, suffix: str) -> str:
    if value.endswith(suffix):
        return value[: -len(suffix)]
    return value


def _derive_enriched_filename(source: Path | None) -> str:
    base = source.stem if source is not None else "llm-output"
    base = base.rstrip("-_ ")
    base = _strip_suffix(base, "-llm")
    base = _strip_suffix(base, "-raw")
    base = _strip_suffix(base, "-enriched")
    slug = _slugify(base)
    return f"{slug}-enriched.csv"


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


def _coerce_str(data: Mapping[str, object], key: str, *, allow_empty: bool = False) -> str:
    value = data.get(key)
    if value is None:
        raise ValueError(f"{key} is required")
    text = str(value).strip()
    if not text and not allow_empty:
        raise ValueError(f"{key} is required")
    return text


def _should_clear_category(
    *,
    category: str,
    subcategory: str,
    confidence: float,
    config: AppConfig,
) -> bool:
    """
    Determine whether the LLM-provided category should be cleared.

    We strip categories when:
    - The confidence is below the auto-approval threshold (default 0.8). In this case we want the
      downstream review flow to surface the transaction for manual verification instead of silently
      applying a guess.
    - The category was set to the generic "Uncategorized" placeholder, which conveys no real signal.
    """

    threshold = config.categorization.confidence.auto_approve
    if confidence < threshold:
        return True

    if category.lower() == "uncategorized":
        return True

    return False


def enrich_rows(rows: Iterable[Mapping[str, object]], *, config: AppConfig | None = None) -> list[EnrichedTransaction]:
    effective_config = config or load_config()
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
        category = _coerce_str(row, "category", allow_empty=True)
        subcategory = _coerce_str(row, "subcategory", allow_empty=True)
        confidence = _parse_confidence(row.get("confidence"))

        if _should_clear_category(
            category=category,
            subcategory=subcategory,
            confidence=confidence,
            config=effective_config,
        ):
            category = ""
            subcategory = ""

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
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    help="Directory where enriched CSVs should be written using auto-generated filenames.",
)
@click.option("--stdout", is_flag=True, help="Emit enriched CSV to stdout instead of writing a file.")
def cli(input_path: Path, output_path: Path | None, output_dir: Path | None, stdout: bool) -> None:
    """Enrich LLM CSV output with account_key and fingerprint columns."""

    if output_path and output_dir:
        raise click.UsageError("Specify either --output or --output-dir, not both.")
    if stdout and (output_path or output_dir):
        raise click.UsageError("Use either --stdout or file output options, not both.")

    rows = _read_csv(input_path)
    enriched = enrich_rows(rows)

    if output_dir is not None:
        target_dir = output_dir / "enriched"
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / _derive_enriched_filename(input_path)

    if stdout:
        writer = csv.DictWriter(click.get_text_stream("stdout"), fieldnames=list(_REQUIRED_COLUMNS) + ["account_key", "fingerprint"])
        writer.writeheader()
        for txn in enriched:
            writer.writerow(txn.as_dict())
    else:
        destination = output_path or input_path.with_name(_derive_enriched_filename(input_path))
        _write_csv(destination, enriched)
        click.echo(f"Wrote enriched CSV to {destination}")


if __name__ == "__main__":  # pragma: no cover
    cli()
