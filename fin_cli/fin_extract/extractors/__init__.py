"""Extractor autodetection utilities."""

from __future__ import annotations

from .base import ExtractorRegistry, StatementExtractor
from .chase import ChaseExtractor

REGISTRY = ExtractorRegistry([ChaseExtractor])


def detect_extractor(document) -> StatementExtractor | None:
    return REGISTRY.detect(document)


def register_extractor(extractor: type[StatementExtractor]) -> None:
    REGISTRY.register(extractor)
