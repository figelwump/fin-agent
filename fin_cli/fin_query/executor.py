"""Query execution helpers for fin-query."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Iterator

import yaml

from fin_cli.shared.config import AppConfig
from fin_cli.shared.database import connect
from fin_cli.shared.exceptions import QueryError

from .types import QueryResult, SavedQuerySummary, SchemaOverview, SchemaTable

DEFAULT_ROW_LIMIT = 200
QUERIES_PACKAGE = "fin_cli.fin_query.queries"
MANIFEST_NAME = "index.yaml"


@dataclass(slots=True)
class SavedQueryDefinition:
    """Full representation of a saved query loaded from the manifest."""

    name: str
    description: str
    sql_resource: Traversable
    parameters: dict[str, dict[str, Any]]

    def default_params(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for key, meta in self.parameters.items():
            if isinstance(meta, Mapping) and "default" in meta:
                defaults[key] = _coerce_parameter_value(meta["default"], meta.get("type"), key)
        return defaults


def execute_sql(
    *,
    config: AppConfig,
    query: str,
    params: Mapping[str, object] | None = None,
    limit: int | None = None,
) -> QueryResult:
    """Execute ad-hoc SQL and return a structured result set."""

    effective_limit = _normalise_limit(limit)
    bindings = dict(params or {})

    try:
        with _read_only_connection(config) as connection:
            cursor = connection.cursor()
            cursor.execute(query, bindings)
            rows, truncated = _fetch_rows(cursor, effective_limit)
            description = cursor.description or ()
    except sqlite3.OperationalError as exc:
        raise QueryError(f"SQLite error: {exc}") from exc
    except sqlite3.DatabaseError as exc:
        raise QueryError(f"Database error during execution: {exc}") from exc

    columns = tuple(col[0] for col in description)
    serialised_rows = [tuple(row) for row in rows]
    result = QueryResult(
        columns=columns,
        rows=serialised_rows,
        limit_applied=effective_limit is not None,
        limit_value=effective_limit,
        description=None,
        truncated=truncated,
    )
    return result


def run_saved_query(
    *,
    config: AppConfig,
    name: str,
    runtime_params: Mapping[str, object] | None = None,
    limit: int | None = None,
) -> QueryResult:
    """Resolve a saved query definition and execute it."""

    definition = _lookup_saved_query(name)
    params: dict[str, Any] = definition.default_params()
    params.update(runtime_params or {})

    # Apply type coercion based on manifest metadata.
    for key, meta in definition.parameters.items():
        if key in params and isinstance(meta, Mapping):
            params[key] = _coerce_parameter_value(params[key], meta.get("type"), key)
        elif isinstance(meta, Mapping) and meta.get("required"):
            raise QueryError(f"Saved query '{name}' requires parameter '{key}'.")

    # If the SQL expects a :limit binding, wire CLI --limit through to it when provided.
    if limit is not None and "limit" in definition.parameters and "limit" not in params:
        params["limit"] = limit

    query_text = definition.sql_resource.read_text(encoding="utf-8")
    result = execute_sql(
        config=config,
        query=query_text,
        params=params,
        limit=limit,
    )
    return replace(result, description=definition.description or None)


def list_saved_queries(*, config: AppConfig) -> Sequence[SavedQuerySummary]:
    """Return metadata for all saved queries defined in the manifest."""

    catalog = _load_manifest()
    summaries: list[SavedQuerySummary] = []
    for definition in catalog:
        summaries.append(
            SavedQuerySummary(
                name=definition.name,
                description=definition.description,
                path=str(definition.sql_resource),
                parameters=definition.parameters,
            )
        )
    return summaries


def describe_schema(
    *,
    config: AppConfig,
    table_filter: str | None = None,
    as_json: bool = False,
) -> SchemaOverview:
    """Inspect the SQLite schema for reporting purposes."""

    # `as_json` will inform formatting decisions in Phase 4 renderers; we accept it
    # now so future changes do not require signature churn.
    _ = as_json

    with _read_only_connection(config) as connection:
        tables = _fetch_table_names(connection, table_filter)
        if table_filter and not tables:
            raise QueryError(f"Table '{table_filter}' does not exist in the database.")

        schema_tables: list[SchemaTable] = []
        for table_name in tables:
            columns = _fetch_table_columns(connection, table_name)
            indexes = _fetch_table_indexes(connection, table_name)
            foreign_keys = _fetch_foreign_keys(connection, table_name)
            estimated_rows = _estimate_row_count(connection, table_name)
            schema_tables.append(
                SchemaTable(
                    name=table_name,
                    columns=columns,
                    indexes=indexes,
                    foreign_keys=foreign_keys,
                    estimated_row_count=estimated_rows,
                )
            )

    return SchemaOverview(tables=schema_tables, database_path=config.database.path)


# ---------------------------------------------------------------------------
# Internal helpers


def _normalise_limit(limit: int | None) -> int | None:
    if limit is None:
        return DEFAULT_ROW_LIMIT
    if limit <= 0:
        return None
    return limit


@contextmanager
def _read_only_connection(config: AppConfig) -> Iterator[sqlite3.Connection]:
    """Yield a connection that prevents writes to the user database."""
    try:
        with connect(config, read_only=True, apply_migrations=False) as connection:
            yield connection
    except FileNotFoundError as exc:
        raise QueryError(f"Database path not found: {exc}") from exc


def _fetch_rows(cursor: sqlite3.Cursor, limit: int | None) -> tuple[Sequence[sqlite3.Row], bool]:
    if limit is None:
        rows = cursor.fetchall()
        return rows, False

    rows = cursor.fetchmany(limit + 1)
    truncated = len(rows) > limit
    return rows[:limit], truncated


def _load_manifest() -> list[SavedQueryDefinition]:
    manifest_resource = resources.files(QUERIES_PACKAGE).joinpath(MANIFEST_NAME)
    if not manifest_resource.exists():
        raise QueryError(
            "Saved query manifest is missing; ensure index.yaml exists under fin_query/queries."
        )

    try:
        manifest_data = yaml.safe_load(manifest_resource.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:  # pragma: no cover - packaging issue
        raise QueryError(f"Unable to load query manifest: {exc}") from exc

    version = manifest_data.get("version")
    if version != 1:
        raise QueryError("Unsupported saved query manifest version; expected version=1.")

    queries = manifest_data.get("queries") or []
    definitions: list[SavedQueryDefinition] = []
    for entry in queries:
        definition = _parse_query_definition(entry)
        definitions.append(definition)
    definitions.sort(key=lambda definition: definition.name)
    return definitions


def _lookup_saved_query(name: str) -> SavedQueryDefinition:
    catalog = _load_manifest()
    for definition in catalog:
        if definition.name == name:
            return definition
    available = ", ".join(definition.name for definition in catalog)
    raise QueryError(f"Saved query '{name}' is not defined. Available queries: {available or 'none'}.")


def _parse_query_definition(entry: Mapping[str, Any]) -> SavedQueryDefinition:
    if not isinstance(entry, Mapping):
        raise QueryError("Each saved query entry must be a mapping of properties.")

    try:
        name = str(entry["name"])
        filename = str(entry["file"])
        description = str(entry.get("description") or "")
    except KeyError as exc:
        raise QueryError(f"Saved query missing required field: {exc}") from exc

    sql_resource = resources.files(QUERIES_PACKAGE).joinpath(filename)
    if not sql_resource.exists():
        raise QueryError(f"Saved query '{name}' references missing SQL file '{filename}'.")

    parameters = entry.get("parameters") or {}
    if not isinstance(parameters, Mapping):
        raise QueryError(f"Parameters for saved query '{name}' must be a mapping.")

    normalised_params: dict[str, dict[str, Any]] = {}
    for key, meta in parameters.items():
        if not isinstance(meta, Mapping):
            raise QueryError(f"Parameter '{key}' for saved query '{name}' must define metadata.")
        normalised_params[str(key)] = dict(meta)

    return SavedQueryDefinition(
        name=name,
        description=description,
        sql_resource=sql_resource,
        parameters=normalised_params,
    )


def _coerce_parameter_value(raw: Any, declared_type: str | None, param_name: str | None = None) -> Any:
    if raw is None:
        return None
    if declared_type is None:
        return raw
    try:
        if declared_type == "integer":
            return int(raw)
        if declared_type == "float":
            return float(raw)
        if declared_type == "boolean":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str):
                lowered = raw.lower()
                if lowered in {"true", "1", "yes"}:
                    return True
                if lowered in {"false", "0", "no"}:
                    return False
            return bool(raw)
    except (TypeError, ValueError) as exc:
        label = f" for parameter '{param_name}'" if param_name else ""
        raise QueryError(f"Unable to coerce value{label} to {declared_type}: {raw}") from exc
    return raw


def _fetch_table_names(connection: sqlite3.Connection, table_filter: str | None) -> list[str]:
    sql = "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    params: tuple[Any, ...] = ()
    if table_filter:
        sql += " AND name = ?"
        params = (table_filter,)
    sql += " ORDER BY name"
    cursor = connection.execute(sql, params)
    return [row[0] for row in cursor.fetchall()]


def _fetch_table_columns(connection: sqlite3.Connection, table: str) -> Sequence[tuple[str, str, bool]]:
    cursor = connection.execute(f"PRAGMA table_info('{table}')")
    return [(row[1], row[2], bool(row[3])) for row in cursor.fetchall()]


def _fetch_table_indexes(connection: sqlite3.Connection, table: str) -> Sequence[str]:
    cursor = connection.execute(f"PRAGMA index_list('{table}')")
    return [row[1] for row in cursor.fetchall()]


def _fetch_foreign_keys(connection: sqlite3.Connection, table: str) -> Sequence[tuple[str, str, str]]:
    cursor = connection.execute(f"PRAGMA foreign_key_list('{table}')")
    return [(row[3], row[2], row[4]) for row in cursor.fetchall()]


def _estimate_row_count(connection: sqlite3.Connection, table: str) -> int:
    cursor = connection.execute(f"SELECT COUNT(*) FROM '{table}'")
    return int(cursor.fetchone()[0])
