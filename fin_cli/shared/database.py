"""Database utilities placeholder.

Phase 2 will flesh out connection management, migrations, and query helpers.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import AppConfig


@contextmanager
def connect(config: AppConfig) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection using the configured database path."""
    db_path = Path(config.database_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        yield connection
    finally:
        connection.close()


def run_migrations(_: AppConfig) -> None:
    """Placeholder migration runner."""
    # Phase 2 will execute SQL files from shared/migrations.
    return None
