from __future__ import annotations

import io
import json
from pathlib import Path

from fin_cli.fin_query import render
from fin_cli.fin_query.types import QueryResult, SavedQuerySummary, SchemaOverview, SchemaTable


class StubLogger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def info(self, message: str, *args) -> None:
        self.messages.append(("info", message % args if args else message))

    def warning(self, message: str, *args) -> None:
        self.messages.append(("warning", message % args if args else message))

    def debug(self, message: str, *args) -> None:
        self.messages.append(("debug", message % args if args else message))

    def error(self, message: str, *args) -> None:
        self.messages.append(("error", message % args if args else message))

    def success(self, message: str, *args) -> None:
        self.messages.append(("success", message % args if args else message))


def test_render_query_result_csv() -> None:
    buffer = io.StringIO()
    logger = StubLogger()
    result = QueryResult(columns=("merchant", "amount"), rows=[("Amazon", -42.1)], truncated=True, limit_value=1)

    render.render_query_result(result, output_format="csv", logger=logger, stream=buffer)

    output = buffer.getvalue().strip().splitlines()
    assert output[0] == "merchant,amount"
    assert "Amazon" in output[1]
    assert any(level == "warning" for level, _ in logger.messages)


def test_render_query_result_json() -> None:
    buffer = io.StringIO()
    logger = StubLogger()
    result = QueryResult(columns=("merchant", "amount"), rows=[("Amazon", -42.1)], truncated=False)

    render.render_query_result(result, output_format="json", logger=logger, stream=buffer)

    data = json.loads(buffer.getvalue())
    assert data == [{"merchant": "Amazon", "amount": -42.1}]


def test_render_saved_query_catalog(monkeypatch) -> None:
    buffer = io.StringIO()
    logger = StubLogger()

    # Force CSV fallback by disabling Rich console.
    monkeypatch.setattr(render, "Console", None)
    catalog = [
        SavedQuerySummary(
            name="recent_transactions",
            description="Most recent transactions",
            path="queries/recent_transactions.sql",
            parameters={"limit": {"type": "integer", "default": 25}},
        )
    ]

    render.render_saved_query_catalog(catalog, logger=logger, stream=buffer)

    output = buffer.getvalue().strip().splitlines()
    assert output[0].startswith("name,description")
    assert "recent_transactions" in output[1]


def test_render_schema_overview_json() -> None:
    buffer = io.StringIO()
    logger = StubLogger()
    overview = SchemaOverview(
        database_path=Path("/tmp/test.db"),
        tables=[
            SchemaTable(
                name="transactions",
                columns=(("id", "INTEGER", True),),
                indexes=("idx_transactions_id",),
                foreign_keys=(("account_id", "accounts", "id"),),
                estimated_row_count=10,
            )
        ],
    )

    render.render_schema_overview(overview, output_format="json", logger=logger, stream=buffer)

    payload = json.loads(buffer.getvalue())
    assert payload["database"].endswith("test.db")
    assert payload["tables"][0]["name"] == "transactions"
