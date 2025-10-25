"""Post-processing helpers for LLM extracted transactions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import click

from fin_cli.shared import models
from fin_cli.shared.merchants import merchant_pattern_key
from fin_cli.shared.config import AppConfig, load_config
from fin_cli.shared.database import connect

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
    source: str = ""  # Track categorization source: llm_extraction, pattern_match, or empty

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
            "source": self.source,
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


def enrich_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    config: AppConfig | None = None,
    connection=None,
    apply_patterns: bool = False,
    verbose: bool = False,
) -> list[EnrichedTransaction]:
    effective_config = config or load_config()
    connection_ctx = None
    if apply_patterns:
        if connection is None:
            connection_ctx = connect(effective_config, read_only=True)
            connection = connection_ctx.__enter__()
        if connection is None:
            raise RuntimeError("apply_patterns=True requires a database connection")

    pattern_cache: dict[str, dict[str, Any] | None] = {}
    enriched: list[EnrichedTransaction] = []
    try:
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

            # Track source of categorization
            source = ""
            should_clear = _should_clear_category(
                category=category,
                subcategory=subcategory,
                confidence=confidence,
                config=effective_config,
            )

            if should_clear:
                if verbose and category:
                    threshold = effective_config.categorization.confidence.auto_approve
                    if confidence < threshold:
                        click.echo(f"  ⚠ Clearing low-confidence LLM category: {merchant} → {category}/{subcategory} (confidence: {confidence:.2f} < {threshold:.2f})")
                    elif category.lower() == "uncategorized":
                        click.echo(f"  ⚠ Clearing generic 'Uncategorized' for: {merchant}")
                category = ""
                subcategory = ""
            elif category:
                # Category provided by LLM and not cleared
                source = "llm_extraction"

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

            if apply_patterns and connection is not None and pattern_key:
                cached = pattern_cache.get(pattern_key)
                if pattern_key not in pattern_cache:
                    db_row = connection.execute(
                        """
                        SELECT mp.confidence, mp.pattern_display, mp.metadata,
                               c.category, c.subcategory
                        FROM merchant_patterns mp
                        JOIN categories c ON c.id = mp.category_id
                        WHERE mp.pattern = ?
                        ORDER BY mp.confidence DESC
                        LIMIT 1
                        """,
                        (pattern_key,),
                    ).fetchone()
                    if db_row:
                        metadata_value: Any = db_row["metadata"]
                        if metadata_value:
                            try:
                                metadata_value = json.loads(metadata_value)
                            except json.JSONDecodeError:
                                pass
                        pattern_cache[pattern_key] = {
                            "category": db_row["category"],
                            "subcategory": db_row["subcategory"],
                            "confidence": float(db_row["confidence"]) if db_row["confidence"] is not None else 1.0,
                            "pattern_display": db_row["pattern_display"],
                            "metadata": metadata_value,
                        }
                    else:
                        pattern_cache[pattern_key] = None
                    cached = pattern_cache[pattern_key]
                if cached:
                    category = cached["category"]
                    subcategory = cached["subcategory"]
                    confidence = float(cached["confidence"]) if cached["confidence"] is not None else confidence
                    source = "pattern_match"
                    display_from_db = cached.get("pattern_display")  # type: ignore[index]
                    if display_from_db:
                        pattern_display = str(display_from_db)
                    elif not pattern_display:
                        pattern_display = merchant
                    if merchant_metadata is None and cached.get("metadata") is not None:  # type: ignore[index]
                        merchant_metadata = cached["metadata"]  # type: ignore[index]
                    if verbose:
                        click.echo(f"  ✓ {merchant} → {category}/{subcategory} (pattern: {pattern_key}, confidence: {confidence:.2f})")
                elif verbose:
                    click.echo(f"  ○ No pattern match for: {merchant} (pattern_key: {pattern_key})")

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
                    source=source,
                )
            )
    finally:
        if connection_ctx is not None:
            connection_ctx.__exit__(None, None, None)
    return enriched


def _repair_csv_formatting(path: Path) -> Path:
    """Auto-repair common CSV formatting issues like unescaped commas.

    Returns the path to the repaired CSV (creates a backup if repairs were needed).
    """
    import tempfile

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        lines = f.readlines()

    if not lines:
        return path

    # Parse header to determine expected field count
    header = lines[0].strip().split(',')
    expected_fields = len(header)

    repairs_needed = False
    repaired_lines = [lines[0]]  # Keep header as-is

    for line_num, line in enumerate(lines[1:], start=2):
        raw_line = line.strip()
        if not raw_line:
            continue

        # Quick check: count fields with simple split
        fields = raw_line.split(',')

        if len(fields) == expected_fields:
            # No issue, keep as-is
            repaired_lines.append(line)
        elif len(fields) == expected_fields + 1:
            # Likely one unescaped comma - merge fields 4 and 5 (original_description)
            # This is the most common case: "SQ *K&J ORCHARDS, LLC" becomes two fields
            click.echo(
                f"  ⚠ Line {line_num}: Auto-repairing unescaped comma "
                f"(merging fields 4-5 in original_description)",
                err=True
            )
            repairs_needed = True

            # Merge the split fields and re-quote
            fixed_fields = fields[:3] + [f'"{fields[3]},{fields[4]}"'] + fields[5:]
            repaired_lines.append(','.join(fixed_fields) + '\n')
        else:
            # Complex issue - log warning but keep original
            click.echo(
                f"  ⚠ Line {line_num}: Expected {expected_fields} fields, got {len(fields)}. "
                f"Cannot auto-repair - please fix manually.",
                err=True
            )
            repaired_lines.append(line)

    if not repairs_needed:
        return path

    # Create backup and write repaired version
    backup_path = path.with_suffix(path.suffix + '.backup')
    import shutil
    shutil.copy2(path, backup_path)
    click.echo(f"  ℹ Created backup: {backup_path}", err=True)

    with path.open("w", encoding="utf-8", newline="") as f:
        f.writelines(repaired_lines)

    click.echo(f"  ✓ Repaired CSV written to: {path}", err=True)
    return path


def _read_csv(path: Path) -> list[dict[str, object]]:
    # Auto-repair CSV formatting issues before parsing
    repaired_path = _repair_csv_formatting(path)

    with repaired_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _write_csv(path: Path, rows: Sequence[EnrichedTransaction]) -> None:
    fieldnames = list(_REQUIRED_COLUMNS) + [
        "account_key",
        "fingerprint",
        "pattern_key",
        "pattern_display",
        "merchant_metadata",
        "source",
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
@click.option(
    "--apply-patterns",
    is_flag=True,
    help="Use existing merchant_patterns to fill category/confidence before export.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show detailed logging for pattern matches and categorization decisions.",
)
def cli(
    input_path: Path | None,
    output_path: Path | None,
    output_dir: Path | None,
    stdout: bool,
    workdir: Path | None,
    apply_patterns: bool,
    verbose: bool,
) -> None:
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

    config = load_config()
    connection_ctx = None
    connection = None
    if apply_patterns:
        connection_ctx = connect(config, read_only=True)
        connection = connection_ctx.__enter__()

    try:
        for candidate in inputs:
            rows = _read_csv(candidate)
            if verbose:
                click.echo(f"\nProcessing {candidate.name}...")
            enriched = enrich_rows(
                rows,
                config=config,
                connection=connection,
                apply_patterns=apply_patterns,
                verbose=verbose,
            )

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
                    "source",
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
    finally:
        if connection_ctx is not None:
            connection_ctx.__exit__(None, None, None)


if __name__ == "__main__":  # pragma: no cover
    cli()
