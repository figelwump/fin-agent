from __future__ import annotations

import hashlib
import json
from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_extract.main import main as extract_cli
from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "asset_tracking"


def _setup_db(tmp_path: Path):
    db_path = tmp_path / "asset-extract.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    with connect(config) as connection:
        connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?)",
            ("UBS-INV-001", "UBS", "brokerage"),
        )
    return db_path, env


def test_asset_json_validate_only(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()
    fixture = FIXTURE_ROOT / "ubs_statement.json"

    result = runner.invoke(
        extract_cli,
        ["--db", str(db_path), "asset-json", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    # No imports when --apply not passed
    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        hv_count = connection.execute("SELECT COUNT(*) FROM holding_values").fetchone()[0]
        assert hv_count == 0


def test_asset_json_apply_imports(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()
    fixture = FIXTURE_ROOT / "ubs_statement.json"

    result = runner.invoke(
        extract_cli,
        ["--db", str(db_path), "asset-json", "--apply", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        hv_count = connection.execute("SELECT COUNT(*) FROM holding_values").fetchone()[0]
        assert hv_count == 3
        doc_hash = connection.execute("SELECT document_hash FROM documents").fetchone()[0]
        assert doc_hash == "ubs-2024-12-31-demo-hash"


def test_asset_json_computes_hash_when_missing(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()

    statement_path = tmp_path / "ubs_demo.pdf"
    statement_bytes = b"fake ubs statement contents"
    statement_path.write_bytes(statement_bytes)
    expected_hash = hashlib.sha256(statement_bytes).hexdigest()

    payload = {
        "document": {"broker": "UBS", "as_of_date": "2024-12-31"},
        "instruments": [
            {
                "name": "Hash Test Equity",
                "symbol": "HASH",
                "currency": "USD",
                "vehicle_type": "stock",
            }
        ],
        "holdings": [{"account_key": "UBS-INV-001", "symbol": "HASH", "status": "active"}],
        "holding_values": [
            {
                "account_key": "UBS-INV-001",
                "symbol": "HASH",
                "as_of_date": "2024-12-31",
                "quantity": 5,
                "price": 10.0,
                "source": "statement",
            }
        ],
    }

    payload_path = tmp_path / "asset_payload.json"
    payload_path.write_text(json.dumps(payload))

    result = runner.invoke(
        extract_cli,
        [
            "--db",
            str(db_path),
            "asset-json",
            "--apply",
            "--document-path",
            str(statement_path),
            str(payload_path),
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        doc_row = connection.execute("SELECT document_hash, file_path FROM documents").fetchone()
        assert doc_row is not None
        assert doc_row["document_hash"] == expected_hash
        assert Path(doc_row["file_path"]).name == statement_path.name

        hv_doc_ids = connection.execute(
            "SELECT COUNT(*) FROM holding_values WHERE document_id IS NOT NULL"
        ).fetchone()[0]
        assert hv_doc_ids == 1

        hv_doc_hashes = {
            row[0]
            for row in connection.execute(
                """
                SELECT d.document_hash
                FROM holding_values hv
                JOIN documents d ON d.id = hv.document_id
                """
            ).fetchall()
        }
        assert hv_doc_hashes == {expected_hash}
