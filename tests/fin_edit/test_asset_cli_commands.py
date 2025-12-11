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


def test_asset_import_autoclassifies_instruments(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()
    fixture = FIXTURE_ROOT / "ubs_statement.json"

    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "asset-import", "--from", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT i.symbol, ac.main_class, ac.sub_class
            FROM instrument_classifications ic
            JOIN instruments i ON i.id = ic.instrument_id
            JOIN asset_classes ac ON ac.id = ic.asset_class_id
            ORDER BY i.symbol
            """
        ).fetchall()

        mapping = {(row["symbol"], row["main_class"], row["sub_class"]) for row in rows}
        assert ("UBS-SWEEP", "cash", "cash sweep") in mapping
        assert ("AAPL", "equities", "US equity") in mapping

    # Re-run import to ensure classifications remain idempotent
    result = runner.invoke(
        edit_cli,
        ["--db", str(db_path), "--apply", "asset-import", "--from", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        count_after_rerun = connection.execute(
            "SELECT COUNT(*) FROM instrument_classifications"
        ).fetchone()[0]
        assert count_after_rerun == len(mapping)


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


def test_holdings_transfer_preview(tmp_path: Path) -> None:
    """Test holdings-transfer command in preview mode."""
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()

    # Setup: create source and destination accounts, instrument, and holding
    with connect(load_config(env=env)) as connection:
        # Add destination account
        connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?)",
            ("Schwab-IRA", "Schwab", "brokerage"),
        )
        # Add instrument
        connection.execute(
            "INSERT INTO instruments (name, symbol, currency, vehicle_type) VALUES (?, ?, ?, ?)",
            ("Salesforce, Inc.", "CRM", "USD", "stock"),
        )
        # Add holding at source account
        connection.execute(
            """INSERT INTO holdings
               (account_id, instrument_id, status, position_side, cost_basis_total)
               VALUES (1, 1, 'active', 'long', 50000.00)"""
        )

    # Preview transfer (no --apply)
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "holdings-transfer",
            "--symbol",
            "CRM",
            "--from",
            "UBS-INV-001",
            "--to",
            "Schwab-IRA",
            "--carry-cost-basis",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    assert "Transfer Preview:" in result.output
    assert "CRM" in result.output
    assert "UBS-INV-001" in result.output
    assert "Schwab-IRA" in result.output
    assert "Use --apply to execute" in result.output

    # Verify nothing changed
    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        source = connection.execute(
            "SELECT status FROM holdings WHERE account_id = 1 AND instrument_id = 1"
        ).fetchone()
        assert source["status"] == "active"

        dest = connection.execute("SELECT COUNT(*) FROM holdings WHERE account_id = 2").fetchone()[
            0
        ]
        assert dest == 0


def test_holdings_transfer_apply(tmp_path: Path) -> None:
    """Test holdings-transfer command with --apply."""
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()

    # Setup
    with connect(load_config(env=env)) as connection:
        connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?)",
            ("Schwab-IRA", "Schwab", "brokerage"),
        )
        connection.execute(
            "INSERT INTO instruments (name, symbol, currency, vehicle_type) VALUES (?, ?, ?, ?)",
            ("Salesforce, Inc.", "CRM", "USD", "stock"),
        )
        connection.execute(
            """INSERT INTO holdings
               (account_id, instrument_id, status, position_side, cost_basis_total, cost_basis_method)
               VALUES (1, 1, 'active', 'long', 50000.00, 'FIFO')"""
        )

    # Execute transfer
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "holdings-transfer",
            "--symbol",
            "CRM",
            "--from",
            "UBS-INV-001",
            "--to",
            "Schwab-IRA",
            "--transfer-date",
            "2025-12-01",
            "--carry-cost-basis",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    assert "Transferred CRM" in result.output

    # Verify changes
    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        # Source holding should be closed
        source = connection.execute(
            "SELECT status, closed_at FROM holdings WHERE account_id = 1 AND instrument_id = 1"
        ).fetchone()
        assert source["status"] == "closed"
        assert source["closed_at"] == "2025-12-01"

        # Destination holding should be created
        dest = connection.execute(
            """SELECT status, opened_at, cost_basis_total, cost_basis_method, position_side
               FROM holdings WHERE account_id = 2 AND instrument_id = 1"""
        ).fetchone()
        assert dest["status"] == "active"
        assert dest["opened_at"] == "2025-12-01"
        assert dest["cost_basis_total"] == 50000.00
        assert dest["cost_basis_method"] == "FIFO"
        assert dest["position_side"] == "long"


def test_holdings_transfer_without_cost_basis(tmp_path: Path) -> None:
    """Test holdings-transfer without carrying cost basis."""
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()

    with connect(load_config(env=env)) as connection:
        connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?)",
            ("Schwab-IRA", "Schwab", "brokerage"),
        )
        connection.execute(
            "INSERT INTO instruments (name, symbol, currency) VALUES (?, ?, ?)",
            ("Test Stock", "TEST", "USD"),
        )
        connection.execute(
            """INSERT INTO holdings
               (account_id, instrument_id, status, position_side, cost_basis_total)
               VALUES (1, 1, 'active', 'long', 25000.00)"""
        )

    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "holdings-transfer",
            "--symbol",
            "TEST",
            "--from",
            "UBS-INV-001",
            "--to",
            "Schwab-IRA",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        dest = connection.execute(
            "SELECT cost_basis_total FROM holdings WHERE account_id = 2"
        ).fetchone()
        assert dest["cost_basis_total"] is None


def test_holdings_transfer_errors(tmp_path: Path) -> None:
    """Test holdings-transfer error cases."""
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()

    # Error: instrument not found
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "holdings-transfer",
            "--symbol",
            "NOTFOUND",
            "--from",
            "UBS-INV-001",
            "--to",
            "UBS-INV-001",  # Use same account to avoid account error
        ],
        env=env,
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()

    # Setup instrument and destination account, but no holding
    with connect(load_config(env=env)) as connection:
        connection.execute(
            "INSERT INTO instruments (name, symbol, currency) VALUES (?, ?, ?)",
            ("Test", "TEST", "USD"),
        )
        connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?)",
            ("Schwab-IRA", "Schwab", "brokerage"),
        )

    # Error: no active holding at source
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "holdings-transfer",
            "--symbol",
            "TEST",
            "--from",
            "UBS-INV-001",
            "--to",
            "Schwab-IRA",
        ],
        env=env,
    )
    assert result.exit_code != 0
    assert "no active holding" in result.output.lower()

    # Error: destination account not found
    with connect(load_config(env=env)) as connection:
        connection.execute(
            "INSERT INTO holdings (account_id, instrument_id, status, position_side) VALUES (1, 1, 'active', 'long')"
        )

    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "holdings-transfer",
            "--symbol",
            "TEST",
            "--from",
            "UBS-INV-001",
            "--to",
            "NonexistentAccount",
        ],
        env=env,
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
