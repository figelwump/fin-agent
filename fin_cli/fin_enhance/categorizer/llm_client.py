"""LLM client for dynamic transaction categorization."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from fin_cli.shared.config import AppConfig
from fin_cli.shared.logging import Logger
from fin_cli.shared.merchants import merchant_pattern_key, normalize_merchant

TRANSACTION_ID_RE = re.compile(r"\b[A-Z0-9]{6,}\b")
PHONE_RE = re.compile(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b")
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
ORDER_PREFIX_RE = re.compile(r"^[A-Z0-9]+\s*\*\w+\s*", re.IGNORECASE)
STRIP_PATTERNS = (TRANSACTION_ID_RE, PHONE_RE, DATE_RE, URL_RE)


try:  # Optional dependency
    from openai import OpenAI  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - dependency optional at runtime
    OpenAI = None  # type: ignore


@dataclass(slots=True)
class LLMRequestItem:
    """Single merchant description to send to the LLM."""

    merchant: str
    original_description: str
    amount: float
    date: str


@dataclass(slots=True)
class LLMSuggestion:
    """Categorization suggestion returned by the LLM."""

    category: str
    subcategory: str
    confidence: float
    is_new_category: bool
    notes: str | None = None


@dataclass(slots=True)
class LLMResult:
    """Aggregated LLM result for a merchant."""

    merchant_normalized: str
    pattern_key: str | None = None
    pattern_display: str | None = None
    merchant_metadata: Mapping[str, Any] | None = None
    suggestions: list[LLMSuggestion] = field(default_factory=list)

class LLMClientError(RuntimeError):
    """Raised when the LLM client cannot fulfill a request."""





def _normalize_metadata(value: Any) -> dict[str, Any] | None:
    """Normalize arbitrary metadata payloads from the LLM."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, val in value.items():
            if key is None:
                continue
            normalized[str(key)] = val
        return normalized if normalized else None
    return None


class LLMClientError(RuntimeError):
    """Raised when the LLM client cannot fulfill a request."""





def _normalize_metadata(value: Any) -> dict[str, Any] | None:
    """Normalize arbitrary metadata payloads from the LLM."""

    if value is None:
        return None
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, val in value.items():
            if key is None:
                continue
            normalized[str(key)] = val
        return normalized if normalized else None
    return None


def normalize_merchant(merchant: str) -> str:
    """Return a normalized key for caching and batching purposes."""

    cleaned = merchant.strip().upper()
    return " ".join(cleaned.split())


def merchant_pattern_key(merchant: str) -> str:
    """Return a deterministic lookup key for merchant pattern learning.

    Cleans known volatile tokens (ticket IDs, phone numbers, dates, URLs, order
    prefixes) while retaining a stable brand token to reuse for future matches.
    """

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

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        tokens = normalized.split()
        if tokens:
            cleaned = tokens[0].split(".", 1)[0].strip()
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = normalized
    return cleaned[:80]

class LLMClient:
    """Thin wrapper around the configured LLM provider."""

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._model = config.categorization.llm.model
        self._provider = config.categorization.llm.provider.lower()
        self._enabled = bool(config.categorization.llm.enabled)
        self._api_key_env = config.categorization.llm.api_key_env
        self._client = None
        if self._enabled:
            self._client = self._bootstrap_client()

    @property
    def enabled(self) -> bool:
        return self._enabled and self._client is not None

    def _bootstrap_client(self) -> Any | None:
        if self._provider != "openai":
            self._logger.warning(
                f"LLM provider '{self._provider}' is not supported yet; disabling LLM categorization."
            )
            return None
        if OpenAI is None:
            self._logger.warning(
                "openai package is not installed. Install extras with 'pip install fin-cli[llm]' to enable LLM support."
            )
            return None
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            self._logger.warning(
                f"Environment variable {self._api_key_env} not set. Skipping LLM categorization."
            )
            return None
        try:
            return OpenAI(api_key=api_key)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.error(f"Failed to initialize OpenAI client: {exc}")
            return None
    def build_payload(
        self,
        items: Mapping[str, list[LLMRequestItem]],
        *,
        known_categories: Sequence[Mapping[str, str]] | None = None,
    ) -> str:
        """Create JSON payload describing merchants and transactions."""

        merchants: list[dict[str, Any]] = []
        for merchant_key, txn_items in items.items():
            merchants.append(
                {
                    "merchant_normalized": merchant_key,
                    "pattern_key": merchant_key,
                    "transactions": [
                        {
                            "merchant": item.merchant,
                            "original_description": item.original_description,
                            "amount": item.amount,
                            "date": item.date,
                        }
                        for item in txn_items
                    ],
                }
            )
        payload: dict[str, Any] = {"merchants": merchants}
        if known_categories:
            payload["known_categories"] = [
                {
                    "category": str(entry.get("category", "")).strip(),
                    "subcategory": str(entry.get("subcategory", "")).strip(),
                }
                for entry in known_categories
                if entry.get("category") and entry.get("subcategory")
            ]
        return json.dumps(payload, separators=(",", ":"))

    def categorize_batch(
        self,
        items: Mapping[str, list[LLMRequestItem]],
        *,
        known_categories: Sequence[Mapping[str, str]] | None = None,
        max_batch_merchants: int = 6,
    ) -> dict[str, LLMResult]:
        """Categorize merchants using the configured LLM.

        Returns mapping from merchant key to LLMResult. Merchants with errors are omitted.
        """

        if not self.enabled:
            return {}

        results: dict[str, LLMResult] = {}
        merchant_items = list(items.items())
        for start in range(0, len(merchant_items), max_batch_merchants):
            chunk = dict(merchant_items[start : start + max_batch_merchants])
            payload = self.build_payload(chunk, known_categories=known_categories)
            try:
                chunk_results = self._invoke_llm(payload)
            except LLMClientError as exc:
                self._logger.warning(f"LLM categorization failed for merchants {list(chunk)}: {exc}")
                continue
            results.update(chunk_results)
        return results

    def _invoke_llm(self, payload: str) -> dict[str, LLMResult]:
        if not self._client:
            raise LLMClientError("LLM client unavailable")
        try:
            self._logger.debug(f"LLM request payload bytes={len(payload)}")
            response = self._client.responses.create(  # type: ignore[attr-defined]
                model=self._model,
                input=self._build_prompt(payload),
                temperature=0.1,
                max_output_tokens=800,
            )
        except Exception as exc:  # pragma: no cover - network/SDK errors
            raise LLMClientError(str(exc)) from exc

        raw_output = self._extract_text(response)
        self._logger.debug(
            "LLM raw output preview: "
            f"{(raw_output[:500] + '…') if len(raw_output) > 500 else raw_output}"
        )

        cleaned_output = self._sanitize_llm_json(raw_output)

        try:
            data = json.loads(cleaned_output)
        except json.JSONDecodeError as exc:
            preview = raw_output[:500].strip()
            self._logger.warning(
                "LLM response was not valid JSON. Preview (first 500 chars): "
                f"{preview or '<empty response>'}"
            )
            raise LLMClientError(f"LLM returned invalid JSON: {exc}") from exc

        if not isinstance(data, Mapping) or "merchants" not in data:
            raise LLMClientError("LLM response missing 'merchants' list")

        results: dict[str, LLMResult] = {}
        merchants_data = data.get("merchants")
        if not isinstance(merchants_data, Iterable):
            raise LLMClientError("LLM 'merchants' payload is not iterable")
        for entry in merchants_data:
            if not isinstance(entry, Mapping):
                continue
            key_raw = entry.get("merchant_normalized") or entry.get("pattern_key")
            suggestions_data = entry.get("suggestions", [])
            if not key_raw or not isinstance(suggestions_data, Iterable):
                continue
            key_norm = normalize_merchant(str(key_raw))
            pattern_key_raw = entry.get("pattern_key")
            pattern_key_norm = (
                normalize_merchant(str(pattern_key_raw)) if pattern_key_raw else key_norm
            )
            if not pattern_key_norm:
                pattern_key_norm = key_norm
            pattern_display_raw = entry.get("pattern_display")
            pattern_display = (
                str(pattern_display_raw).strip() if pattern_display_raw else None
            )
            metadata_entry = entry.get("metadata")
            suggestions: list[LLMSuggestion] = []
            for suggestion in suggestions_data:
                if not isinstance(suggestion, Mapping):
                    continue
                category = str(suggestion.get("category", "")).strip()
                subcategory = str(suggestion.get("subcategory", "")).strip()
                if not category or not subcategory:
                    continue
                try:
                    confidence = float(suggestion.get("confidence", 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0
                is_new = bool(suggestion.get("is_new_category", False))
                notes = suggestion.get("notes")
                suggestions.append(
                    LLMSuggestion(
                        category=category,
                        subcategory=subcategory,
                        confidence=max(0.0, min(confidence, 1.0)),
                        is_new_category=is_new,
                        notes=str(notes) if notes else None,
                    )
                )
            if suggestions:
                results[key_norm] = LLMResult(
                    merchant_normalized=key_norm,
                    pattern_key=pattern_key_norm,
                    pattern_display=pattern_display,
                    merchant_metadata=_normalize_metadata(metadata_entry),
                    suggestions=suggestions,
                )
        return results

    def _build_prompt(self, payload_json: str) -> list[Dict[str, Any]]:
        system_prompt = (
            "You categorize financial transactions. Return JSON with a 'merchants' array. Each "
            "merchant must include: 'merchant_normalized' (echo of the provided key), 'pattern_key' "
            "(uppercase canonical brand with no ticket IDs, phone numbers, dates, URLs, or order "
            "numbers), 'pattern_display' (human-friendly label such as 'DoorDash • Dosa Point'), an "
            "optional 'metadata' object with enrichment fields (e.g., {'platform':'DoorDash', "
            "'restaurant_name':'Dosa Point'}), and 'suggestions'. Each suggestion must include "
            "'category', 'subcategory', 'confidence' (0-1 float), 'is_new_category' (boolean), and "
            "optional 'notes'. Use only the provided merchant data; do not invent amounts or dates."
        )
        user_prompt = (
            "Categorize these merchants. Reuse existing consumer finance category hierarchies "
            "whenever possible (e.g., 'Food & Dining' > 'Groceries'). Promote new categories only "
            "when no close match exists. Provide a stable canonical brand in 'pattern_key' and a "
            "friendly display name in 'pattern_display'."
        )
        # Responses API requires explicit block types (e.g., input_text) instead of bare strings.
        # The SDK no longer supports structured input blocks like input_json, so we inline
        # the JSON payload as plain text for the model to parse.
        try:
            compact_payload = json.dumps(json.loads(payload_json), separators=(",", ":"), ensure_ascii=False)
        except json.JSONDecodeError:  # Pragmatic fallback – should never happen
            compact_payload = payload_json

        return [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_prompt},
                    {
                        "type": "input_text",
                        "text": f"Merchant batch JSON (compact):\n{compact_payload}",
                    },
                ],
            },
        ]

    def _extract_text(self, response: Any) -> str:
        """Extract the text payload from the OpenAI Responses API reply."""

        # Newer SDKs expose a convenience attribute that aggregates textual output.
        output_text = getattr(response, "output_text", None)
        if output_text:
            if isinstance(output_text, list):
                return "".join(str(part) for part in output_text)
            if isinstance(output_text, str):
                return output_text

        try:
            return response.output[0].content[0].text  # type: ignore[index]
        except Exception as exc:  # pragma: no cover - SDK compatibility guard
            raise LLMClientError(f"Unexpected LLM response structure: {exc}") from exc

    def _sanitize_llm_json(self, raw: str) -> str:
        """Remove Markdown fences or other wrappers around JSON responses."""

        text = raw.strip()
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                # Drop the opening fence (and optional language hint) + closing fence if present.
                remainder = text[first_newline + 1 :]
                closing = remainder.rfind("```")
                if closing != -1:
                    remainder = remainder[:closing]
                text = remainder.strip()
        return text


def serialize_llm_results(results: Mapping[str, LLMResult]) -> str:
    """Serialize LLM results for caching."""

    merchants: list[dict[str, Any]] = []
    for key, result in results.items():
        merchant_key = result.merchant_normalized or key
        entry: dict[str, Any] = {
            "merchant_normalized": merchant_key,
            "pattern_key": result.pattern_key or merchant_key,
            "suggestions": [
                {
                    "category": suggestion.category,
                    "subcategory": suggestion.subcategory,
                    "confidence": suggestion.confidence,
                    "is_new_category": suggestion.is_new_category,
                    "notes": suggestion.notes,
                }
                for suggestion in result.suggestions
            ],
        }
        if result.pattern_display:
            entry["pattern_display"] = result.pattern_display
        if result.merchant_metadata:
            entry["metadata"] = dict(result.merchant_metadata)
        merchants.append(entry)

    payload = {"merchants": merchants}
    return json.dumps(payload, ensure_ascii=False)


def deserialize_llm_results(raw: str) -> dict[str, LLMResult]:
    """Deserialize cached LLM results."""

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, Mapping):
        return {}
    merchants = data.get("merchants")
    if not isinstance(merchants, Iterable):
        return {}
    results: dict[str, LLMResult] = {}
    for entry in merchants:
        if not isinstance(entry, Mapping):
            continue
        key_raw = entry.get("merchant_normalized") or entry.get("pattern_key")
        suggestions_data = entry.get("suggestions", [])
        if not key_raw or not isinstance(suggestions_data, Iterable):
            continue
        key_norm = normalize_merchant(str(key_raw))
        pattern_key_raw = entry.get("pattern_key")
        pattern_key_norm = normalize_merchant(str(pattern_key_raw)) if pattern_key_raw else key_norm
        pattern_display_raw = entry.get("pattern_display")
        metadata_entry = entry.get("metadata")

        suggestions: list[LLMSuggestion] = []
        for suggestion in suggestions_data:
            if not isinstance(suggestion, Mapping):
                continue
            category = str(suggestion.get("category", "")).strip()
            subcategory = str(suggestion.get("subcategory", "")).strip()
            if not category or not subcategory:
                continue
            try:
                confidence = float(suggestion.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            suggestions.append(
                LLMSuggestion(
                    category=category,
                    subcategory=subcategory,
                    confidence=max(0.0, min(confidence, 1.0)),
                    is_new_category=bool(suggestion.get("is_new_category", False)),
                    notes=str(suggestion.get("notes")) if suggestion.get("notes") else None,
                )
            )
        if suggestions:
            results[key_norm] = LLMResult(
                merchant_normalized=key_norm,
                pattern_key=pattern_key_norm or key_norm,
                pattern_display=str(pattern_display_raw).strip() if pattern_display_raw else None,
                merchant_metadata=_normalize_metadata(metadata_entry),
                suggestions=suggestions,
            )
    return results
