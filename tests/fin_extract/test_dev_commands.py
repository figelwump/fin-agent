from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_extract.main import main


def _base_env(tmp_path: Path) -> dict[str, str]:
    return {
        "FINCLI_CONFIG_DIR": str(tmp_path / "config"),
        "FINCLI_PLUGIN_DIR": str(tmp_path / "plugins"),
    }


def _strip_ansi(value: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", value)


def test_dev_list_plugins_shows_bundled_and_builtin(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["dev", "list-plugins"], env=_base_env(tmp_path))

    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "Registered extractors:" in clean
    assert "built-in python" in clean
    assert "bundled yaml" in clean


def test_dev_validate_spec_reports_success(tmp_path: Path) -> None:
    spec_path = Path(__file__).resolve().parent.parent.parent / "fin_cli" / "fin_extract" / "bundled_specs" / "chase.yaml"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["dev", "validate-spec", str(spec_path)],
        env=_base_env(tmp_path),
    )

    assert result.exit_code == 0
    clean = _strip_ansi(result.output)
    assert "Spec 'chase' loaded successfully" in clean
    assert "override" in clean  # warning about collision with existing extractor
