from __future__ import annotations

from importlib import resources
from pathlib import Path

from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations


def _temp_config(tmp_path: Path):
    db_path = tmp_path / "test.db"
    env = {
        paths.DATABASE_PATH_ENV: str(db_path),
    }
    return load_config(env=env)


def _latest_migration_version() -> int:
    return max(
        int(path.stem.split("_", 1)[0])
        for path in resources.files("fin_cli.shared.migrations").iterdir()
        if path.suffix == ".sql"
    )


def test_run_migrations_creates_schema(tmp_path: Path) -> None:
    config = _temp_config(tmp_path)
    run_migrations(config)
    with connect(config, apply_migrations=False) as connection:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "accounts",
            "categories",
            "transactions",
            "merchant_patterns",
            "schema_versions",
        }.issubset(tables)
        version = connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
        assert version == _latest_migration_version()


def test_connect_applies_migrations_by_default(tmp_path: Path) -> None:
    config = _temp_config(tmp_path)
    with connect(config) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM schema_versions")
        assert cursor.fetchone()[0] >= 1


def test_run_migrations_is_idempotent(tmp_path: Path) -> None:
    """Running migrations twice should not duplicate seed rows or error.

    Asset tracking migrations seed asset_sources via INSERT OR IGNORE; this
    regression test ensures reruns remain safe as new migrations are added.
    """

    config = _temp_config(tmp_path)

    # First run creates the schema and seeds rows.
    run_migrations(config)
    # Second run should be a no-op rather than raising or duplicating data.
    run_migrations(config)

    with connect(config, apply_migrations=False) as connection:
        version = connection.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0]
        assert version == _latest_migration_version()

        duplicate_sources = connection.execute(
            """
            SELECT name, COUNT(*) AS count
            FROM asset_sources
            GROUP BY name
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        assert duplicate_sources == []
