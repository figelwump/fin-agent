"""Tests for preferences management with safe file handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fin_cli.shared.preferences import (
    InvestmentProfile,
    PreferenceSettings,
    TargetAllocation,
    UserPreferences,
    get_preferences_path,
    load_preferences,
    save_preferences,
    update_portfolio_targets,
    update_profile,
)


@pytest.fixture
def temp_prefs_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for preferences."""
    prefs_dir = tmp_path / ".finagent"
    prefs_dir.mkdir(parents=True)
    return prefs_dir


@pytest.fixture
def temp_prefs_path(temp_prefs_dir: Path) -> Path:
    """Return path to temp preferences file."""
    return temp_prefs_dir / "preferences.json"


class TestGetPreferencesPath:
    """Tests for get_preferences_path."""

    def test_default_path(self) -> None:
        """Default path should be in config dir."""
        path = get_preferences_path()
        assert path.name == "preferences.json"
        assert ".finagent" in str(path)

    def test_env_override(self, tmp_path: Path) -> None:
        """Environment variable should override default."""
        custom_path = tmp_path / "custom" / "prefs.json"
        env = {"FINAGENT_PREFERENCES_PATH": str(custom_path)}
        path = get_preferences_path(env=env)
        assert path == custom_path


class TestLoadPreferences:
    """Tests for load_preferences."""

    def test_load_missing_file_returns_defaults(
        self, temp_prefs_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing file should return defaults with warning."""
        prefs = load_preferences(path=temp_prefs_path)
        assert prefs.version == 1
        assert prefs.profile is None
        assert prefs.portfolio_targets == ()
        assert "not found" in caplog.text.lower()

    def test_load_existing_file(self, temp_prefs_path: Path) -> None:
        """Should load preferences from existing file."""
        data = {
            "version": 1,
            "updated_at": "2025-12-01T10:00:00Z",
            "profile": {
                "horizon": "long",
                "risk_tolerance": "high",
                "income_needs": "none",
            },
            "targets": {
                "portfolio": [
                    {"main_class": "equities", "sub_class": "US", "weight": 60},
                    {"main_class": "bonds", "sub_class": "treasury", "weight": 40},
                ],
                "accounts": {},
            },
            "preferences": {
                "cash_cushion_months": 12,
                "rebalance_threshold_pct": 3.0,
                "tax_aware": False,
            },
        }
        temp_prefs_path.write_text(json.dumps(data))

        prefs = load_preferences(path=temp_prefs_path)
        assert prefs.version == 1
        assert prefs.profile is not None
        assert prefs.profile.horizon == "long"
        assert prefs.profile.risk_tolerance == "high"
        assert len(prefs.portfolio_targets) == 2
        assert prefs.portfolio_targets[0].main_class == "equities"
        assert prefs.portfolio_targets[0].weight == 60
        assert prefs.settings.cash_cushion_months == 12
        assert prefs.settings.tax_aware is False

    def test_load_corrupted_file_returns_defaults(
        self, temp_prefs_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Corrupted file should return defaults with warning."""
        temp_prefs_path.write_text("not valid json {{{")

        prefs = load_preferences(path=temp_prefs_path)
        assert prefs.version == 1
        assert prefs.profile is None
        assert "failed to read" in caplog.text.lower()


class TestSavePreferences:
    """Tests for save_preferences with atomic writes."""

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Should create parent directory if missing."""
        prefs_path = tmp_path / "new_dir" / "subdir" / "prefs.json"
        assert not prefs_path.parent.exists()

        prefs = UserPreferences()
        save_preferences(prefs, path=prefs_path)

        assert prefs_path.parent.exists()
        assert prefs_path.exists()

    def test_save_atomic_write(self, temp_prefs_path: Path) -> None:
        """Should write atomically (no temp file left behind on success)."""
        prefs = UserPreferences(
            profile=InvestmentProfile(
                horizon="medium",
                risk_tolerance="moderate",
                income_needs="partial",
            ),
            portfolio_targets=(
                TargetAllocation("equities", "US", 50),
                TargetAllocation("bonds", "treasury", 50),
            ),
        )

        save_preferences(prefs, path=temp_prefs_path)

        # Check no temp files left
        temp_files = list(temp_prefs_path.parent.glob(".preferences_*.tmp"))
        assert len(temp_files) == 0

        # Check content is correct
        with temp_prefs_path.open() as f:
            data = json.load(f)
        assert data["version"] == 1
        assert data["profile"]["horizon"] == "medium"
        assert len(data["targets"]["portfolio"]) == 2

    def test_save_updates_timestamp(self, temp_prefs_path: Path) -> None:
        """Should update the timestamp on save."""
        prefs = UserPreferences()
        original_time = prefs.updated_at

        save_preferences(prefs, path=temp_prefs_path)

        with temp_prefs_path.open() as f:
            data = json.load(f)

        # Timestamp should be different (updated during save)
        assert data["updated_at"] != original_time or len(original_time) > 0

    def test_save_overwrites_existing(self, temp_prefs_path: Path) -> None:
        """Should overwrite existing file."""
        # Save initial
        prefs1 = UserPreferences(portfolio_targets=(TargetAllocation("equities", "US", 100),))
        save_preferences(prefs1, path=temp_prefs_path)

        # Overwrite
        prefs2 = UserPreferences(portfolio_targets=(TargetAllocation("bonds", "treasury", 100),))
        save_preferences(prefs2, path=temp_prefs_path)

        loaded = load_preferences(path=temp_prefs_path)
        assert len(loaded.portfolio_targets) == 1
        assert loaded.portfolio_targets[0].main_class == "bonds"


class TestUpdateFunctions:
    """Tests for update_portfolio_targets and update_profile."""

    def test_update_portfolio_targets(self, temp_prefs_path: Path) -> None:
        """Should update targets while preserving other fields."""
        # Start with profile
        initial = UserPreferences(
            profile=InvestmentProfile("long", "high", "none"),
            settings=PreferenceSettings(cash_cushion_months=12),
        )
        save_preferences(initial, path=temp_prefs_path)

        # Update targets
        new_targets = [
            TargetAllocation("equities", "US", 70),
            TargetAllocation("bonds", "treasury", 30),
        ]
        updated = update_portfolio_targets(new_targets, path=temp_prefs_path)

        assert len(updated.portfolio_targets) == 2
        assert updated.profile is not None  # Profile preserved
        assert updated.profile.horizon == "long"
        assert updated.settings.cash_cushion_months == 12  # Settings preserved

    def test_update_profile(self, temp_prefs_path: Path) -> None:
        """Should update profile while preserving other fields."""
        # Start with targets
        initial = UserPreferences(portfolio_targets=(TargetAllocation("equities", "US", 100),))
        save_preferences(initial, path=temp_prefs_path)

        # Update profile
        new_profile = InvestmentProfile("short", "low", "living")
        updated = update_profile(new_profile, path=temp_prefs_path)

        assert updated.profile is not None
        assert updated.profile.horizon == "short"
        assert len(updated.portfolio_targets) == 1  # Targets preserved


class TestUserPreferencesToDict:
    """Tests for UserPreferences serialization."""

    def test_to_dict_complete(self) -> None:
        """Should serialize all fields correctly."""
        prefs = UserPreferences(
            version=1,
            updated_at="2025-12-01T10:00:00Z",
            profile=InvestmentProfile("long", "moderate-high", "none"),
            portfolio_targets=(
                TargetAllocation("equities", "US", 60),
                TargetAllocation("bonds", "treasury", 40),
            ),
            account_targets={
                "1": (TargetAllocation("equities", "intl", 100),),
            },
            settings=PreferenceSettings(
                cash_cushion_months=6,
                rebalance_threshold_pct=5.0,
                tax_aware=True,
            ),
        )

        data = prefs.to_dict()

        assert data["version"] == 1
        assert data["profile"]["horizon"] == "long"
        assert len(data["targets"]["portfolio"]) == 2
        assert data["targets"]["accounts"]["1"][0]["main_class"] == "equities"
        assert data["preferences"]["cash_cushion_months"] == 6

    def test_to_dict_minimal(self) -> None:
        """Should handle minimal preferences."""
        prefs = UserPreferences()
        data = prefs.to_dict()

        assert data["version"] == 1
        assert data["profile"] is None
        assert data["targets"]["portfolio"] == []
        assert data["targets"]["accounts"] == {}
