"""Shared CLI helpers and decorators."""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

import click

from .config import AppConfig, load_config
from .database import run_migrations
from .exceptions import ConfigurationError, FinAgentError
from .logging import Logger, get_logger

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(slots=True)
class CLIContext:
    """Runtime context shared across CLI invocations."""

    config: AppConfig
    db_path: Path
    dry_run: bool
    verbose: bool
    logger: Logger


pass_cli_context = click.make_pass_decorator(CLIContext)


def common_cli_options(func: F) -> F:
    """Decorator injecting shared CLI options and context creation."""

    @click.option("--config", "config_path", type=click.Path(path_type=str), help="Path to config file.")
    @click.option("--db", "db_path", type=click.Path(path_type=str), help="Override database path.")
    @click.option("--dry-run", is_flag=True, help="Preview actions without side effects.")
    @click.option("--verbose", is_flag=True, help="Enable verbose logging output.")
    @click.pass_context
    @functools.wraps(func)
    def wrapper(
        ctx: click.Context,
        *args: Any,
        config_path: str | None = None,
        db_path: str | None = None,
        dry_run: bool = False,
        verbose: bool = False,
        **kwargs: Any,
    ) -> Any:
        try:
            app_config = load_config(config_path)
        except ConfigurationError as exc:
            raise click.ClickException(str(exc)) from exc

        logger = get_logger(verbose=verbose)
        effective_db_path = Path(db_path).expanduser() if db_path else app_config.database.path
        if db_path:
            app_config = app_config.with_database_path(effective_db_path)

        if not dry_run:
            run_migrations(app_config)

        cli_ctx = CLIContext(
            config=app_config,
            db_path=effective_db_path,
            dry_run=dry_run,
            verbose=verbose,
            logger=logger,
        )
        ctx.obj = cli_ctx
        kwargs["cli_ctx"] = cli_ctx
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def handle_cli_errors(func: F) -> F:
    """Convert project exceptions into Click-friendly errors."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ConfigurationError as exc:
            raise click.ClickException(f"Configuration error: {exc}") from exc
        except FinAgentError as exc:
            raise click.ClickException(str(exc)) from exc
        except click.ClickException:
            raise
        except Exception as exc:  # pragma: no cover
            raise click.ClickException(f"Unexpected error: {exc}") from exc

    return wrapper  # type: ignore[return-value]
