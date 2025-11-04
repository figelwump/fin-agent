"""Extractor autodetection utilities."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from fin_cli.shared.exceptions import UnsupportedFormatError

from .base import ExtractorRegistry, StatementExtractor
from .bofa import BankOfAmericaExtractor
from .chase import ChaseExtractor
from .mercury import MercuryExtractor

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from ..plugin_loader import PluginLoadReport

REGISTRY = ExtractorRegistry([ChaseExtractor, BankOfAmericaExtractor, MercuryExtractor])

_LOGGER = logging.getLogger(__name__)
_BUNDLED_SPEC_REPORT: PluginLoadReport | None = None


def ensure_bundled_specs_loaded() -> PluginLoadReport:
    """Load bundled declarative specs once and return the report."""

    global _BUNDLED_SPEC_REPORT
    if _BUNDLED_SPEC_REPORT is None:
        from ..plugin_loader import load_bundled_specs

        report = load_bundled_specs(REGISTRY)
        for event in report.failures:
            _LOGGER.warning("Failed to load bundled extractor %s: %s", event.source, event.message)
        for event in report.skipped:
            _LOGGER.debug(
                "Skipped bundled extractor %s (%s)",
                event.source,
                event.message or "already registered",
            )
        _BUNDLED_SPEC_REPORT = report
    return _BUNDLED_SPEC_REPORT


__all__ = (
    "REGISTRY",
    "FRIENDLY_NAMES",
    "detect_extractor",
    "ensure_bundled_specs_loaded",
    "register_extractor",
    "_BUNDLED_SPEC_REPORT",
)

FRIENDLY_NAMES: dict[str, str] = {
    "chase": "Chase",
    "bofa": "Bank of America",
    "mercury": "Mercury",
}


def detect_extractor(
    document,
    *,
    allowed_institutions: Iterable[str] | None = None,
) -> StatementExtractor:
    ensure_bundled_specs_loaded()
    allowed = tuple(allowed_institutions) if allowed_institutions is not None else REGISTRY.names()
    allowed_set = {name.lower() for name in allowed}

    probable = _infer_institution(getattr(document, "text", ""))
    matches: list[StatementExtractor] = []

    for extractor_cls in REGISTRY.iter_types(include_alternates=True):
        if allowed_set and extractor_cls.name.lower() not in allowed_set:
            continue
        extractor = extractor_cls()
        try:
            supported = extractor.supports(document)
        except Exception:  # pragma: no cover - defensive against extractor bugs
            supported = False
        if supported:
            matches.append(extractor)

    if matches:
        if probable:
            for extractor in matches:
                if extractor.name == probable:
                    return extractor
        return matches[0]

    if probable and probable not in allowed_set:
        raise UnsupportedFormatError(
            f"Detected {FRIENDLY_NAMES.get(probable, probable.title())} statement but support is disabled via configuration."
        )
    supported_list = ", ".join(
        FRIENDLY_NAMES.get(name.lower(), name) for name in sorted(allowed_set)
    )
    raise UnsupportedFormatError(
        "Unsupported statement format. Supported institutions: "
        f"{supported_list or 'none configured'}"
    )


def register_extractor(
    extractor: type[StatementExtractor],
    *,
    allow_override: bool = False,
):
    """Register an extractor type with optional precedence override."""

    REGISTRY.register(extractor, allow_override=allow_override)


def _infer_institution(text: str) -> str | None:
    lowered = text.lower()
    if "mercury" in lowered:
        return "mercury"
    if "bank of america" in lowered or "bofa" in lowered:
        return "bofa"
    if "chase" in lowered:
        return "chase"
    return None
