"""Merchant normalization helpers shared across modules."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

_TRAN10_RE = re.compile(r"\b\d{6,}\b")
_PHONE_RE = re.compile(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b")
_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_ORDER_PREFIX_RE = re.compile(r"^[A-Z0-9]+\s*\*\w+\s*", re.IGNORECASE)
_STRIP_PATTERNS = (_TRAN10_RE, _PHONE_RE, _DATE_RE, _URL_RE)


def normalize_merchant(merchant: str) -> str:
    """Return an uppercase, whitespace-collapsed merchant label."""

    cleaned = merchant.strip().upper()
    return " ".join(cleaned.split())


@lru_cache(maxsize=2048)
def merchant_pattern_key(merchant: str) -> str:
    """Return a reusable merchant key with volatile tokens stripped."""

    normalized = normalize_merchant(merchant)
    if not normalized:
        return normalized

    cleaned = _ORDER_PREFIX_RE.sub("", normalized)

    if "*" in cleaned:
        prefix, rest = cleaned.split("*", 1)
        rest = rest.lstrip()
        suffix = ""
        if rest:
            parts = rest.split(" ", 1)
            if len(parts) == 2:
                suffix = parts[1]
        cleaned = f"{prefix.strip()} {suffix.strip()}".strip()

    for pattern in _STRIP_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        tokens = normalized.split()
        if tokens:
            cleaned = tokens[0].split(".", 1)[0].strip()
    return cleaned[:80]


_OVERRIDES = (
    ("AMAZON", "Amazon"),
    ("AMZN", "Amazon"),
    ("INSTACART", "Instacart"),
    ("WHOLEFDS", "Whole Foods"),
    ("WHOLE FOODS", "Whole Foods"),
    ("YOUTUBE", "YouTube TV"),
    ("GOOGLE", "Google"),
    ("KINDLE", "Kindle"),
    ("TESLA", "Tesla"),
    ("TARGET", "Target"),
    ("COHO", "CoHo"),
)


def friendly_display_name(canonical: str, variants: Iterable[str]) -> str:
    candidate = canonical.upper()
    for needle, label in _OVERRIDES:
        if needle in candidate:
            return label
    for variant in variants:
        norm = normalize_merchant(variant)
        for needle, label in _OVERRIDES:
            if needle in norm:
                return label
        if norm:
            words = norm.split()
            if words:
                return words[0].title()
    if canonical:
        return canonical.split()[0].title()
    return "Unknown"

