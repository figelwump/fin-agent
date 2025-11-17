from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pytest

from fin_cli.fin_query import executor
from fin_cli.fin_query.types import QueryResult
from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations
from fin_cli.shared.exceptions import QueryError


def _config(tmp_path) -> tuple[str, Mapping[str, str]]:
    db_path = tmp_path / "fin_query.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    return config, env


def _seed_transactions(config) -> None:
    with connect(config) as connection:
        account_id = connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?) RETURNING id",
            ("Primary", "TestBank", "checking"),
        ).fetchone()[0]
        groceries_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Food & Dining", "Groceries"),
        ).fetchone()[0]
        shopping_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Shopping", "Online"),
        ).fetchone()[0]
        entertainment_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Entertainment", "Comedy"),
        ).fetchone()[0]
        rows = [
            (
                date(2025, 8, 1).isoformat(),
                "Amazon",
                -42.10,
                shopping_id,
                account_id,
                "AMAZON MKTPLACE",
                "2025-09-01T09:30:00",
                0.9,
                "rule:pattern",
                "2025-08-01--42.10-Amazon",
            ),
            (
                date(2025, 8, 2).isoformat(),
                "Whole Foods",
                -115.55,
                groceries_id,
                account_id,
                "WHOLEFDS 123",
                "2025-09-02T10:15:00",
                1.0,
                "review:manual",
                "2025-08-02--115.55-WholeFoods",
            ),
            (
                date(2025, 9, 3).isoformat(),
                "Amazon",
                -19.99,
                shopping_id,
                account_id,
                "AMAZON MKTPLACE",
                "2025-09-15T08:45:00",
                0.8,
                "rule:pattern",
                "2025-09-03--19.99-Amazon",
            ),
            (
                date(2025, 7, 15).isoformat(),
                "Comedy Cellar",
                -75.00,
                entertainment_id,
                account_id,
                "COMEDY CELLAR NYC",
                "2025-07-16T20:15:00",
                0.95,
                "review:manual",
                "2025-07-15--75.00-ComedyCellar",
            ),
        ]
        connection.executemany(
            """
            INSERT INTO transactions (
                date, merchant, amount, category_id, account_id, original_description,
                import_date, categorization_confidence, categorization_method, fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        connection.execute(
            """
            INSERT INTO merchant_patterns (pattern, category_id, confidence, usage_count)
            VALUES (?, ?, ?, ?)
            """,
            ("AMAZON", shopping_id, 0.9, 12),
        )


def test_execute_sql_applies_limit(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.execute_sql(
        config=config,
        query="SELECT merchant FROM transactions ORDER BY date",
        params={},
        limit=1,
    )

    assert isinstance(result, QueryResult)
    assert result.limit_applied is True
    assert result.limit_value == 1
    assert result.truncated is True
    assert result.rows == [("Comedy Cellar",)]


def test_run_saved_query_requires_params(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    with pytest.raises(QueryError):
        executor.run_saved_query(config=config, name="category_summary", runtime_params={})


def test_run_saved_query_success(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.run_saved_query(
        config=config,
        name="category_summary",
        runtime_params={"month": "2025-08"},
        limit=10,
    )

    assert result.description == "Total amount per category for the selected month."
    assert any(row[0] == "Food & Dining" for row in result.rows)
    assert result.limit_applied is True
    assert result.truncated is False


def test_list_saved_queries_sorted(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    names = [summary.name for summary in executor.list_saved_queries(config=config)]
    assert names == sorted(names)


def test_run_merchant_patterns_query(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.run_saved_query(
        config=config,
        name="merchant_patterns",
        runtime_params={"pattern": "%AMAZON%"},
        limit=10,
    )

    assert any(row[0] == "AMAZON" for row in result.rows)
    assert result.limit_applied is True


def test_run_categories_query(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.run_saved_query(
        config=config,
        name="categories",
        runtime_params={"category": "%Dining%"},
        limit=10,
    )

    assert any("Dining" in row[0] for row in result.rows)
    assert result.limit_applied is True


def test_run_recent_imports_query(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.run_saved_query(
        config=config,
        name="recent_imports",
        runtime_params={},
        limit=2,
    )

    assert result.limit_value == 2
    # First row should be the most recently imported transaction
    assert result.rows[0][1] >= result.rows[1][1]


def test_run_transactions_month_query(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.run_saved_query(
        config=config,
        name="transactions_month",
        runtime_params={"month": "2025-08"},
        limit=50,
    )

    assert result.limit_applied is True
    assert len(result.rows) == 2
    date_idx = result.columns.index("date")
    assert all(str(row[date_idx]).startswith("2025-08") for row in result.rows)

    filtered = executor.run_saved_query(
        config=config,
        name="transactions_month",
        runtime_params={"month": "2025-08", "category": "Food%"},
        limit=50,
    )
    category_idx = filtered.columns.index("category")
    assert {row[category_idx] for row in filtered.rows} == {"Food & Dining"}


def test_run_merchants_query(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.run_saved_query(
        config=config,
        name="merchants",
        runtime_params={"min_count": 2},
        limit=5,
    )

    assert result.description == "Merchant frequency table for prompt building."
    assert result.limit_applied is True
    merchants = {row[0]: row[1] for row in result.rows}
    assert merchants.get("Amazon") == 2
    assert "Whole Foods" not in merchants


def test_run_merchant_search_query(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.run_saved_query(
        config=config,
        name="merchant_search",
        runtime_params={"pattern": "%Amazon%"},
        limit=5,
    )

    assert result.description == "Transactions matching merchants via SQL LIKE patterns."
    assert result.limit_applied is True
    assert result.columns[0] == "id"
    assert any(row[result.columns.index("merchant")] == "Amazon" for row in result.rows)


def test_run_category_transactions_query(tmp_path) -> None:
    config, _ = _config(tmp_path)
    _seed_transactions(config)

    result = executor.run_saved_query(
        config=config,
        name="category_transactions",
        runtime_params={"category": "Entertainment", "subcategory": "Comedy"},
        limit=10,
    )

    assert result.description == "Transactions filtered by category and optional subcategory."
    categories = {
        (row[result.columns.index("category")], row[result.columns.index("subcategory")])
        for row in result.rows
    }
    assert categories == {("Entertainment", "Comedy")}
