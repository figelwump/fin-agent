"""Shared CLI helpers (stub for Phase 1)."""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

import click

F = TypeVar("F", bound=Callable[..., Any])


def common_cli_options(func: F) -> F:
    """Decorator adding placeholder shared options.

    Real implementation will wire options like --db, --config, --verbose, and set
    up rich-based logging. For now we preserve the decorator shape so CLI modules
    can adopt it without churn.
    """

    @click.option("--config", type=click.Path(path_type=str), help="Path to config file.")
    @click.option("--verbose", is_flag=True, help="Enable verbose logging output.")
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("verbose"):
            click.echo("[stub] verbose logging not yet implemented.")
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def handle_cli_errors(func: F) -> F:
    """Decorator placeholder for consistent error handling."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except click.ClickException:
            raise
        except Exception as exc:  # pragma: no cover - minimal stub for now
            raise click.ClickException(str(exc)) from exc

    return wrapper  # type: ignore[return-value]
