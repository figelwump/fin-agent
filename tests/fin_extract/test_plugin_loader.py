from __future__ import annotations

from pathlib import Path

from fin_cli.fin_extract import extractors as extractor_module
from fin_cli.fin_extract.extractors.base import ExtractorRegistry, StatementExtractor
from fin_cli.fin_extract.plugin_loader import load_user_plugins


def test_bundled_specs_loaded_without_failures() -> None:
    report = extractor_module.ensure_bundled_specs_loaded()
    assert not report.failures
    primaries = {extractor.name: extractor for extractor in extractor_module.REGISTRY.iter_types()}
    for bank in ("chase", "bofa", "mercury"):
        primary = primaries[bank]
        assert getattr(primary, "__plugin_kind__") == "bundled_yaml"
        alternates = extractor_module.REGISTRY.alternates_for(bank)
        assert any(getattr(alt, "__plugin_kind__") == "builtin_python" for alt in alternates)


class BuiltinExtractor(StatementExtractor):
    name = "builtin"

    def supports(self, document) -> bool:  # pragma: no cover - not invoked in tests
        return False

    def extract(self, document):  # pragma: no cover - not invoked in tests
        raise NotImplementedError


def _write_yaml_plugin(path: Path, *, name: str = "custom") -> None:
    path.write_text(
        """
name: {name}
institution: Test Bank
account_type: checking
columns:
  date:
    aliases: ["date"]
  description:
    aliases: ["description"]
  amount:
    aliases: ["amount"]
dates:
  formats: ["%Y-%m-%d"]
sign_classification:
  method: "keywords"
  charge_keywords: []
  credit_keywords: []
  transfer_keywords: []
  interest_keywords: []
  card_payment_keywords: []
""".strip().format(name=name),
        encoding="utf-8",
    )


def test_load_user_yaml_plugin_registers(tmp_path: Path) -> None:
    plugin_path = tmp_path / "bank.yaml"
    _write_yaml_plugin(plugin_path, name="custom_bank")

    registry = ExtractorRegistry([BuiltinExtractor])
    report = load_user_plugins(registry, [tmp_path])

    assert any(event.status == "registered" and event.name == "custom_bank" for event in report.events)
    assert registry.names() == ("builtin", "custom_bank")
    yaml_extractor = next(
        extractor
        for extractor in registry.iter_types(include_alternates=True)
        if extractor.name == "custom_bank"
    )
    assert getattr(yaml_extractor, "__plugin_kind__") == "user_yaml"
    assert getattr(yaml_extractor, "__origin__") == str(plugin_path)


def test_load_user_yaml_plugin_duplicate_skips(tmp_path: Path) -> None:
    plugin_path = tmp_path / "dup.yaml"
    _write_yaml_plugin(plugin_path, name="builtin")

    registry = ExtractorRegistry([BuiltinExtractor])
    report = load_user_plugins(registry, [tmp_path])

    duplicate_event = next(event for event in report.events if event.source == str(plugin_path))
    assert duplicate_event.status == "skipped"
    assert duplicate_event.message


def test_load_python_plugin_registers(tmp_path: Path) -> None:
    plugin_path = tmp_path / "plugin.py"
    plugin_path.write_text(
        """
from fin_cli.fin_extract.extractors.base import StatementExtractor
from fin_cli.fin_extract.types import ExtractionResult, StatementMetadata


class MyPlugin(StatementExtractor):
    name = "plugin_bank"

    def supports(self, document):
        return True

    def extract(self, document):
        metadata = StatementMetadata(
            institution="Plugin Bank",
            account_name="Plugin",
            account_type="checking",
            start_date=None,
            end_date=None,
        )
        return ExtractionResult(metadata=metadata, transactions=[])
""".strip(),
        encoding="utf-8",
    )

    registry = ExtractorRegistry([BuiltinExtractor])
    report = load_user_plugins(registry, [tmp_path])

    assert any(event.status == "registered" and event.name == "plugin_bank" for event in report.events)
    assert "plugin_bank" in registry.names()
    plugin_extractor = next(
        extractor
        for extractor in registry.iter_types(include_alternates=True)
        if extractor.name == "plugin_bank"
    )
    assert getattr(plugin_extractor, "__plugin_kind__") == "python_user"
    assert str(tmp_path / "plugin.py") == getattr(plugin_extractor, "__origin__")


def test_allowlist_filters_plugins(tmp_path: Path) -> None:
    allowed_plugin = tmp_path / "allowed.yaml"
    blocked_plugin = tmp_path / "blocked.yaml"
    _write_yaml_plugin(allowed_plugin, name="good")
    _write_yaml_plugin(blocked_plugin, name="skipme")

    registry = ExtractorRegistry([BuiltinExtractor])
    report = load_user_plugins(registry, [tmp_path], allowed_names={"good"})

    registered = [event.name for event in report.registered]
    assert registered == ["good"]
    skipped = [event for event in report.skipped if event.name == "skipme"]
    assert skipped and skipped[0].message == "not in allowed plugin list"


def test_blocklist_filters_plugins(tmp_path: Path) -> None:
    plugin_path = tmp_path / "blocked.yaml"
    _write_yaml_plugin(plugin_path, name="blocked")

    registry = ExtractorRegistry([BuiltinExtractor])
    report = load_user_plugins(registry, [tmp_path], blocked_names={"blocked"})

    assert not report.registered
    skipped = [event for event in report.skipped if event.name == "blocked"]
    assert skipped and skipped[0].message == "blocked by configuration"
