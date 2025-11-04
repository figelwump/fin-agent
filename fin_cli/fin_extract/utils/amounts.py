"""Amount parsing and sign classification helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

_CURRENCY_RE = re.compile(r"[-−–]?[\d,.]+(?:\.\d+)?")


def parse_amount(value: str) -> float:
    """Parse currency strings into floats.

    Handles values such as ``-$1,234.56`` or ``(123.45)`` and normalises
    en/em dashes that appear in PDF extractions.
    """

    cleaned = (value or "").strip().replace(",", "")
    cleaned = cleaned.replace("–", "-").replace("−", "-")
    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    cleaned = cleaned.replace("$", "")
    match = _CURRENCY_RE.search(cleaned)
    if not match:
        raise ValueError(f"Empty amount in '{value}'")
    amount = float(match.group())
    return -amount if negative else amount


def normalize_token(value: str) -> str:
    """Normalise text for keyword comparisons."""

    cleaned = (value or "").lower()
    cleaned = cleaned.replace("•", "")
    return re.sub(r"[^a-z0-9\s]", "", cleaned)


def _matches(text: str, keywords: Iterable[str]) -> bool:
    normalized = normalize_token(text)
    return any(keyword in normalized for keyword in keywords if keyword)


@dataclass(slots=True)
class SignClassifier:
    """Determine transaction sign and filtering rules based on keywords."""

    treat_money_in_as_credit: bool = True
    treat_money_out_as_charge: bool = True
    default_positive: bool = True
    charge_keywords: set[str] = field(default_factory=set)
    credit_keywords: set[str] = field(default_factory=set)
    transfer_keywords: set[str] = field(default_factory=set)
    interest_keywords: set[str] = field(default_factory=set)
    card_payment_keywords: set[str] = field(default_factory=set)

    def classify(
        self,
        amount: float,
        *,
        description: str,
        type_value: str = "",
        money_in_value: str = "",
        money_out_value: str = "",
    ) -> float | None:
        """Return signed amount or ``None`` to drop the transaction."""

        if amount == 0:
            return None

        description_norm = normalize_token(description)
        type_norm = normalize_token(type_value)
        money_in_norm = normalize_token(money_in_value)
        money_out_norm = normalize_token(money_out_value)

        if self._matches_any(description_norm, type_norm, self.transfer_keywords):
            return None
        if self._matches_any(description_norm, type_norm, self.interest_keywords):
            return None
        if self._matches_any(description_norm, type_norm, self.card_payment_keywords):
            return None

        signed = None

        if self.treat_money_in_as_credit and money_in_value and not money_out_value:
            signed = -abs(amount)
        elif self.treat_money_out_as_charge and money_out_value and not money_in_value:
            signed = abs(amount)
        elif self._matches_any(description_norm, type_norm, self.credit_keywords, money_in_norm):
            signed = -abs(amount)
        elif self._matches_any(description_norm, type_norm, self.charge_keywords, money_out_norm):
            signed = abs(amount)

        if signed is None:
            signed = abs(amount) if self.default_positive else -abs(amount)

        return signed

    def _matches_any(
        self,
        description_norm: str,
        type_norm: str,
        keywords: Iterable[str],
        extra: str | None = None,
    ) -> bool:
        if not keywords:
            return False
        for keyword in keywords:
            if not keyword:
                continue
            if keyword in description_norm or keyword in type_norm:
                return True
            if extra and keyword in extra:
                return True
        return False
