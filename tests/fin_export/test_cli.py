from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_export.main import cli as export_cli


def _invoke(args: list[str]) -> tuple[int, str]:
    runner = CliRunner()
    result = runner.invoke(export_cli, args)
    return result.exit_code, result.output


def test_markdown_report_includes_sections(load_analysis_dataset, app_config) -> None:
    load_analysis_dataset("spending_multi_year")
    exit_code, output = _invoke(
        [
            "--db",
            str(app_config.database.path),
            "--month",
            "2025-08",
        ]
    )
    assert exit_code == 0, output
    assert "## Summary" in output
    assert "Spending by Category" in output
    assert "Top Merchants" in output


def test_markdown_report_handles_empty_subscriptions(load_analysis_dataset, app_config) -> None:
    load_analysis_dataset("sparse")
    exit_code, output = _invoke(
        [
            "--db",
            str(app_config.database.path),
            "--month",
            "2025-08",
        ]
    )
    assert exit_code == 0, output
    assert "## Active Subscriptions" in output
    assert "- No subscriptions matched the configured filters." in output


def test_json_report_structure(load_analysis_dataset, app_config) -> None:
    load_analysis_dataset("spending_multi_year")
    exit_code, output = _invoke(
        [
            "--db",
            str(app_config.database.path),
            "--month",
            "2025-08",
            "--sections",
            "summary,categories",
            "--format",
            "json",
        ]
    )
    assert exit_code == 0, output
    payload = json.loads(output)
    assert payload["version"] == "1.0"
    summary = payload["sections"]["summary"]
    assert "metrics" in summary["payload"]
    assert summary["payload"]["comparison"] is not None
    categories = payload["sections"].get("categories")
    assert categories is not None
    assert categories["tables"][0]["columns"]


def test_invalid_section_errors(app_config) -> None:
    exit_code, output = _invoke(
        [
            "--db",
            str(app_config.database.path),
            "--sections",
            "made-up",
        ]
    )
    assert exit_code != 0
    assert "Unknown section" in output


def test_output_path_infers_format(load_analysis_dataset, app_config, tmp_path: Path) -> None:
    load_analysis_dataset("spending_multi_year")
    output_path = tmp_path / "report.json"
    exit_code, _ = _invoke(
        [
            "--db",
            str(app_config.database.path),
            "--month",
            "2025-08",
            "--output",
            str(output_path),
            "--sections",
            "summary",
        ]
    )
    assert exit_code == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text())
    assert payload["sections"]["summary"]["payload"]["metrics"]["total_spent"] >= 0
