"""Database utilities and migration runner."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterator, Sequence

from .config import AppConfig
from .exceptions import DatabaseError

MIGRATION_PACKAGE = "fin_cli.shared.migrations"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    description: str
    sql: str


def _resolve_database_path(config: AppConfig) -> Path:
    db_path = config.database.path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _open_connection(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _load_migrations() -> Sequence[Migration]:
    migrations: list[Migration] = []
    with resources.as_file(resources.files(MIGRATION_PACKAGE)) as package_path:
        for entry in sorted(package_path.iterdir()):
            if entry.suffix.lower() != ".sql":
                continue
            name = entry.stem
            try:
                version_str, description = name.split("_", 1)
            except ValueError:
                version_str, description = name, name
            try:
                version = int(version_str)
            except ValueError as exc:  # pragma: no cover - configuration time error
                raise DatabaseError(f"Invalid migration filename '{entry.name}'") from exc
            sql = entry.read_text(encoding="utf-8")
            migrations.append(Migration(version=version, name=name, description=description, sql=sql))
    migrations.sort(key=lambda m: m.version)
    return migrations


def _get_applied_versions(connection: sqlite3.Connection) -> set[int]:
    try:
        rows = connection.execute("SELECT version FROM schema_versions").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {int(row[0]) for row in rows}


def run_migrations(config: AppConfig) -> None:
    """Apply pending migrations using the config's database path."""
    db_path = _resolve_database_path(config)
    migrations = _load_migrations()
    if not migrations:
        return

    connection = _open_connection(db_path)
    try:
        applied = _get_applied_versions(connection)
        for migration in migrations:
            if migration.version in applied:
                continue
            connection.execute("BEGIN")
            connection.executescript(migration.sql)
            connection.execute(
                "INSERT OR REPLACE INTO schema_versions(version, description) VALUES (?, ?)",
                (migration.version, migration.description),
            )
            connection.commit()
    finally:
        connection.close()


@contextmanager
def connect(
    config: AppConfig,
    *,
    read_only: bool = False,
    apply_migrations: bool = True,
) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection for the configured database."""
    if apply_migrations and not read_only:
        run_migrations(config)
    db_path = _resolve_database_path(config)
    connection = _open_connection(db_path, read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()
