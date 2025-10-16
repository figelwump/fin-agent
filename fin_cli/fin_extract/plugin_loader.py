"""Plugin discovery and loading utilities for fin-extract."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Iterable, Iterator, Sequence, TYPE_CHECKING

import yaml

from .extractors.base import ExtractorRegistry, RegistrationResult, StatementExtractor

_LOGGER = logging.getLogger(__name__)
_DECLARATIVE_MODULE: ModuleType | None = None

if TYPE_CHECKING:  # pragma: no cover - import only for static type checking
    from .declarative import DeclarativeExtractor, DeclarativeSpec


def _get_declarative_module() -> ModuleType:
    """Return the declarative module, importing lazily to avoid circular imports."""

    global _DECLARATIVE_MODULE
    if _DECLARATIVE_MODULE is None:
        from . import declarative as declarative_module  # local import to defer load

        _DECLARATIVE_MODULE = declarative_module
    return _DECLARATIVE_MODULE


@dataclass(frozen=True)
class PluginLoadEvent:
    """Represents a single plugin load outcome."""

    source: str
    kind: str
    status: str
    name: str | None = None
    became_primary: bool = False
    replaced_existing: bool = False
    message: str | None = None


@dataclass
class PluginLoadReport:
    """Aggregate report for a plugin discovery run."""

    events: list[PluginLoadEvent] = field(default_factory=list)

    @property
    def registered(self) -> list[PluginLoadEvent]:
        return [event for event in self.events if event.status == "registered"]

    @property
    def failures(self) -> list[PluginLoadEvent]:
        return [event for event in self.events if event.status == "error"]

    @property
    def skipped(self) -> list[PluginLoadEvent]:
        return [event for event in self.events if event.status == "skipped"]

    def extend(self, events: Iterable[PluginLoadEvent]) -> None:
        self.events.extend(events)

    def add(self, event: PluginLoadEvent) -> None:
        self.events.append(event)


def load_bundled_specs(
    registry: ExtractorRegistry,
    *,
    allow_override: bool = False,
) -> PluginLoadReport:
    """Load declarative specs bundled with the package."""

    report = PluginLoadReport()
    package = "fin_cli.fin_extract.bundled_specs"
    try:
        traversable = resources.files(package)
    except ModuleNotFoundError:
        _LOGGER.debug("Bundled specs package %s not found", package)
        return report

    for resource in traversable.iterdir():
        if not resource.name.lower().endswith((".yaml", ".yml")):
            continue
        event = _register_declarative_resource(
            resource,
            registry,
            origin=f"bundled::{resource.name}",
            allow_override=True,
            kind="bundled_yaml",
        )
        report.add(event)
    return report


def load_user_plugins(
    registry: ExtractorRegistry,
    roots: Sequence[str | Path],
    *,
    allow_override: bool = False,
    allowed_names: set[str] | None = None,
    blocked_names: set[str] | None = None,
) -> PluginLoadReport:
    """Discover and load user-supplied plugins from the provided roots."""

    report = PluginLoadReport()
    for root in roots:
        path = Path(root).expanduser()
        if not path.exists():
            _LOGGER.debug("Plugin root %s does not exist; skipping", path)
            continue
        for plugin_path in _iter_plugin_files(path):
            suffix = plugin_path.suffix.lower()
            if suffix in {".yaml", ".yml"}:
                event = _register_declarative_path(
                    plugin_path,
                    registry,
                    allow_override=allow_override,
                    kind="user_yaml",
                    allowed_names=allowed_names,
                    blocked_names=blocked_names,
                )
                report.add(event)
            elif suffix == ".py":
                events = _register_python_module(
                    plugin_path,
                    registry,
                    allow_override=allow_override,
                    allowed_names=allowed_names,
                    blocked_names=blocked_names,
                )
                report.extend(events)
    return report


def _iter_plugin_files(root: Path) -> Iterator[Path]:
    """Yield candidate plugin files under *root*."""

    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() in {".py", ".yaml", ".yml"}:
            yield path


def _register_declarative_path(
    path: Path,
    registry: ExtractorRegistry,
    *,
    allow_override: bool,
    kind: str,
    allowed_names: set[str] | None,
    blocked_names: set[str] | None,
) -> PluginLoadEvent:
    try:
        declarative_module = _get_declarative_module()
        spec = declarative_module.load_spec(path)
    except Exception as exc:  # pragma: no cover - defensive logging path
        _LOGGER.exception("Failed to load declarative spec at %s", path)
        return PluginLoadEvent(
            source=str(path),
            kind=kind,
            status="error",
            message=_format_exception(exc),
        )

    decision = _enforce_name_policy(spec.name, allowed_names, blocked_names)
    if decision is not None:
        return PluginLoadEvent(
            source=str(path),
            kind=kind,
            status="skipped",
            name=spec.name,
            message=decision,
        )

    extractor_type = _make_declarative_type(spec, origin=str(path), source_kind=kind)
    result = registry.register(extractor_type, allow_override=allow_override)
    status, message = _status_from_registration(result)
    return PluginLoadEvent(
        source=str(path),
        kind=kind,
        status=status,
        name=spec.name,
        became_primary=result.became_primary,
        replaced_existing=result.replaced_existing,
        message=message,
    )


def _register_declarative_resource(
    resource: resources.abc.Traversable,
    registry: ExtractorRegistry,
    *,
    origin: str,
    allow_override: bool,
    kind: str,
) -> PluginLoadEvent:
    try:
        data = resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - defensive logging path
        _LOGGER.exception("Bundled spec resource %s could not be read", origin)
        return PluginLoadEvent(
            source=origin,
            kind=kind,
            status="error",
            message=_format_exception(exc),
        )

    try:
        payload = yaml.safe_load(data) or {}
        declarative_module = _get_declarative_module()
        spec = declarative_module._parse_spec(payload)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - defensive logging path
        _LOGGER.exception("Bundled spec resource %s failed validation", origin)
        return PluginLoadEvent(
            source=origin,
            kind=kind,
            status="error",
            message=_format_exception(exc),
        )

    extractor_type = _make_declarative_type(spec, origin=origin, source_kind=kind)
    result = registry.register(extractor_type, allow_override=allow_override)
    status, message = _status_from_registration(result)
    return PluginLoadEvent(
        source=origin,
        kind=kind,
        status=status,
        name=spec.name,
        became_primary=result.became_primary,
        replaced_existing=result.replaced_existing,
        message=message,
    )


def _register_python_module(
    path: Path,
    registry: ExtractorRegistry,
    *,
    allow_override: bool,
    allowed_names: set[str] | None,
    blocked_names: set[str] | None,
) -> list[PluginLoadEvent]:
    module_name = _module_name_for_path(path)
    events: list[PluginLoadEvent] = []

    sys_path_added = False
    path_parent = str(path.parent)
    if path_parent not in sys.path:
        sys.path.insert(0, path_parent)
        sys_path_added = True

    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to create loader for {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - defensive logging path
        _LOGGER.exception("Failed to import plugin module %s", path)
        events.append(
            PluginLoadEvent(
                source=str(path),
                kind="python",
                status="error",
                message=_format_exception(exc),
            )
        )
        return events
    finally:
        if sys_path_added:
            try:
                sys.path.remove(path_parent)
            except ValueError:  # pragma: no cover - defensive cleanup
                pass

    extractor_types = _extractor_types_from_module(module)
    if not extractor_types:
        events.append(
            PluginLoadEvent(
                source=str(path),
                kind="python",
                status="skipped",
                message="No StatementExtractor subclasses found",
            )
        )
        return events

    for extractor_type in extractor_types:
        decision = _enforce_name_policy(extractor_type.name, allowed_names, blocked_names)
        if decision is not None:
            events.append(
                PluginLoadEvent(
                    source=f"{path}::{extractor_type.__name__}",
                    kind="python",
                    status="skipped",
                    name=extractor_type.name,
                    message=decision,
                )
            )
            continue

        setattr(extractor_type, "__origin__", str(path))
        setattr(extractor_type, "__plugin_kind__", "python_user")
        result = registry.register(extractor_type, allow_override=allow_override)
        status, message = _status_from_registration(result)
        events.append(
            PluginLoadEvent(
                source=f"{path}::{extractor_type.__name__}",
                kind="python",
                status=status,
                name=extractor_type.name,
                became_primary=result.became_primary,
                replaced_existing=result.replaced_existing,
                message=message,
            )
        )

    return events


def _make_declarative_type(
    spec: "DeclarativeSpec",
    *,
    origin: str,
    source_kind: str,
) -> type["DeclarativeExtractor"]:
    declarative_module = _get_declarative_module()
    base_cls = declarative_module.DeclarativeExtractor
    spec_copy = copy.deepcopy(spec)

    class _DeclarativePluginExtractor(base_cls):
        name = spec_copy.name

        def __init__(self) -> None:
            super().__init__(copy.deepcopy(spec_copy))

    _DeclarativePluginExtractor.__module__ = "fin_cli.fin_extract.plugins"
    _DeclarativePluginExtractor.__qualname__ = f"DeclarativeExtractor[{spec_copy.name}]"
    setattr(_DeclarativePluginExtractor, "__origin__", origin)
    setattr(_DeclarativePluginExtractor, "__plugin_kind__", source_kind)
    return _DeclarativePluginExtractor


def _module_name_for_path(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"fin_user_plugins.{digest}"


def _extractor_types_from_module(module: ModuleType) -> list[type[StatementExtractor]]:
    candidates: list[type[StatementExtractor]] = []
    for attribute in vars(module).values():
        if not inspect.isclass(attribute):
            continue
        if not issubclass(attribute, StatementExtractor) or attribute is StatementExtractor:
            continue
        if inspect.isabstract(attribute):
            continue
        candidates.append(attribute)
    return candidates


def _status_from_registration(result: RegistrationResult) -> tuple[str, str | None]:
    if result.became_primary:
        if result.replaced_existing:
            return "registered", "Replaced previously registered extractor"
        return "registered", None
    return "skipped", "Existing extractor takes precedence"


def _format_exception(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def _enforce_name_policy(
    name: str,
    allowed_names: set[str] | None,
    blocked_names: set[str] | None,
) -> str | None:
    lowered = name.lower()
    if blocked_names and lowered in blocked_names:
        return "blocked by configuration"
    if allowed_names is not None and lowered not in allowed_names:
        return "not in allowed plugin list"
    return None
