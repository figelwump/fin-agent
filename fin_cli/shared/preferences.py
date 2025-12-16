"""User preferences management with safe file handling.

Handles portfolio targets, risk tolerance, and investment preferences.
Preferences are stored in ~/.finagent/preferences.json with atomic writes.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths

logger = logging.getLogger(__name__)

DEFAULT_PREFERENCES_FILE = "preferences.json"
PREFERENCES_FILE_ENV = "FINAGENT_PREFERENCES_PATH"

# Current schema version - increment when breaking changes occur
PREFERENCES_VERSION = 1


@dataclass(frozen=True, slots=True)
class TargetAllocation:
    """A single target allocation entry."""

    main_class: str
    sub_class: str
    weight: float  # percentage (0-100)


@dataclass(frozen=True, slots=True)
class InvestmentProfile:
    """User's investment profile and risk tolerance."""

    horizon: str  # "short", "medium", "long"
    risk_tolerance: str  # "low", "moderate", "moderate-high", "high"
    income_needs: str  # "living", "partial", "none"


@dataclass(frozen=True, slots=True)
class PreferenceSettings:
    """Additional preference settings."""

    cash_cushion_months: int = 6
    rebalance_threshold_pct: float = 5.0
    tax_aware: bool = True


@dataclass(slots=True)
class UserPreferences:
    """Complete user preferences."""

    version: int = PREFERENCES_VERSION
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    profile: InvestmentProfile | None = None
    portfolio_targets: tuple[TargetAllocation, ...] = ()
    account_targets: Mapping[str, tuple[TargetAllocation, ...]] = field(default_factory=dict)
    settings: PreferenceSettings = field(default_factory=PreferenceSettings)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        result: dict[str, Any] = {
            "version": self.version,
            "updated_at": self.updated_at,
            "profile": None,
            "targets": {
                "portfolio": [
                    {"main_class": t.main_class, "sub_class": t.sub_class, "weight": t.weight}
                    for t in self.portfolio_targets
                ],
                "accounts": {
                    account_id: [
                        {"main_class": t.main_class, "sub_class": t.sub_class, "weight": t.weight}
                        for t in targets
                    ]
                    for account_id, targets in self.account_targets.items()
                },
            },
            "preferences": {
                "cash_cushion_months": self.settings.cash_cushion_months,
                "rebalance_threshold_pct": self.settings.rebalance_threshold_pct,
                "tax_aware": self.settings.tax_aware,
            },
        }
        if self.profile:
            result["profile"] = {
                "horizon": self.profile.horizon,
                "risk_tolerance": self.profile.risk_tolerance,
                "income_needs": self.profile.income_needs,
            }
        return result


def get_preferences_path(env: Mapping[str, str] | None = None) -> Path:
    """Return the preferences file path."""
    env = env or os.environ
    override = env.get(PREFERENCES_FILE_ENV)
    if override:
        return paths.resolve_path(override)
    config_dir = paths.get_config_dir(create=False, env=env)
    return config_dir / DEFAULT_PREFERENCES_FILE


def load_preferences(
    path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> UserPreferences:
    """Load user preferences from disk.

    Returns sensible defaults if file doesn't exist.
    Logs a warning if file is missing but doesn't raise.
    """
    resolved_path = Path(path) if path else get_preferences_path(env)

    if not resolved_path.exists():
        logger.warning(
            "Preferences file not found at %s; using defaults. "
            "Run the preference capture workflow to set your targets.",
            resolved_path,
        )
        return UserPreferences()

    try:
        with resolved_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Failed to read preferences from %s: %s; using defaults.", resolved_path, exc
        )
        return UserPreferences()

    return _parse_preferences(data)


def save_preferences(
    preferences: UserPreferences,
    path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Save user preferences to disk with atomic write.

    Creates the config directory if it doesn't exist.
    Uses temp file + rename for atomic write to prevent corruption.

    Returns the path where preferences were saved.
    """
    resolved_path = Path(path) if path else get_preferences_path(env)

    # Ensure parent directory exists with appropriate permissions
    parent = resolved_path.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        logger.info("Created preferences directory: %s", parent)

    # Update timestamp
    preferences.updated_at = datetime.now(timezone.utc).isoformat()

    # Atomic write: write to temp file in same directory, then rename
    data = preferences.to_dict()
    json_content = json.dumps(data, indent=2, sort_keys=False)

    try:
        # Create temp file in same directory to ensure atomic rename works
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=".preferences_",
            dir=parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json_content)
                f.write("\n")  # Trailing newline
                f.flush()
                os.fsync(f.fileno())  # Ensure data is flushed to disk

            # Atomic rename
            os.replace(temp_path, resolved_path)
            logger.info("Saved preferences to %s", resolved_path)

        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    except OSError as exc:
        logger.error("Failed to save preferences to %s: %s", resolved_path, exc)
        raise

    return resolved_path


def update_portfolio_targets(
    targets: list[TargetAllocation],
    path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> UserPreferences:
    """Update portfolio targets and save.

    Loads existing preferences, updates targets, and saves atomically.
    """
    prefs = load_preferences(path, env)
    # Create new preferences with updated targets
    updated = UserPreferences(
        version=prefs.version,
        updated_at=prefs.updated_at,
        profile=prefs.profile,
        portfolio_targets=tuple(targets),
        account_targets=prefs.account_targets,
        settings=prefs.settings,
    )
    save_preferences(updated, path, env)
    return updated


def update_profile(
    profile: InvestmentProfile,
    path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> UserPreferences:
    """Update investment profile and save."""
    prefs = load_preferences(path, env)
    updated = UserPreferences(
        version=prefs.version,
        updated_at=prefs.updated_at,
        profile=profile,
        portfolio_targets=prefs.portfolio_targets,
        account_targets=prefs.account_targets,
        settings=prefs.settings,
    )
    save_preferences(updated, path, env)
    return updated


def _parse_preferences(data: dict[str, Any]) -> UserPreferences:
    """Parse preferences from JSON data."""
    version = data.get("version", 1)
    updated_at = data.get("updated_at", datetime.now(timezone.utc).isoformat())

    # Parse profile
    profile = None
    profile_data = data.get("profile")
    if profile_data:
        profile = InvestmentProfile(
            horizon=profile_data.get("horizon", "medium"),
            risk_tolerance=profile_data.get("risk_tolerance", "moderate"),
            income_needs=profile_data.get("income_needs", "none"),
        )

    # Parse targets
    targets_data = data.get("targets", {})
    portfolio_targets = tuple(
        TargetAllocation(
            main_class=t.get("main_class", ""),
            sub_class=t.get("sub_class", ""),
            weight=float(t.get("weight", 0)),
        )
        for t in targets_data.get("portfolio", [])
    )

    account_targets: dict[str, tuple[TargetAllocation, ...]] = {}
    for account_id, account_targets_data in targets_data.get("accounts", {}).items():
        account_targets[account_id] = tuple(
            TargetAllocation(
                main_class=t.get("main_class", ""),
                sub_class=t.get("sub_class", ""),
                weight=float(t.get("weight", 0)),
            )
            for t in account_targets_data
        )

    # Parse settings
    settings_data = data.get("preferences", {})
    settings = PreferenceSettings(
        cash_cushion_months=int(settings_data.get("cash_cushion_months", 6)),
        rebalance_threshold_pct=float(settings_data.get("rebalance_threshold_pct", 5.0)),
        tax_aware=bool(settings_data.get("tax_aware", True)),
    )

    return UserPreferences(
        version=version,
        updated_at=updated_at,
        profile=profile,
        portfolio_targets=portfolio_targets,
        account_targets=account_targets,
        settings=settings,
    )
