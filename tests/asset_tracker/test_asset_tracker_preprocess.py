from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from click.testing import CliRunner

from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "asset-tracker"
    / "scripts"
    / "preprocess.py"
)
spec = importlib.util.spec_from_file_location("asset_tracker_preprocess", MODULE_PATH)
preprocess = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = preprocess
spec.loader.exec_module(preprocess)


def _prepare_config(tmp_path: Path):
    db_path = tmp_path / "asset-tracker-preprocess.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    return config, env


def _seed_instrument(config) -> None:
    with connect(config) as connection:
        connection.execute(
            """
            INSERT INTO instruments (name, symbol, exchange, currency, vehicle_type, identifiers)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("Apple Inc", "AAPL", "NASDAQ", "USD", "stock", None),
        )


def test_build_prompt_includes_taxonomy_and_existing_instruments(tmp_path: Path) -> None:
    config, _env = _prepare_config(tmp_path)
    _seed_instrument(config)

    prompt = preprocess.build_prompt(
        "Holdings section...\nAAPL 10 shares",
        label="ubs-demo",
        config=config,
        max_instruments=10,
    )

    assert "Asset Class Taxonomy" in prompt
    assert "equities | US equity" in prompt
    assert "- AAPL: Apple Inc (stock)" in prompt
    assert "## ubs-demo" in prompt
    assert "AAPL 10 shares" in prompt


def test_cli_emit_json_returns_taxonomy_payload(tmp_path: Path) -> None:
    config, env = _prepare_config(tmp_path)
    _seed_instrument(config)

    input_path = tmp_path / "ubs-scrubbed.txt"
    input_path.write_text("Header\nHoldings section...\nAAPL 10 shares", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        preprocess.cli,
        ["--input", str(input_path), "--emit-json", "--max-instruments", "10"],
        env=env,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload.keys()) == {"asset_classes", "existing_instruments"}
    assert payload["asset_classes"], "seeded taxonomy should be present"
    symbols = {item["symbol"] for item in payload["existing_instruments"]}
    assert "AAPL" in symbols


def test_cli_workdir_discovers_scrubbed_input_and_writes_prompt(tmp_path: Path) -> None:
    _, env = _prepare_config(tmp_path)

    workdir = tmp_path / "workspace"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "demo-scrubbed.txt").write_text("Header\nHoldings section...", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        preprocess.cli,
        ["--workdir", str(workdir)],
        env=env,
    )

    assert result.exit_code == 0, result.output
    output_path = workdir / "demo-prompt.txt"
    assert output_path.exists()
    prompt = output_path.read_text(encoding="utf-8")
    assert "## demo" in prompt


def test_cli_workdir_rejects_multiple_scrubbed_inputs(tmp_path: Path) -> None:
    _, env = _prepare_config(tmp_path)

    workdir = tmp_path / "workspace"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "demo-1-scrubbed.txt").write_text("Header\nHoldings section...", encoding="utf-8")
    (workdir / "demo-2-scrubbed.txt").write_text("Header\nHoldings section...", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        preprocess.cli,
        ["--workdir", str(workdir)],
        env=env,
    )

    assert result.exit_code != 0
    assert "Multiple scrubbed statements found" in result.output
