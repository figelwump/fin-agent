from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

from fin_cli.fin_query import executor
from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations

# Helpers to seed a minimal asset-tracking dataset for saved query tests.
# The dataset includes multiple sources to verify source precedence rules,
# classifications for allocation math, and an intentionally unclassified
# instrument to exercise gap-detection queries.


def _config(tmp_path: Path):
    db_path = tmp_path / "asset-query.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    return config


def _get_source_id(connection, name: str, source_type: str, priority: int) -> int:
    row = connection.execute(
        "SELECT id FROM asset_sources WHERE name = ?",
        (name,),
    ).fetchone()
    if row:
        return int(row["id"])
    row = connection.execute(
        "INSERT INTO asset_sources (name, source_type, priority) VALUES (?, ?, ?) RETURNING id",
        (name, source_type, priority),
    ).fetchone()
    return int(row["id"])


def _asset_class_id(connection, main: str, sub: str) -> int:
    row = connection.execute(
        "SELECT id FROM asset_classes WHERE main_class = ? AND sub_class = ?",
        (main, sub),
    ).fetchone()
    if not row:
        raise AssertionError(f"Missing asset class {main}/{sub} in seed data")
    return int(row["id"])


def _insert_instrument(
    connection,
    *,
    name: str,
    symbol: str,
    vehicle_type: str | None,
    currency: str = "USD",
    exchange: str | None = None,
    classification: tuple[str, str] | None = None,
    identifiers: dict | None = None,
) -> int:
    identifiers_json = json.dumps(identifiers or {}) or None
    row = connection.execute(
        """
        INSERT INTO instruments (name, symbol, exchange, currency, vehicle_type, identifiers)
        VALUES (?, ?, ?, ?, ?, ?) RETURNING id
        """,
        (name, symbol, exchange, currency, vehicle_type, identifiers_json),
    ).fetchone()
    instrument_id = int(row["id"])
    if classification:
        class_id = _asset_class_id(connection, *classification)
        connection.execute(
            "INSERT INTO instrument_classifications (instrument_id, asset_class_id, is_primary) VALUES (?, ?, 1)",
            (instrument_id, class_id),
        )
    return instrument_id


def _insert_holding(
    connection, account_id: int, instrument_id: int, *, status: str = "active"
) -> int:
    row = connection.execute(
        """
        INSERT INTO holdings (account_id, instrument_id, status)
        VALUES (?, ?, ?) RETURNING id
        """,
        (account_id, instrument_id, status),
    ).fetchone()
    return int(row["id"])


def _insert_holding_value(
    connection,
    *,
    holding_id: int,
    as_of_date: str,
    quantity: float,
    price: float,
    market_value: float,
    source_id: int,
    document_id: int | None,
    valuation_currency: str = "USD",
    fx_rate_used: float = 1.0,
    as_of_datetime: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO holding_values (
            holding_id, as_of_date, as_of_datetime, quantity, price, market_value,
            source_id, document_id, valuation_currency, fx_rate_used
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            holding_id,
            as_of_date,
            as_of_datetime,
            quantity,
            price,
            market_value,
            source_id,
            document_id,
            valuation_currency,
            fx_rate_used,
        ),
    )


def _seed_asset_portfolio(config):
    totals = {}
    with connect(config) as connection:
        stmt_source = _get_source_id(connection, "Statement Import", "statement", 1)
        api_source = _get_source_id(connection, "API Sync", "api", 3)

        account_id = int(
            connection.execute(
                "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?) RETURNING id",
                ("Primary Brokerage", "UBS", "brokerage"),
            ).fetchone()["id"]
        )

        doc_row = connection.execute(
            """
            INSERT INTO documents (document_hash, source_id, broker, period_end_date)
            VALUES (?, ?, ?, ?) RETURNING id
            """,
            ("asset-test-doc-hash", stmt_source, "UBS", date(2025, 12, 5).isoformat()),
        ).fetchone()
        document_id = int(doc_row["id"])

        aapl_id = _insert_instrument(
            connection,
            name="Apple Inc",
            symbol="AAPL",
            exchange="NASDAQ",
            currency="USD",
            vehicle_type="stock",
            classification=("equities", "US equity"),
            identifiers={"cusip": "037833100"},
        )
        bnd_id = _insert_instrument(
            connection,
            name="Vanguard Total Bond Market ETF",
            symbol="BND",
            exchange="NYSEARCA",
            currency="USD",
            vehicle_type="ETF",
            classification=("bonds", "corporate IG"),
            identifiers={"isin": "US9219378356"},
        )
        sweep_id = _insert_instrument(
            connection,
            name="Sweep Fund",
            symbol="SWVXX",
            exchange=None,
            currency="USD",
            vehicle_type="MMF",
            classification=("cash", "money market"),
            identifiers={"fund_id": "sweep"},
        )
        unknown_id = _insert_instrument(
            connection,
            name="Private Note",
            symbol="PN-001",
            exchange=None,
            currency="USD",
            vehicle_type="note",
            classification=None,
            identifiers={"note_id": "pn-test"},
        )

        aapl_holding = _insert_holding(connection, account_id, aapl_id)
        bnd_holding = _insert_holding(connection, account_id, bnd_id)
        sweep_holding = _insert_holding(connection, account_id, sweep_id)
        unknown_holding = _insert_holding(connection, account_id, unknown_id)

        # AAPL: API is newer date but lower priority; latest should prefer statement row.
        _insert_holding_value(
            connection,
            holding_id=aapl_holding,
            as_of_date="2025-12-01",
            quantity=10.0,
            price=190.0,
            market_value=1900.0,
            source_id=stmt_source,
            document_id=document_id,
        )
        _insert_holding_value(
            connection,
            holding_id=aapl_holding,
            as_of_date="2025-12-02",
            quantity=10.0,
            price=191.0,
            market_value=1910.0,
            source_id=api_source,
            document_id=None,
        )
        totals["AAPL"] = 1900.0

        # BND: two statement rows; latest date should win and feed history query.
        _insert_holding_value(
            connection,
            holding_id=bnd_holding,
            as_of_date="2025-11-15",
            quantity=88.0,
            price=79.0,
            market_value=6952.0,
            source_id=stmt_source,
            document_id=document_id,
        )
        _insert_holding_value(
            connection,
            holding_id=bnd_holding,
            as_of_date="2025-12-03",
            quantity=90.0,
            price=80.0,
            market_value=7200.0,
            source_id=stmt_source,
            document_id=document_id,
        )
        totals["BND"] = 7200.0

        _insert_holding_value(
            connection,
            holding_id=sweep_holding,
            as_of_date="2025-12-01",
            quantity=3000.0,
            price=1.0,
            market_value=3000.0,
            source_id=stmt_source,
            document_id=document_id,
        )
        totals["SWVXX"] = 3000.0

        _insert_holding_value(
            connection,
            holding_id=unknown_holding,
            as_of_date="2020-01-01",
            quantity=200.0,
            price=1.0,
            market_value=200.0,
            source_id=stmt_source,
            document_id=document_id,
        )
        totals["PN-001"] = 200.0

    return {
        "account_id": account_id,
        "document_id": document_id,
        "document_hash": "asset-test-doc-hash",
        "holdings": {
            "AAPL": aapl_holding,
            "BND": bnd_holding,
            "SWVXX": sweep_holding,
            "PN-001": unknown_holding,
        },
        "totals": totals,
    }


def test_holding_latest_values_respects_source_priority(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_asset_portfolio(config)

    result = executor.run_saved_query(
        config=config,
        name="holding_latest_values",
        runtime_params={},
        limit=20,
    )

    symbol_idx = result.columns.index("symbol")
    price_idx = result.columns.index("price")
    market_idx = result.columns.index("market_value")
    source_idx = result.columns.index("source_name")

    rows_by_symbol = {row[symbol_idx]: row for row in result.rows}
    assert rows_by_symbol.keys() >= {"AAPL", "BND", "SWVXX", "PN-001"}

    # Statement (priority 1) should beat newer API (priority 3).
    assert rows_by_symbol["AAPL"][price_idx] == 190.0
    assert rows_by_symbol["AAPL"][market_idx] == 1900.0
    assert rows_by_symbol["AAPL"][source_idx] == "Statement Import"

    # Latest date wins within same source.
    assert rows_by_symbol["BND"][price_idx] == 80.0
    assert rows_by_symbol["BND"][market_idx] == 7200.0


def test_portfolio_snapshot_includes_classes_and_fx(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_asset_portfolio(config)

    result = executor.run_saved_query(
        config=config,
        name="portfolio_snapshot",
        runtime_params={"as_of_date": None, "account_id": None},
        limit=20,
    )

    symbol_idx = result.columns.index("symbol")
    main_idx = result.columns.index("main_class")
    sub_idx = result.columns.index("sub_class")
    fx_idx = result.columns.index("fx_rate_used")

    rows = {row[symbol_idx]: row for row in result.rows}
    assert rows["AAPL"][main_idx] == "equities"
    assert rows["AAPL"][sub_idx] == "US equity"
    assert rows["BND"][main_idx] == "bonds"
    assert rows["SWVXX"][main_idx] == "cash"
    assert rows["PN-001"][main_idx] is None
    assert all(rows[symbol][fx_idx] == 1.0 for symbol in rows)


def test_allocation_by_class_calculates_percentages(tmp_path: Path) -> None:
    config = _config(tmp_path)
    seeded = _seed_asset_portfolio(config)

    result = executor.run_saved_query(
        config=config,
        name="allocation_by_class",
        runtime_params={"as_of_date": None, "account_id": None},
        limit=10,
    )

    main_idx = result.columns.index("main_class")
    sub_idx = result.columns.index("sub_class")
    total_idx = result.columns.index("total_value")
    pct_idx = result.columns.index("allocation_pct")

    expected_totals = {
        ("equities", "US equity"): seeded["totals"]["AAPL"],
        ("bonds", "corporate IG"): seeded["totals"]["BND"],
        ("cash", "money market"): seeded["totals"]["SWVXX"],
        ("unclassified", "unknown"): seeded["totals"]["PN-001"],
    }
    seen = {}
    for row in result.rows:
        key = (row[main_idx], row[sub_idx])
        seen[key] = row
        assert math.isclose(row[total_idx], expected_totals[key], rel_tol=1e-6)

    assert set(seen.keys()) == set(expected_totals.keys())
    total_allocation = sum(row[pct_idx] for row in result.rows)
    assert math.isclose(total_allocation, 100.0, rel_tol=1e-3, abs_tol=0.05)


def test_allocation_by_account_returns_total_weight(tmp_path: Path) -> None:
    config = _config(tmp_path)
    seeded = _seed_asset_portfolio(config)

    result = executor.run_saved_query(
        config=config,
        name="allocation_by_account",
        runtime_params={"as_of_date": None},
        limit=5,
    )

    total_idx = result.columns.index("total_value")
    pct_idx = result.columns.index("allocation_pct")
    account_idx = result.columns.index("account_id")

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row[account_idx] == seeded["account_id"]
    assert math.isclose(row[total_idx], sum(seeded["totals"].values()), rel_tol=1e-6)
    assert row[pct_idx] == 100.0


def test_stale_holdings_flags_old_positions(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_asset_portfolio(config)

    result = executor.run_saved_query(
        config=config,
        name="stale_holdings",
        runtime_params={"days": 30},
        limit=10,
    )

    symbol_idx = result.columns.index("symbol")
    symbols = {row[symbol_idx] for row in result.rows}
    assert symbols == {"PN-001"}


def test_holding_history_orders_by_date_and_documents(tmp_path: Path) -> None:
    config = _config(tmp_path)
    seeded = _seed_asset_portfolio(config)

    result = executor.run_saved_query(
        config=config,
        name="holding_history",
        runtime_params={"holding_id": seeded["holdings"]["BND"]},
        limit=5,
    )

    as_of_idx = result.columns.index("as_of_date")
    doc_idx = result.columns.index("document_hash")
    assert [row[as_of_idx] for row in result.rows][:2] == ["2025-12-03", "2025-11-15"]
    assert all(row[doc_idx] == "asset-test-doc-hash" for row in result.rows)


def test_holdings_missing_classification_lists_unmapped_instruments(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_asset_portfolio(config)

    result = executor.run_saved_query(
        config=config,
        name="holdings_missing_classification",
        runtime_params={},
        limit=10,
    )

    symbol_idx = result.columns.index("symbol")
    assert [row[symbol_idx] for row in result.rows] == ["PN-001"]
