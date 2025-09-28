"""Extractor autodetection utilities."""

from __future__ import annotations

from typing import Iterable

from fin_cli.shared.exceptions import UnsupportedFormatError

from .base import ExtractorRegistry, StatementExtractor
from .chase import ChaseExtractor
from .bofa import BankOfAmericaExtractor
from .mercury import MercuryExtractor

REGISTRY = ExtractorRegistry([ChaseExtractor, BankOfAmericaExtractor, MercuryExtractor])

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
    extractor = REGISTRY.detect(document, allowed_names=tuple(allowed_institutions) if allowed_institutions else None)
    if extractor is not None:
        return extractor

    probable = _infer_institution(getattr(document, "text", ""))
    allowed = tuple(allowed_institutions) if allowed_institutions is not None else REGISTRY.names()
    allowed_set = {name.lower() for name in allowed}
    if probable and probable not in allowed_set:
        raise UnsupportedFormatError(
            "Detected {friendly} statement but support is disabled via configuration.".format(
                friendly=FRIENDLY_NAMES.get(probable, probable.title()),
            )
        )
    supported_list = ", ".join(FRIENDLY_NAMES.get(name.lower(), name) for name in sorted(allowed_set))
    raise UnsupportedFormatError(
        "Unsupported statement format. Supported institutions: "
        f"{supported_list or 'none configured'}"
    )


def register_extractor(extractor: type[StatementExtractor]) -> None:
    REGISTRY.register(extractor)


def _infer_institution(text: str) -> str | None:
    lowered = text.lower()
    if "chase" in lowered:
        return "chase"
    if "bank of america" in lowered or "bofa" in lowered:
        return "bofa"
    if "mercury" in lowered:
        return "mercury"
    return None
