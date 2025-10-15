
"""Merchant normalization helpers shared across modules."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable

TRANSACTION_ID_RE = re.compile(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{4,}\b")
PHONE_RE = re.compile(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b")
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
ORDER_PREFIX_RE = re.compile(r"^[A-Z0-9]+\s*\*\w+\s*", re.IGNORECASE)
HASH_NUMBER_RE = re.compile(r"#\d{2,}")
DOMAIN_SUFFIX_RE = re.compile(r"\b([A-Z0-9]+)\.(COM|NET|ORG|CO|IO|AI|EDU|GOV)\b")
STRIP_PATTERNS = (PHONE_RE, DATE_RE, URL_RE, TRANSACTION_ID_RE)

AGGREGATOR_LABELS: dict[str, str] = {
    "LYFT": "Lyft",
    "UBER": "Uber",
    "DOORDASH": "DoorDash",
    "INSTACART": "Instacart",
    "AIRBNB": "Airbnb",
    "UNITED AIRLINES": "United Airlines",
    "UNITED": "United Airlines",
    "ALASKA AIRLINES": "Alaska Airlines",
    "ALASKA": "Alaska Airlines",
    "DELTA": "Delta Air Lines",
    "SOUTHWEST": "Southwest Airlines",
}

GENERIC_PLATFORMS = {"TST", "SQ", "SQUARE", "N/A", "AIRPORT DINING"}


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

    cleaned = ORDER_PREFIX_RE.sub("", normalized)

    if "*" in cleaned:
        prefix, rest = cleaned.split("*", 1)
        rest = rest.lstrip()
        suffix = ""
        if rest:
            parts = rest.split(" ", 1)
            if len(parts) == 2:
                suffix = parts[1]
        cleaned = f"{prefix.strip()} {suffix.strip()}".strip()

    for pattern in STRIP_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    cleaned = DOMAIN_SUFFIX_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"\.(COM|NET|ORG|CO|IO|AI|EDU|GOV)\b", " ", cleaned)
    cleaned = HASH_NUMBER_RE.sub(" ", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        tokens = normalized.split()
        if tokens:
            cleaned = tokens[0].split(".", 1)[0].strip()
    return cleaned[:80]


def friendly_display_name(canonical: str, variants: Iterable[str]) -> str:
    """Fallback display name derived from canonical key and observed variants."""

    candidates = [variant for variant in variants if variant]
    if canonical:
        candidates.append(canonical)

    for value in candidates:
        cleaned = value.strip()
        if not cleaned:
            continue
        if "•" in cleaned:
            parts = [part.strip().title() for part in cleaned.split("•") if part.strip()]
            if parts:
                return " • ".join(parts)
        if cleaned.isupper() and len(cleaned) > 3:
            return cleaned.title()
        if len(cleaned.split()) > 1:
            return cleaned.title()
        return cleaned.capitalize()
    return canonical.title() if canonical else "Unknown"
