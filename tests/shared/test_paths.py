from __future__ import annotations

from pathlib import Path

from fin_cli.shared import paths


def test_get_config_dir_uses_env_override(tmp_path: Path) -> None:
    env = {paths.CONFIG_DIR_ENV: str(tmp_path / "config")}
    result = paths.get_config_dir(create=True, env=env)
    assert result == tmp_path / "config"
    assert result.exists()


def test_default_database_path_uses_override(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "custom.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    resolved = paths.default_database_path(create_parents=True, env=env)
    assert resolved == db_path
    assert resolved.parent.exists()


def test_resolve_path_expands_user(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    result = paths.resolve_path("~/file.txt")
    assert result == fake_home / "file.txt"
