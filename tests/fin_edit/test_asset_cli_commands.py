from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_edit.main import main as edit_cli
from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "asset_tracking"


def _setup_db(tmp_path: Path):
    db_path = tmp_path / "asset-cli.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    with connect(config) as connection:
        connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?)",
            ("UBS-INV-001", "UBS", "brokerage"),
        )
    return db_path, env


def test_instruments_and_holding_values_upsert(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()
    fixture = FIXTURE_ROOT / "ubs_statement.json"

    # Upsert instruments first
    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "instruments-upsert", "--from", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    # Upsert holding values (also ensures holdings/documents)
    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "holding-values-upsert", "--from", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        symbols = {
            row[0] for row in connection.execute("SELECT symbol FROM instruments").fetchall()
        }
        assert symbols >= {"AAPL", "ACWI", "UBS-SWEEP"}

        holding_rows = connection.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
        assert holding_rows == 3

        hv_count = connection.execute("SELECT COUNT(*) FROM holding_values").fetchone()[0]
        assert hv_count == 3

        doc_row = connection.execute("SELECT document_hash FROM documents").fetchone()
        assert doc_row is not None and doc_row[0] == "ubs-2024-12-31-demo-hash"

    # Re-run upsert to ensure idempotence via ON CONFLICT
    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "holding-values-upsert", "--from", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output
    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        hv_count_again = connection.execute("SELECT COUNT(*) FROM holding_values").fetchone()[0]
    assert hv_count_again == 3


def test_holding_values_validation_and_derivation(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()

    payload = {
        "instruments": [
            {"name": "Test Bond", "symbol": "TBND", "currency": "usd", "vehicle_type": "bond"}
        ],
        "holding_values": [
            {
                "account_key": "UBS-INV-001",
                "symbol": "TBND",
                "as_of_date": "2025-01-31",
                "quantity": 10,
                "market_value": 200.0,
                "source": "manual",
            }
        ],
    }
    payload_path = tmp_path / "hv_payload.json"
    payload_path.write_text(__import__("json").dumps(payload))

    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "holding-values-upsert", "--from", str(payload_path)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        row = connection.execute(
            """
            SELECT hv.price, hv.market_value
            FROM holding_values hv
            JOIN holdings h ON h.id = hv.holding_id
            JOIN instruments i ON i.id = h.instrument_id
            WHERE i.symbol = 'TBND'
            """
        ).fetchone()
        # price should have been derived as 20.0
        assert row is not None
        assert row["price"] == 20.0
        assert row["market_value"] == 200.0

    # Invalid: missing price/market_value and bad currency
    bad_payload = {
        "instruments": [
            {"name": "Bad", "symbol": "BAD", "currency": "US", "vehicle_type": "stock"}
        ],
        "holding_values": [
            {
                "account_key": "UBS-INV-001",
                "symbol": "BAD",
                "as_of_date": "2025-01-31",
                "quantity": 5,
                "source": "statement",
            }
        ],
    }
    bad_path = tmp_path / "hv_bad.json"
    bad_path.write_text(__import__("json").dumps(bad_payload))
    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "holding-values-upsert", "--from", str(bad_path)],
        env=env,
    )
    assert result.exit_code != 0


def test_asset_import_wrapper(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()
    fixture = FIXTURE_ROOT / "schwab_statement.json"

    with connect(load_config(env=env)) as connection:
        connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?)",
            ("SCHWAB-IRA-2024", "Schwab", "IRA"),
        )

    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "asset-import", "--from", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        hv_count = connection.execute("SELECT COUNT(*) FROM holding_values").fetchone()[0]
        assert hv_count == 3
        doc_hash = connection.execute("SELECT document_hash FROM documents").fetchone()[0]
        assert doc_hash == "schwab-2025-01-15-demo-hash"


def test_holdings_add_and_deactivate(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()
    # Seed instrument directly into DB
    with connect(load_config(env=env)) as connection:
        connection.execute(
            "INSERT INTO instruments (name, symbol, currency) VALUES (?, ?, ?)",
            ("Test Equity", "TEST", "USD"),
        )

    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "holdings-add",
            "--account-id",
            "1",
            "--instrument-symbol",
            "TEST",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        holding_id = connection.execute(
            "SELECT id FROM holdings WHERE instrument_id = 1"
        ).fetchone()[0]

    # Deactivate
    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "holdings-deactivate", "--holding-id", str(holding_id)],
        env=env,
    )
    assert result.exit_code == 0, result.output
    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        status = connection.execute(
            "SELECT status FROM holdings WHERE id = ?", (holding_id,)
        ).fetchone()[0]
        assert status == "closed"


def test_documents_register_and_delete(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "documents-register",
            "--hash",
            "doc-hash-123",
            "--source",
            "Manual Entry",
            "--source-type",
            "manual",
            "--priority",
            "2",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        doc_id = connection.execute(
            "SELECT id FROM documents WHERE document_hash = ?", ("doc-hash-123",)
        ).fetchone()[0]
        assert doc_id

    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "documents-delete", "--hash", "doc-hash-123"],
        env=env,
    )
    assert result.exit_code == 0, result.output
    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        remaining = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        assert remaining == 0
