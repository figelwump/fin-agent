from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

from click.testing import CliRunner

from fin_cli.shared import models, paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "statement-processor"
    / "scripts"
    / "categorize_leftovers.py"
)
spec = importlib.util.spec_from_file_location("categorize_leftovers", MODULE_PATH)
categorize = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = categorize  # type: ignore[index]
spec.loader.exec_module(categorize)  # type: ignore[attr-defined]


def _prepare_db(tmp_path: Path) -> dict[str, str]:
    db_path = tmp_path / "db.sqlite"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    with connect(config) as connection:
        models.get_or_create_category(
            connection,
            category="Food & Dining",
            subcategory="Coffee",
            auto_generated=False,
            user_approved=True,
        )
        models.get_or_create_category(
            connection,
            category="Shopping",
            subcategory="Online",
            auto_generated=False,
            user_approved=True,
        )
    return env


def _write_enriched(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
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
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_cli_builds_prompt(tmp_path: Path) -> None:
    env = _prepare_db(tmp_path)

    csv_path = tmp_path / "leftovers.csv"
    _write_enriched(
        csv_path,
        [
            {
                "date": "2025-09-15",
                "merchant": "AMZN Mktp US",
                "amount": "45.67",
                "original_description": "AMZN Mktp US*7X51S5QT3",
                "account_name": "Chase Prime Visa",
                "institution": "Chase",
                "account_type": "credit",
                "category": "",
                "subcategory": "",
                "confidence": "0.20",
            }
        ],
    )

    runner = CliRunner()
    output_path = tmp_path / "prompt.txt"
    result = runner.invoke(
        categorize.cli,
        ["--input", str(csv_path), "--output", str(output_path)],
        env=env,
    )

    assert result.exit_code == 0, result.output
    prompt = output_path.read_text(encoding="utf-8")
    assert "categorization LLM" in prompt
    assert "AMZN Mktp US" in prompt
    assert "Food & Dining > Coffee" in prompt or "Shopping > Online" in prompt


def test_cli_no_leftovers(tmp_path: Path) -> None:
    env = _prepare_db(tmp_path)
    csv_path = tmp_path / "clean.csv"
    _write_enriched(
        csv_path,
        [
            {
                "date": "2025-09-15",
                "merchant": "Coffee Shop",
                "amount": "5.50",
                "original_description": "COFFEE SHOP",
                "account_name": "Chase Prime Visa",
                "institution": "Chase",
                "account_type": "credit",
                "category": "Food & Dining",
                "subcategory": "Coffee",
                "confidence": "0.95",
            }
        ],
    )

    runner = CliRunner()
    result = runner.invoke(categorize.cli, ["--input", str(csv_path)], env=env)

    assert result.exit_code == 0, result.output
    assert "No uncategorized transactions" in result.output
