"""Post-processing helpers for LLM extracted transactions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import click

from fin_cli.shared import models
from fin_cli.shared.merchants import merchant_pattern_key
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
    pattern_key: str | None = None
    pattern_display: str | None = None
    merchant_metadata: Mapping[str, object] | str | None = None

    def as_dict(self) -> dict[str, object]:
        metadata_value: str = ""
        if isinstance(self.merchant_metadata, Mapping):
            metadata_value = json.dumps(self.merchant_metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        elif isinstance(self.merchant_metadata, str):
            metadata_value = self.merchant_metadata
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
            "pattern_key": self.pattern_key or "",
            "pattern_display": self.pattern_display or "",
            "merchant_metadata": metadata_value,
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
        pattern_key = str(row.get("pattern_key") or "").strip()
        if not pattern_key:
            pattern_key = merchant_pattern_key(merchant) or ""
        pattern_display = str(row.get("pattern_display") or "").strip()
        if not pattern_display and pattern_key:
            pattern_display = merchant

        merchant_metadata: Mapping[str, object] | str | None = None
        raw_metadata = row.get("merchant_metadata")
        if raw_metadata is not None:
            metadata_text = str(raw_metadata).strip()
            if metadata_text:
                try:
                    merchant_metadata = json.loads(metadata_text)
                except json.JSONDecodeError:
                    merchant_metadata = metadata_text

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
                pattern_key=pattern_key or None,
                pattern_display=pattern_display or None,
                merchant_metadata=merchant_metadata,
            )
        )
    return enriched


def _read_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _write_csv(path: Path, rows: Sequence[EnrichedTransaction]) -> None:
    fieldnames = list(_REQUIRED_COLUMNS) + [
        "account_key",
        "fingerprint",
        "pattern_key",
        "pattern_display",
        "merchant_metadata",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for txn in rows:
            writer.writerow(txn.as_dict())


@click.command()
@click.option("--input", "input_path", type=click.Path(path_type=Path, exists=True, dir_okay=False), required=False)
@click.option("--output", "output_path", type=click.Path(path_type=Path, dir_okay=False), help="Optional destination for enriched CSV.")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    help="Directory where enriched CSVs should be written using auto-generated filenames.",
)
@click.option("--stdout", is_flag=True, help="Emit enriched CSV to stdout instead of writing a file.")
@click.option(
    "--workdir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Statement-processor workspace root (from bootstrap.sh). Processes all LLM CSVs when --input is omitted.",
)
def cli(input_path: Path | None, output_path: Path | None, output_dir: Path | None, stdout: bool, workdir: Path | None) -> None:
    """Enrich LLM CSV output with account_key and fingerprint columns."""

    if output_path and output_dir:
        raise click.UsageError("Specify either --output or --output-dir, not both.")
    if stdout and (output_path or output_dir):
        raise click.UsageError("Use either --stdout or file output options, not both.")

    resolved_workdir: Path | None = None
    inputs: list[Path]
    if workdir is not None:
        resolved_workdir = workdir.expanduser().resolve()
        if not resolved_workdir.exists():
            raise click.ClickException(f"Workspace {resolved_workdir} does not exist. Run bootstrap.sh first.")
        if input_path is None:
            llm_dir = resolved_workdir / "llm"
            inputs = sorted(llm_dir.glob("*.csv"))
            if not inputs:
                raise click.ClickException(f"No LLM CSV files found under {llm_dir}.")
        else:
            inputs = [input_path]
        if output_path is None and output_dir is None and not stdout:
            output_dir = resolved_workdir
    else:
        if input_path is None:
            raise click.UsageError("--input is required unless --workdir is provided.")
        inputs = [input_path]

    if stdout and len(inputs) > 1:
        raise click.UsageError("--stdout can only be used with a single input file.")
    if output_path and len(inputs) > 1:
        raise click.UsageError("--output can only be used with a single input file.")

    for candidate in inputs:
        rows = _read_csv(candidate)
        enriched = enrich_rows(rows)

        effective_output_path = output_path
        if output_dir is not None:
            target_dir = output_dir / "enriched"
            target_dir.mkdir(parents=True, exist_ok=True)
            effective_output_path = target_dir / _derive_enriched_filename(candidate)

        if stdout:
            stdout_fieldnames = list(_REQUIRED_COLUMNS) + [
                "account_key",
                "fingerprint",
                "pattern_key",
                "pattern_display",
                "merchant_metadata",
            ]
            writer = csv.DictWriter(click.get_text_stream("stdout"), fieldnames=stdout_fieldnames)
            writer.writeheader()
            for txn in enriched:
                writer.writerow(txn.as_dict())
        else:
            destination = effective_output_path or candidate.with_name(_derive_enriched_filename(candidate))
            _write_csv(destination, enriched)
            click.echo(f"Wrote enriched CSV to {destination}")

        if stdout:
            # Only one file allowed when stdout is true; loop will end immediately.
            break


if __name__ == "__main__":  # pragma: no cover
    cli()
