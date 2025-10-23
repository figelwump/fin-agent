"""Utilities for resolving and managing application paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

DEFAULT_CONFIG_DIR = "~/.finagent"
DEFAULT_DATA_DIR = "~/.findata"
DEFAULT_DATABASE_PATH = "~/.finagent/data.db"
DEFAULT_CONFIG_FILE = "config.yaml"
DEFAULT_PLUGINS_DIR = "~/.finagent/extractors"

CONFIG_DIR_ENV = "FINCLI_CONFIG_DIR"
DATA_DIR_ENV = "FINCLI_DATA_DIR"
CONFIG_FILE_ENV = "FINCLI_CONFIG_PATH"
DATABASE_PATH_ENV = "FINAGENT_DATABASE_PATH"
PLUGINS_DIR_ENV = "FINCLI_PLUGIN_DIR"


def _expand(path_str: str) -> Path:
    """Return a Path with user and environment variables expanded."""
    return Path(os.path.expandvars(path_str)).expanduser()


def get_config_dir(create: bool = False, env: Mapping[str, str] | None = None) -> Path:
    """Return the configuration directory, optionally creating it."""
    env = env or os.environ
    raw = env.get(CONFIG_DIR_ENV, DEFAULT_CONFIG_DIR)
    path = _expand(raw)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_dir(create: bool = False, env: Mapping[str, str] | None = None) -> Path:
    """Return the data directory, optionally creating it."""
    env = env or os.environ
    raw = env.get(DATA_DIR_ENV, DEFAULT_DATA_DIR)
    path = _expand(raw)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def default_config_path(create_parents: bool = False, env: Mapping[str, str] | None = None) -> Path:
    """Return the default config file path, optionally ensuring parent dirs exist."""
    env = env or os.environ
    override = env.get(CONFIG_FILE_ENV)
    if override:
        path = _expand(override)
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path
    config_dir = get_config_dir(create=create_parents, env=env)
    return config_dir / DEFAULT_CONFIG_FILE


def default_database_path(create_parents: bool = False, env: Mapping[str, str] | None = None) -> Path:
    """Return the default database file path, optionally ensuring parent dirs exist."""
    env = env or os.environ
    override = env.get(DATABASE_PATH_ENV)
    if override:
        path = _expand(override)
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path
    path = _expand(DEFAULT_DATABASE_PATH)
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def default_plugins_path(create: bool = False, env: Mapping[str, str] | None = None) -> Path:
    """Return the default user plugins directory."""

    env = env or os.environ
    override = env.get(PLUGINS_DIR_ENV)
    path = _expand(override) if override else _expand(DEFAULT_PLUGINS_DIR)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_path(path_str: str | Path) -> Path:
    """Expand user and environment variables for arbitrary paths."""
    if isinstance(path_str, Path):
        return _expand(str(path_str))
    return _expand(path_str)
