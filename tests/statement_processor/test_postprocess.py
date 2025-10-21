from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from click.testing import CliRunner

from fin_cli.shared import models

MODULE_PATH = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "statement-processor" / "postprocess.py"
_spec = importlib.util.spec_from_file_location("statement_processor_postprocess", MODULE_PATH)
postprocess = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = postprocess
_spec.loader.exec_module(postprocess)


def _sample_row() -> Dict[str, Any]:
    return {
        "date": "2025-09-15",
        "merchant": "  AMAZON  ",
        "amount": "45.67",
        "original_description": " AMZN Mktp US*7X51S5QT3 ",
        "account_name": "Chase Prime Visa",
        "institution": "Chase",
        "account_type": "Credit",
        "category": "Shopping",
        "subcategory": "Online Retail",
        "confidence": "0.95",
    }


def test_enrich_rows_computes_hashes(tmp_path: Path) -> None:
    enriched = postprocess.enrich_rows([_sample_row()])

    assert len(enriched) == 1
    txn = enriched[0]
    expected_account_key = models.compute_account_key("Chase Prime Visa", "Chase", "credit")
    assert txn.account_key == expected_account_key
    assert txn.merchant == "AMAZON"

    expected_fingerprint = models.compute_transaction_fingerprint(
        datetime.strptime("2025-09-15", "%Y-%m-%d").date(),
        45.67,
        "AMAZON",
        None,
        expected_account_key,
    )
    assert txn.fingerprint == expected_fingerprint
    assert txn.confidence == 0.95


def test_enrich_rows_clears_low_confidence_uncategorized(tmp_path: Path) -> None:
    row = _sample_row()
    row["category"] = "Uncategorized"
    row["subcategory"] = "Other"
    row["confidence"] = "0.6"

    enriched = postprocess.enrich_rows([row])
    assert enriched[0].category == ""
    assert enriched[0].subcategory == ""
    assert enriched[0].confidence == 0.6


def test_cli_writes_enriched_csv(tmp_path: Path) -> None:
    input_path = tmp_path / "llm.csv"
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(postprocess._REQUIRED_COLUMNS))  # type: ignore[attr-defined]
        writer.writeheader()
        writer.writerow(_sample_row())

    runner = CliRunner()
    output_path = tmp_path / "llm-enriched.csv"
    result = runner.invoke(
        postprocess.cli,
        ["--input", str(input_path), "--output", str(output_path)],
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    contents = output_path.read_text(encoding="utf-8")
    assert "account_key" in contents
    assert "fingerprint" in contents


def test_cli_output_dir_creates_enriched(tmp_path: Path) -> None:
    input_path = tmp_path / "batch-1-llm.csv"
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(postprocess._REQUIRED_COLUMNS))  # type: ignore[attr-defined]
        writer.writeheader()
        writer.writerow(_sample_row())

    runner = CliRunner()
    workdir = tmp_path / "workspace"
    result = runner.invoke(
        postprocess.cli,
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(workdir),
        ],
    )

    assert result.exit_code == 0, result.output
    enriched_path = workdir / "enriched" / "batch-1-enriched.csv"
    assert enriched_path.exists()


def test_cli_workdir_processes_all(tmp_path: Path) -> None:
    workdir = tmp_path / "workspace"
    llm_dir = workdir / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)

    for name in ("batch-1-llm.csv", "batch-2-llm.csv"):
        with (llm_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(postprocess._REQUIRED_COLUMNS))  # type: ignore[attr-defined]
            writer.writeheader()
            writer.writerow(_sample_row())

    runner = CliRunner()
    result = runner.invoke(
        postprocess.cli,
        [
            "--workdir",
            str(workdir),
        ],
    )

    assert result.exit_code == 0, result.output
    enriched_dir = workdir / "enriched"
    outputs = sorted(enriched_dir.glob("*-enriched.csv"))
    assert len(outputs) == 2
