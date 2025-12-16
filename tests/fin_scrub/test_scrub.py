from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from click.testing import CliRunner

fin_scrub_module = importlib.import_module("fin_cli.fin_scrub.main")
from fin_cli.fin_scrub.main import main as fin_scrub_cli

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "scrubbed"


def _reset_default_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ensure tests don't read user-specific configs."""

    monkeypatch.setattr(fin_scrub_module, "USER_CONFIG_PATH", tmp_path / "fin-scrub.yaml")
    config = fin_scrub_module._load_default_config()
    fin_scrub_module._configure_runtime(config)
    monkeypatch.setattr(fin_scrub_module, "_apply_scrubadub", lambda text, stats: text)


def test_scrub_text_redacts_common_patterns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reset_default_runtime(monkeypatch, tmp_path)
    raw_text = (FIXTURE_DIR / "sample_raw_statement.txt").read_text(encoding="utf-8")

    stats = fin_scrub_module.ScrubStats()
    scrubbed = fin_scrub_module._scrub_text(raw_text, stats)

    assert "[NAME]" in scrubbed
    assert "[ADDRESS]" in scrubbed
    assert "[EMAIL]" in scrubbed
    assert "[URL]" in scrubbed
    assert "[ROUTING_NUMBER]" in scrubbed
    assert "[ACCOUNT_NUMBER]" in scrubbed
    assert "[CARD_NUMBER_LAST4:1111]" in scrubbed
    assert "[ACCOUNT_LAST4:4242]" in scrubbed
    assert "John Smith" not in scrubbed
    assert "john.q.smith@example.com" not in scrubbed
    assert "https://examplebank.com/profile" not in scrubbed
    # Transactions should remain untouched for downstream parsers.
    assert "09/01 Coffee Shop        -5.45" in scrubbed

    # Confirm stats recorded key replacements.
    assert stats.counts["CARD_NUMBER"] == 1
    assert stats.counts["ACCOUNT_NUMBER"] == 1
    assert stats.counts["ROUTING_NUMBER"] == 1
    assert stats.counts.get("NAME", 0) >= 1


def test_cli_writes_scrubbed_output_and_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reset_default_runtime(monkeypatch, tmp_path)
    input_path = tmp_path / "statement.txt"
    input_path.write_text((FIXTURE_DIR / "sample_raw_statement.txt").read_text(encoding="utf-8"))
    output_dir = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        fin_scrub_cli,
        [
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--report",
        ],
    )

    assert result.exit_code == 0, result.output
    scrubbed_files = list(output_dir.glob("*-scrubbed.txt"))
    assert len(scrubbed_files) == 1
    scrubbed_text = scrubbed_files[0].read_text(encoding="utf-8")
    assert "[CARD_NUMBER_LAST4:1111]" in scrubbed_text
    assert "[EMAIL]" in scrubbed_text
    assert "John Smith" not in scrubbed_text
    assert "Redaction counts:" in (result.stderr or "")


def test_cli_missing_input_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _reset_default_runtime(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(fin_scrub_cli, [])

    assert result.exit_code != 0
    assert "Provide an input" in result.output


def test_cli_config_override_disables_name_scrubbing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reset_default_runtime(monkeypatch, tmp_path)
    config_path = tmp_path / "custom.yaml"
    config_path.write_text(
        'detectors:\n  scrub_name: false\nplaceholders:\n  EMAIL: "[MASKED_EMAIL]"\n',
        encoding="utf-8",
    )
    input_path = tmp_path / "statement.txt"
    input_path.write_text((FIXTURE_DIR / "sample_raw_statement.txt").read_text(encoding="utf-8"))

    runner = CliRunner()
    result = runner.invoke(
        fin_scrub_cli,
        [
            str(input_path),
            "--stdout",
            "--report",
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "John Smith" in result.output
    assert "[MASKED_EMAIL]" in result.output
    assert "[NAME]" not in result.output
    assert "NAME:" not in (result.stderr or "")
