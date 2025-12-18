from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from click.testing import CliRunner

from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations
from fin_cli.shared.utils import compute_file_sha256

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "asset-tracker"
    / "scripts"
    / "postprocess.py"
)
spec = importlib.util.spec_from_file_location("asset_tracker_postprocess", MODULE_PATH)
postprocess = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = postprocess
spec.loader.exec_module(postprocess)


def _prepare_config(tmp_path: Path):
    db_path = tmp_path / "asset-tracker-postprocess.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    return config, env


def _minimal_payload(*, account_key: str, symbol: str) -> dict:
    return {
        "document": {
            "broker": "UBS",
            "as_of_date": "2025-12-01",
        },
        "instruments": [
            {
                "name": "Sweep Fund",
                "symbol": symbol,
                "currency": "USD",
                "vehicle_type": "MMF",
                "identifiers": {"fund_id": "sweep"},
            }
        ],
        "holdings": [{"account_key": account_key, "symbol": symbol, "status": "active"}],
        "holding_values": [
            {
                "account_key": account_key,
                "symbol": symbol,
                "as_of_date": "2025-12-01",
                "quantity": 1.0,
                "price": 1.0,
                "market_value": 1.0,
                "source": "statement",
            }
        ],
    }


def test_enrich_payload_sets_document_hash_and_source_file_hash(tmp_path: Path) -> None:
    config, _env = _prepare_config(tmp_path)

    scrubbed = tmp_path / "statement-scrubbed.txt"
    scrubbed.write_text(
        "# SOURCE_FILE_HASH: original-pdf-sha\nHoldings section...", encoding="utf-8"
    )
    expected_hash = compute_file_sha256(scrubbed)

    payload = _minimal_payload(account_key="UBS-INV-001", symbol="UBS-SWEEP")
    enriched = postprocess.enrich_payload(payload, document_path=scrubbed, config=config)

    doc = enriched["document"]
    assert doc["document_hash"] == expected_hash
    assert doc["file_path"] == str(scrubbed)
    assert doc["source_file_hash"] == "original-pdf-sha"

    value = enriched["holding_values"][0]
    assert value["document_hash"] == expected_hash


def test_enrich_payload_auto_classifies_instruments(tmp_path: Path) -> None:
    config, _env = _prepare_config(tmp_path)
    payload = _minimal_payload(account_key="UBS-INV-001", symbol="UBS-SWEEP")

    enriched = postprocess.enrich_payload(payload, config=config, auto_classify=True)
    metadata = enriched["instruments"][0]["metadata"]
    assert metadata["auto_class"]["main"] == "cash"
    assert metadata["auto_class"]["sub"] == "cash sweep"


def test_detect_potential_transfers_flags_existing_holdings(tmp_path: Path) -> None:
    config, _env = _prepare_config(tmp_path)

    with connect(config) as connection:
        source_account_id = int(
            connection.execute(
                "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?) RETURNING id",
                ("UBS-INV-001", "UBS", "brokerage"),
            ).fetchone()["id"]
        )
        instrument_id = int(
            connection.execute(
                "INSERT INTO instruments (name, symbol, exchange, currency, vehicle_type) VALUES (?, ?, ?, ?, ?) RETURNING id",
                ("Salesforce, Inc.", "CRM", "NYSE", "USD", "stock"),
            ).fetchone()["id"]
        )
        holding_id = int(
            connection.execute(
                "INSERT INTO holdings (account_id, instrument_id, status) VALUES (?, ?, 'active') RETURNING id",
                (source_account_id, instrument_id),
            ).fetchone()["id"]
        )

    payload = {
        "document": {"document_hash": "doc", "broker": "Schwab", "as_of_date": "2025-12-01"},
        "instruments": [
            {
                "name": "Salesforce, Inc.",
                "symbol": "CRM",
                "currency": "USD",
                "vehicle_type": "stock",
                "identifiers": {"cusip": "79466L302"},
            }
        ],
        "holdings": [{"account_key": "Schwab-IRA", "symbol": "CRM", "status": "active"}],
        "holding_values": [
            {
                "account_key": "Schwab-IRA",
                "symbol": "CRM",
                "as_of_date": "2025-12-01",
                "quantity": 1.0,
                "price": 100.0,
                "market_value": 100.0,
                "source": "statement",
                "document_hash": "doc",
            }
        ],
    }

    transfers = postprocess.detect_potential_transfers(payload, config=config)
    assert len(transfers) == 1
    transfer = transfers[0]
    assert transfer["symbol"] == "CRM"
    assert transfer["existing_account"] == "UBS-INV-001"
    assert transfer["existing_holding_id"] == holding_id
    assert transfer["new_accounts"] == ["Schwab-IRA"]


def test_cli_workdir_discovers_inputs_and_writes_enriched_json(tmp_path: Path) -> None:
    _config, env = _prepare_config(tmp_path)

    workdir = tmp_path / "workspace"
    workdir.mkdir(parents=True, exist_ok=True)

    raw_json = _minimal_payload(account_key="UBS-INV-001", symbol="UBS-SWEEP")
    input_path = workdir / "demo-raw.json"
    input_path.write_text(json.dumps(raw_json, indent=2), encoding="utf-8")

    doc_path = workdir / "demo-scrubbed.txt"
    doc_path.write_text(
        "# SOURCE_FILE_HASH: original-pdf-sha\nHoldings section...", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(
        postprocess.cli,
        [
            "--workdir",
            str(workdir),
            "--no-detect-transfers",
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    output_path = workdir / "demo-enriched.json"
    assert output_path.exists()
    enriched = json.loads(output_path.read_text(encoding="utf-8"))
    assert enriched["document"]["source_file_hash"] == "original-pdf-sha"
