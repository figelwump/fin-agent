"""Configuration loading utilities for the financial CLI suite."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import yaml

from . import paths
from .exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Database-related configuration."""

    path: Path


@dataclass(frozen=True, slots=True)
class ExtractionSettings:
    """PDF extraction configuration."""

    engine: str  # "auto", "docling", or "pdfplumber"
    auto_detect_accounts: bool
    supported_banks: tuple[str, ...]
    camelot_fallback_enabled: bool
    enable_plugins: bool
    plugin_paths: tuple[Path, ...]
    plugin_allowlist: tuple[str, ...]
    plugin_blocklist: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """LLM provider configuration."""

    enabled: bool
    provider: str
    model: str
    api_key_env: str


@dataclass(frozen=True, slots=True)
class DynamicCategoriesSettings:
    """Dynamic category creation behaviour."""

    enabled: bool
    min_transactions_for_new: int
    auto_approve_confidence: float
    max_pending_categories: int


@dataclass(frozen=True, slots=True)
class ConfidenceSettings:
    """Confidence threshold configuration for categorization."""

    auto_approve: float


@dataclass(frozen=True, slots=True)
class CategorizationSettings:
    """Composite categorization configuration."""

    llm: LLMSettings
    dynamic_categories: DynamicCategoriesSettings
    confidence: ConfidenceSettings


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Top-level application configuration."""

    source_path: Path
    database: DatabaseSettings
    extraction: ExtractionSettings
    categorization: CategorizationSettings

    def with_database_path(self, new_path: str | Path) -> AppConfig:
        """Return a copy with an updated database path."""
        resolved = paths.resolve_path(new_path)
        new_db = replace(self.database, path=resolved)
        return replace(self, database=new_db)


def _default_config(env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "database": {"path": str(paths.default_database_path(env=env))},
        "extraction": {
            "engine": "auto",
            "auto_detect_accounts": True,
            "supported_banks": ["chase", "bofa", "mercury"],
            "camelot_fallback_enabled": True,
            "enable_plugins": True,
            "plugin_paths": [str(paths.default_plugins_path(env=env))],
            "plugin_allowlist": [],
            "plugin_blocklist": [],
        },
        "categorization": {
            "llm": {
                "enabled": True,
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key_env": "OPENAI_API_KEY",
            },
            "dynamic_categories": {
                "enabled": True,
                "min_transactions_for_new": 3,
                "auto_approve_confidence": 0.85,
                "max_pending_categories": 20,
            },
            "confidence": {
                "auto_approve": 0.8,
            },
        },
    }


ENV_OVERRIDE_SPEC: dict[str, tuple[str, type]] = {
    "extraction.engine": ("FINCLI_EXTRACTION_ENGINE", str),
    "database.path": (paths.DATABASE_PATH_ENV, str),
    "extraction.auto_detect_accounts": ("FINCLI_EXTRACTION_AUTO_DETECT_ACCOUNTS", bool),
    "extraction.supported_banks": ("FINCLI_EXTRACTION_SUPPORTED_BANKS", list),
    "extraction.camelot_fallback_enabled": ("FINCLI_EXTRACTION_CAMELOT_FALLBACK", bool),
    "extraction.enable_plugins": ("FINCLI_EXTRACTION_ENABLE_PLUGINS", bool),
    "extraction.plugin_paths": ("FINCLI_EXTRACTION_PLUGIN_PATHS", list),
    "extraction.plugin_allowlist": ("FINCLI_EXTRACTION_PLUGIN_ALLOW", list),
    "extraction.plugin_blocklist": ("FINCLI_EXTRACTION_PLUGIN_DENY", list),
    "categorization.llm.enabled": ("FINCLI_LLM_ENABLED", bool),
    "categorization.llm.provider": ("FINCLI_LLM_PROVIDER", str),
    "categorization.llm.model": ("FINCLI_LLM_MODEL", str),
    "categorization.llm.api_key_env": ("FINCLI_LLM_API_KEY_ENV", str),
    "categorization.dynamic_categories.enabled": ("FINCLI_DYNAMIC_CATEGORIES_ENABLED", bool),
    "categorization.dynamic_categories.min_transactions_for_new": (
        "FINCLI_DYNAMIC_CATEGORIES_MIN_TRANSACTIONS",
        int,
    ),
    "categorization.dynamic_categories.auto_approve_confidence": (
        "FINCLI_DYNAMIC_CATEGORIES_AUTO_APPROVE_CONFIDENCE",
        float,
    ),
    "categorization.dynamic_categories.max_pending_categories": (
        "FINCLI_DYNAMIC_CATEGORIES_MAX_PENDING",
        int,
    ),
    "categorization.confidence.auto_approve": ("FINCLI_CONFIDENCE_AUTO_APPROVE", float),
}


def load_config(
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> AppConfig:
    """Load configuration from defaults, YAML file, and env overrides."""
    env = dict(env or os.environ)
    resolved_config_path = _resolve_config_path(config_path, env)
    file_data = _load_yaml(resolved_config_path)
    defaults = _default_config(env)
    merged: dict[str, Any] = _deep_merge(defaults, file_data)
    merged = _apply_env_overrides(merged, env)
    return _build_config(merged, resolved_config_path)


def _resolve_config_path(
    config_path: str | Path | None, env: Mapping[str, str]
) -> Path:
    if config_path:
        return paths.resolve_path(config_path)
    return paths.default_config_path(env=env)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
        if not isinstance(data, MutableMapping):
            raise ConfigurationError(f"Config file at {path} must define a mapping root object.")
        return dict(data)


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(config: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    config_copy = _deep_merge(config, {})  # shallow copy via merge
    for dotted_key, (env_key, expected_type) in ENV_OVERRIDE_SPEC.items():
        if env_key not in env:
            continue
        raw_value = env[env_key]
        try:
            value = _coerce_env_value(raw_value, expected_type)
        except ValueError as exc:
            raise ConfigurationError(
                f"Environment override {env_key} has invalid value '{raw_value}': {exc}"
            ) from exc
        _assign_nested(config_copy, dotted_key.split("."), value)
    return config_copy


def _coerce_env_value(raw: str, expected_type: type) -> Any:
    cleaned = raw.strip()
    if expected_type is bool:
        lowered = cleaned.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError("expected boolean (true/false)")
    if expected_type is int:
        return int(cleaned)
    if expected_type is float:
        return float(cleaned)
    if expected_type is list:
        if not cleaned:
            return []
        return tuple(part.strip() for part in cleaned.split(",") if part.strip())
    return cleaned


def _assign_nested(target: MutableMapping[str, Any], keys: list[str], value: Any) -> None:
    current = target
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], MutableMapping):
            current[key] = {}
        current = current[key]  # type: ignore[assignment]
    current[keys[-1]] = value


def _build_config(data: Mapping[str, Any], source_path: Path) -> AppConfig:
    try:
        database = DatabaseSettings(path=paths.resolve_path(data["database"]["path"]))
        extraction = ExtractionSettings(
            engine=str(data["extraction"]["engine"]),
            auto_detect_accounts=bool(data["extraction"]["auto_detect_accounts"]),
            supported_banks=tuple(data["extraction"]["supported_banks"]),
            camelot_fallback_enabled=bool(data["extraction"]["camelot_fallback_enabled"]),
            enable_plugins=bool(data["extraction"]["enable_plugins"]),
            plugin_paths=tuple(paths.resolve_path(p) for p in data["extraction"]["plugin_paths"]),
            plugin_allowlist=tuple(str(name) for name in data["extraction"]["plugin_allowlist"]),
            plugin_blocklist=tuple(str(name) for name in data["extraction"]["plugin_blocklist"]),
        )
        llm_cfg = data["categorization"]["llm"]
        llm = LLMSettings(
            enabled=bool(llm_cfg["enabled"]),
            provider=str(llm_cfg["provider"]),
            model=str(llm_cfg["model"]),
            api_key_env=str(llm_cfg["api_key_env"]),
        )
        dyn_cfg = data["categorization"]["dynamic_categories"]
        dynamic_categories = DynamicCategoriesSettings(
            enabled=bool(dyn_cfg["enabled"]),
            min_transactions_for_new=int(dyn_cfg["min_transactions_for_new"]),
            auto_approve_confidence=float(dyn_cfg["auto_approve_confidence"]),
            max_pending_categories=int(dyn_cfg["max_pending_categories"]),
        )
        conf_cfg = data["categorization"]["confidence"]
        confidence = ConfidenceSettings(
            auto_approve=float(conf_cfg["auto_approve"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid configuration structure: {exc}") from exc

    return AppConfig(
        source_path=source_path,
        database=database,
        extraction=extraction,
        categorization=CategorizationSettings(
            llm=llm,
            dynamic_categories=dynamic_categories,
            confidence=confidence,
        ),
    )
