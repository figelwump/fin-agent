from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors
from fin_cli.shared.exceptions import ConfigurationError, FinAgentError


class DummyAppConfig:
    def __init__(self, path: Path) -> None:
        self.database = SimpleNamespace(path=path)

    def with_database_path(self, new_path: str | Path) -> DummyAppConfig:
        return DummyAppConfig(Path(new_path))


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _stub_config(tmp_path: Path) -> DummyAppConfig:
    return DummyAppConfig(tmp_path / "db.sqlite")


def test_common_cli_options_runs_migrations_by_default(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    recorded: dict[str, Path] = {}

    monkeypatch.setattr(
        "fin_cli.shared.cli.load_config", lambda config_path: _stub_config(tmp_path)
    )

    def fake_run_migrations(app_config: DummyAppConfig) -> None:  # type: ignore[override]
        recorded["migrations_db"] = app_config.database.path

    monkeypatch.setattr("fin_cli.shared.cli.run_migrations", fake_run_migrations)

    @click.command()
    @common_cli_options
    def sample(cli_ctx: CLIContext) -> None:
        click.echo(f"dry={cli_ctx.dry_run} db={cli_ctx.db_path}")

    result = runner.invoke(sample, [])

    assert result.exit_code == 0, result.output
    assert "dry=False" in result.output
    assert recorded["migrations_db"].name == "db.sqlite"


def test_common_cli_options_respects_dry_run(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "fin_cli.shared.cli.load_config", lambda config_path: _stub_config(tmp_path)
    )

    migrations_called = False

    def fake_run_migrations(app_config: DummyAppConfig) -> None:  # type: ignore[override]
        nonlocal migrations_called
        migrations_called = True

    monkeypatch.setattr("fin_cli.shared.cli.run_migrations", fake_run_migrations)

    @click.command()
    @common_cli_options
    def sample(cli_ctx: CLIContext) -> None:
        click.echo(f"dry={cli_ctx.dry_run}")

    result = runner.invoke(sample, ["--dry-run"])

    assert result.exit_code == 0, result.output
    assert "dry=True" in result.output
    assert migrations_called is False


def test_common_cli_options_skips_migrations_when_disabled(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "fin_cli.shared.cli.load_config", lambda config_path: _stub_config(tmp_path)
    )

    called = False

    def fake_run_migrations(app_config: DummyAppConfig) -> None:  # type: ignore[override]
        nonlocal called
        called = True

    monkeypatch.setattr("fin_cli.shared.cli.run_migrations", fake_run_migrations)

    @click.command()
    @common_cli_options(run_migrations_on_start=False)
    def sample(cli_ctx: CLIContext) -> None:
        click.echo(str(cli_ctx.db_path))

    result = runner.invoke(sample, [])

    assert result.exit_code == 0, result.output
    assert called is False


def test_common_cli_options_applies_db_override(
    monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path
) -> None:
    base_config = DummyAppConfig(tmp_path / "original.sqlite")

    def fake_load_config(config_path: str | None) -> DummyAppConfig:
        return base_config

    monkeypatch.setattr("fin_cli.shared.cli.load_config", fake_load_config)
    monkeypatch.setattr("fin_cli.shared.cli.run_migrations", lambda cfg: None)

    @click.command()
    @common_cli_options
    def sample(cli_ctx: CLIContext) -> None:
        click.echo(str(cli_ctx.db_path))

    override_path = tmp_path / "override.sqlite"
    result = runner.invoke(sample, ["--db", str(override_path)])

    assert result.exit_code == 0, result.output
    assert override_path.as_posix() in result.output


def test_handle_cli_errors_wraps_known_exceptions() -> None:
    @handle_cli_errors
    def boom() -> None:
        raise FinAgentError("boom")

    with pytest.raises(click.ClickException) as excinfo:
        boom()
    assert str(excinfo.value) == "boom"


def test_handle_cli_errors_formats_configuration_errors() -> None:
    @handle_cli_errors
    def misconfigured() -> None:
        raise ConfigurationError("missing value")

    with pytest.raises(click.ClickException) as excinfo:
        misconfigured()
    assert "Configuration error" in str(excinfo.value)


def test_handle_cli_errors_wraps_unexpected_exceptions() -> None:
    @handle_cli_errors
    def explode() -> None:
        raise RuntimeError("kapow")

    with pytest.raises(click.ClickException) as excinfo:
        explode()
    assert "Unexpected error: kapow" == str(excinfo.value)
