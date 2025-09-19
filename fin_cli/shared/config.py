"""Configuration loading utilities (to be implemented in Phase 1).

The real implementation will merge defaults, YAML config, and environment
variables to satisfy the product spec. This stub keeps import sites stable for
ongoing scaffolding.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AppConfig:
    """Placeholder application config object."""

    database_path: str = "~/.findata/transactions.db"
    config_path: str = "~/.finconfig/config.yaml"


def load_config(*_: str) -> AppConfig:
    """Return a default config until Phase 1 builds real loading logic."""
    return AppConfig()
