from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from fin_cli.fin_analyze.main import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _invoke_cli(runner: CliRunner, args: list[str]) -> tuple[int, str]:
    result = runner.invoke(main, args)
    return result.exit_code, result.output


def test_cli_outputs_json(load_analysis_dataset, app_config, runner) -> None:
    load_analysis_dataset("spending_multi_year")
    exit_code, output = _invoke_cli(
        runner,
        [
            "merchant-frequency",
            "--month",
            "2025-08",
            "--format",
            "json",
            "--db",
            str(app_config.database.path),
            "--min-visits",
            "1",
        ],
    )
    assert exit_code == 0, output
    payload = json.loads(output)
    assert payload["title"] == "Merchant Frequency"
    merchants = {entry["canonical"] for entry in payload["payload"]["merchants"]}
    assert "AMAZON" in merchants


def test_cli_renders_text(load_analysis_dataset, app_config, runner) -> None:
    load_analysis_dataset("spending_multi_year")
    exit_code, output = _invoke_cli(
        runner,
        [
            "spending-patterns",
            "--month",
            "2025-08",
            "--db",
            str(app_config.database.path),
            "--by",
            "day",
        ],
    )
    assert exit_code == 0, output
    assert "Spending Patterns" in output
    assert "Tuesday" in output


def test_cli_category_timeline_with_period(load_analysis_dataset, app_config, runner) -> None:
    load_analysis_dataset("spending_multi_year")
    exit_code, output = _invoke_cli(
        runner,
        [
            "category-timeline",
            "--period",
            "6m",
            "--format",
            "json",
            "--db",
            str(app_config.database.path),
            "--category",
            "Shopping",
            "--include-merchants",
            "--top-n",
            "3",
        ],
    )
    assert exit_code == 0, output
    payload = json.loads(output)["payload"]
    assert payload["interval"] == "month"
    assert payload["filter"] == {"category": "Shopping", "subcategory": None}
    assert payload["metadata"]["top_n"] == 3
    assert "merchants" in payload and "AMAZON" in payload["merchants"]["canonical"]


def test_cli_merchant_frequency_category_filter(load_analysis_dataset, app_config, runner) -> None:
    load_analysis_dataset("spending_multi_year")
    exit_code, output = _invoke_cli(
        runner,
        [
            "merchant-frequency",
            "--month",
            "2025-08",
            "--format",
            "json",
            "--db",
            str(app_config.database.path),
            "--category",
            "Shopping",
        ],
    )
    assert exit_code == 0, output
    payload = json.loads(output)["payload"]
    assert payload.get("filter") == {"category": "Shopping", "subcategory": None}
    merchants = {entry["canonical"] for entry in payload["merchants"]}
    assert "AMAZON" in merchants


def test_cli_errors_on_unknown_analyzer(app_config, runner) -> None:
    exit_code, output = _invoke_cli(
        runner,
        [
            "made-up",
            "--month",
            "2025-08",
            "--db",
            str(app_config.database.path),
        ],
    )
    assert exit_code != 0
    assert "Unknown analysis type" in output


def test_cli_year_option_uses_calendar_window(load_analysis_dataset, app_config, runner) -> None:
    load_analysis_dataset("spending_multi_year")
    exit_code, output = _invoke_cli(
        runner,
        [
            "spending-trends",
            "--year",
            "2024",
            "--format",
            "json",
            "--db",
            str(app_config.database.path),
        ],
    )
    assert exit_code == 0, output
    payload = json.loads(output)["payload"]
    assert payload["window"]["label"] == "calendar_year_2024"


def test_cli_last_12_months_window(monkeypatch, load_analysis_dataset, app_config, runner) -> None:
    load_analysis_dataset("spending_multi_year")

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            tz = tz or timezone.utc
            return datetime(2025, 9, 30, tzinfo=tz)

    monkeypatch.setattr("fin_cli.fin_analyze.temporal.datetime", FixedDateTime)

    exit_code, output = _invoke_cli(
        runner,
        [
            "spending-trends",
            "--last-12-months",
            "--format",
            "json",
            "--db",
            str(app_config.database.path),
        ],
    )
    assert exit_code == 0, output
    payload = json.loads(output)["payload"]
    assert payload["window"]["label"].startswith("last_12_months_2024_09")
    assert payload["window"]["end"] == "2025-09-01"


def test_cli_period_all_window(load_analysis_dataset, app_config, runner) -> None:
    load_analysis_dataset("spending_multi_year")
    exit_code, output = _invoke_cli(
        runner,
        [
            "category-breakdown",
            "--period",
            "all",
            "--format",
            "json",
            "--db",
            str(app_config.database.path),
        ],
    )
    assert exit_code == 0, output
    payload = json.loads(output)["payload"]
    window = payload["window"]
    assert window["label"].startswith("period_all_")
    assert window["start"] <= window["end"]
    assert payload["categories"], "Expected categorized spend records for dataset"


def test_cli_period_all_empty_dataset(load_analysis_dataset, app_config, runner) -> None:
    load_analysis_dataset("empty")
    exit_code, output = _invoke_cli(
        runner,
        [
            "category-breakdown",
            "--period",
            "all",
            "--format",
            "json",
            "--db",
            str(app_config.database.path),
        ],
    )
    assert exit_code != 0
    assert "No categorized spend" in output
    assert "24m" in output
