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
        expected_version = max(
            int(path.stem.split("_", 1)[0])
            for path in resources.files("fin_cli.shared.migrations").iterdir()
            if path.suffix == ".sql"
        )
        assert version == expected_version


def test_connect_applies_migrations_by_default(tmp_path: Path) -> None:
    config = _temp_config(tmp_path)
    with connect(config) as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM schema_versions")
        assert cursor.fetchone()[0] >= 1
