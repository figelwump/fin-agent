"""fin-scrub CLI entrypoint."""

from __future__ import annotations

import importlib.resources as pkg_resources
import re
import sys
import warnings
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import yaml

try:
    from cryptography.utils import CryptographyDeprecationWarning
except Exception:  # pragma: no cover - cryptography is optional until PDF parsing runs
    CryptographyDeprecationWarning = DeprecationWarning  # type: ignore[assignment]

# Suppress the noisy ARC4 deprecation warning emitted by pypdf before pdfplumber loads.
warnings.filterwarnings(
    "ignore",
    message="ARC4 has been moved",
    category=CryptographyDeprecationWarning,
    module="pypdf._crypt_providers._cryptography",
)

from fin_cli.fin_extract.parsers.pdf_loader import load_pdf_document_with_engine
from fin_cli.shared.utils import compute_file_sha256


def _luhn_checksum(number: str) -> bool:
    digits = [int(ch) for ch in number if ch.isdigit()]
    if len(digits) != len(number):
        return False
    checksum = 0
    parity = len(digits) % 2
    for idx, value in enumerate(digits):
        if idx % 2 == parity:
            doubled = value * 2
            if doubled > 9:
                doubled -= 9
            checksum += doubled
        else:
            checksum += value
    return checksum % 10 == 0


@dataclass(slots=True)
class ScrubStats:
    """Collects replacement counts for auditing."""

    counts: dict[str, int] = field(default_factory=dict)

    def increment(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1

    def merge(self, other: ScrubStats) -> None:
        for key, value in other.counts.items():
            self.counts[key] = self.counts.get(key, 0) + value


class RegexRule:
    """Applies a compiled regex and replacement callback."""

    def __init__(
        self, pattern: re.Pattern[str], handler: Callable[[re.Match[str], ScrubStats], str]
    ):
        self.pattern = pattern
        self.handler = handler

    def apply(self, text: str, stats: ScrubStats) -> str:
        return self.pattern.sub(lambda match: self.handler(match, stats), text)


_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_ROUTING_PATTERN = re.compile(r"((?:routing|aba)[^0-9]{0,10})(\d{9})(?!\d)", re.IGNORECASE)
_ACCOUNT_PATTERN = re.compile(r"((?:account|acct)[^0-9]{0,10})(\d{6,})(?!\d)", re.IGNORECASE)
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b")
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)")
_CUSTOMER_ID_PATTERN = re.compile(r"(customer id[:#\s]*)(\w{6,})", re.IGNORECASE)
_CARD_SUFFIX_PATTERN = re.compile(r"(ending in\s*)(\d{4})(?!\d)", re.IGNORECASE)
_STREET_PATTERN = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.#\-']+(?:\s+[A-Za-z0-9.#\-']+){0,4}\s+"
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Court|Ct\.?|Lane|Ln\.?|Drive|Dr\.?|Way|Boulevard|Blvd\.?|Place|Pl\.?|Circle|Cir\.?|Terrace|Ter\.?|Parkway|Pkwy\.?)\b",
    re.IGNORECASE,
)
_CITY_STATE_PATTERN = re.compile(
    r"\b[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*(?:,\s*|\s+)[A-Z]{2}\s*\d{5}(?:-\d{4})?\b"
)
_NAME_PATTERN = re.compile(r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){1,2}\b")
_DEFAULT_TRANSACTION_PATTERNS = [
    re.compile(r"^\s*\d{1,2}/\d{1,2}(?:\s+\d{1,2}/\d{1,2})?\s+.+?\s+[-\$\(\)0-9.,]+$"),
    re.compile(
        r"^\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2}.*\d[\d,]*\.\d{2}",
        re.IGNORECASE,
    ),
]
_DEFAULT_PAGE_HEADER_PATTERNS = [re.compile(r"\bPage\s*\d+\s*of\s*\d+\b", re.IGNORECASE)]
_DEFAULT_PAGE_FOOTER_PATTERNS = [re.compile(r"continued on next page", re.IGNORECASE)]

CONFIG_DIR = Path.home() / ".finagent"
USER_CONFIG_PATH = CONFIG_DIR / "fin-scrub.yaml"
DEFAULT_CONFIG_FILE = "default_config.yaml"

TRANSACTION_PATTERNS: list[re.Pattern[str]] = []
PAGE_HEADER_PATTERNS: list[re.Pattern[str]] = []
PAGE_FOOTER_PATTERNS: list[re.Pattern[str]] = []
PLACEHOLDERS: dict[str, str] = {}
SCRUBADUB_PLACEHOLDERS: dict[str, tuple[str, str, str]] = {}
DISABLED_FILTH_TYPES: set[str] = set()
NAME_SKIP_WORDS: set[str] = set()
REGEX_RULES: list[RegexRule] = []
DETECTORS: dict[str, bool] = {}

DEFAULT_PLACEHOLDERS: dict[str, str] = {
    "NAME": "[NAME]",
    "ADDRESS": "[ADDRESS]",
    "ACCOUNT_NUMBER": "[ACCOUNT_NUMBER]",
    "ACCOUNT_LAST4": "[ACCOUNT_LAST4:{last4}]",
    "CARD_NUMBER": "[CARD_NUMBER]",
    "CARD_NUMBER_LAST4": "[CARD_NUMBER_LAST4:{last4}]",
    "ROUTING_NUMBER": "[ROUTING_NUMBER]",
    "SSN": "[SSN]",
    "EMAIL": "[EMAIL]",
    "URL": "[URL]",
    "CUSTOMER_ID": "[CUSTOMER_ID]",
    "PII": "[PII]",
    "SECRET": "[SECRET]",
    "IP": "[IP]",
}

DEFAULT_DETECTORS: dict[str, bool] = {
    "scrub_name": True,
    "scrub_address": True,
    "scrub_email": True,
    "scrub_url": True,
    "scrub_phone": False,
    "scrub_customer_id": True,
    "scrub_ssn": True,
}

DEFAULT_NAME_SKIP_WORDS = {
    "account",
    "accounts",
    "statement",
    "statements",
    "monthly",
    "interest",
    "fees",
    "fee",
    "balance",
    "balances",
    "withdrawals",
    "withdrawal",
    "deposits",
    "deposit",
    "charges",
    "charge",
    "total",
    "activity",
    "routing",
    "number",
    "numbers",
    "all",
    "dates",
    "utc",
    "beginning",
    "preauthorized",
    "closing",
    "period",
    "summary",
    "payment",
    "payments",
    "due",
    "days",
    "customer",
    "service",
    "information",
    "address",
    "visa",
    "signature",
    "account#",
    "bank",
    "america",
    "available",
    "line",
    "credit",
    "minimum",
    "warning",
    "billing",
    "cycle",
    "september",
    "august",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "october",
    "november",
    "december",
    "target",
    "com",
    "inc",
    "corp",
    "llc",
    "health",
    "autopay",
}

DEFAULT_FILTH_PLACEHOLDERS: dict[str, str] = {
    "email": "EMAIL",
    "name": "NAME",
    "address": "ADDRESS",
    "location": "ADDRESS",
    "street": "ADDRESS",
    "credit_card": "CARD_NUMBER",
    "ssn": "SSN",
    "ipv4": "IP",
    "ipv6": "IP",
    "password": "SECRET",
    "default": "PII",
}


def _compile_pattern_entry(entry: Any) -> re.Pattern[str]:
    if isinstance(entry, str):
        return re.compile(entry)
    if isinstance(entry, dict):
        pattern = entry.get("pattern")
        if not pattern:
            raise click.ClickException("Invalid regex entry: missing 'pattern'")
        flags_value = 0
        for flag_name in entry.get("flags", []) or []:
            if not hasattr(re, flag_name):
                raise click.ClickException(f"Invalid regex flag '{flag_name}'")
            flags_value |= getattr(re, flag_name)
        return re.compile(pattern, flags_value)
    raise click.ClickException("Regex pattern entries must be strings or mappings")


def _compile_pattern_list(
    entries: Any, default_patterns: list[re.Pattern[str]]
) -> list[re.Pattern[str]]:
    if not entries:
        return default_patterns
    if not isinstance(entries, list):
        entries = [entries]
    compiled: list[re.Pattern[str]] = []
    for entry in entries:
        compiled.append(_compile_pattern_entry(entry))
    return compiled or default_patterns


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _deep_merge(base[key], value)
        elif key in base and isinstance(base[key], list) and isinstance(value, list):
            base[key] = base[key] + value
        else:
            base[key] = value
    return base


def _load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise click.ClickException(f"Failed to parse YAML config '{path}': {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise click.ClickException(f"Config file '{path}' must contain a mapping at the root")
    return raw


def _load_default_config() -> dict[str, Any]:
    try:
        data = (
            pkg_resources.files(__package__)
            .joinpath(DEFAULT_CONFIG_FILE)
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise click.ClickException("Missing bundled fin-scrub default configuration") from exc
    except AttributeError:
        # Fallback for Python versions without files(); should not happen on 3.11+.
        with pkg_resources.open_text(__package__, DEFAULT_CONFIG_FILE, encoding="utf-8") as fh:  # type: ignore[attr-defined]
            data = fh.read()
    try:
        loaded = yaml.safe_load(data) or {}
    except yaml.YAMLError as exc:
        raise click.ClickException("Bundled fin-scrub default configuration is invalid") from exc
    if not isinstance(loaded, dict):
        raise click.ClickException("Bundled fin-scrub default configuration must be a mapping")
    return loaded


def _render_placeholder(name: str, **kwargs: Any) -> str:
    template = PLACEHOLDERS.get(name.upper()) or PLACEHOLDERS.get(name) or f"[{name}]"
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
    return template


def _configure_runtime(config: dict[str, Any]) -> None:
    global TRANSACTION_PATTERNS, PAGE_HEADER_PATTERNS, PAGE_FOOTER_PATTERNS
    global PLACEHOLDERS, SCRUBADUB_PLACEHOLDERS, NAME_SKIP_WORDS, REGEX_RULES
    global DETECTORS, DISABLED_FILTH_TYPES

    TRANSACTION_PATTERNS = _compile_pattern_list(
        config.get("transaction_markers"), _DEFAULT_TRANSACTION_PATTERNS
    )
    page_reset = config.get("page_reset_markers", {}) or {}
    PAGE_HEADER_PATTERNS = _compile_pattern_list(
        page_reset.get("headers"), _DEFAULT_PAGE_HEADER_PATTERNS
    )
    PAGE_FOOTER_PATTERNS = _compile_pattern_list(
        page_reset.get("footers"), _DEFAULT_PAGE_FOOTER_PATTERNS
    )

    placeholders_cfg = config.get("placeholders", {}) or {}
    placeholders = deepcopy(DEFAULT_PLACEHOLDERS)
    placeholders.update({key.upper(): value for key, value in placeholders_cfg.items()})
    PLACEHOLDERS = placeholders

    detectors_cfg = deepcopy(DEFAULT_DETECTORS)
    detectors_cfg.update(
        {key: bool(value) for key, value in (config.get("detectors") or {}).items()}
    )
    DETECTORS = detectors_cfg

    skip_words = set(DEFAULT_NAME_SKIP_WORDS)
    for word in config.get("skip_words", {}).get("name", []) or []:
        skip_words.add(str(word).lower())
    NAME_SKIP_WORDS = skip_words

    DISABLED_FILTH_TYPES = set()
    if not DETECTORS.get("scrub_name", True):
        DISABLED_FILTH_TYPES.update({"name"})
    if not DETECTORS.get("scrub_address", True):
        DISABLED_FILTH_TYPES.update({"address", "location", "street"})
    if not DETECTORS.get("scrub_email", True):
        DISABLED_FILTH_TYPES.update({"email"})
    if not DETECTORS.get("scrub_phone", False):
        DISABLED_FILTH_TYPES.update({"phone"})
    if not DETECTORS.get("scrub_ssn", True):
        DISABLED_FILTH_TYPES.update({"ssn"})

    filth_map_config = deepcopy(DEFAULT_FILTH_PLACEHOLDERS)
    filth_map_config.update(config.get("filth_placeholders", {}) or {})
    mapping: dict[str, tuple[str, str, str]] = {}
    for filth_type, placeholder_name in filth_map_config.items():
        if filth_type in DISABLED_FILTH_TYPES:
            continue
        placeholder_key = str(placeholder_name).upper()
        placeholder_value = _render_placeholder(placeholder_key)
        mapping[filth_type] = (placeholder_value, placeholder_key, placeholder_key)
    if "default" not in mapping:
        mapping["default"] = (_render_placeholder("PII"), "PII", "PII")
    SCRUBADUB_PLACEHOLDERS = mapping

    rules: list[RegexRule] = [
        RegexRule(_CARD_PATTERN, _handle_card),
        RegexRule(_ROUTING_PATTERN, _handle_routing),
        RegexRule(_ACCOUNT_PATTERN, _handle_account),
        RegexRule(_CARD_SUFFIX_PATTERN, _handle_card_suffix),
    ]

    if DETECTORS.get("scrub_address", True):
        rules.extend(
            [
                RegexRule(
                    _STREET_PATTERN, _handle_simple(_render_placeholder("ADDRESS"), "ADDRESS")
                ),
                RegexRule(
                    _CITY_STATE_PATTERN, _handle_simple(_render_placeholder("ADDRESS"), "ADDRESS")
                ),
            ]
        )

    if DETECTORS.get("scrub_name", True):
        rules.append(RegexRule(_NAME_PATTERN, _handle_name_match))

    if DETECTORS.get("scrub_ssn", True):
        rules.append(RegexRule(_SSN_PATTERN, _handle_simple(_render_placeholder("SSN"), "SSN")))

    if DETECTORS.get("scrub_email", True):
        rules.append(
            RegexRule(_EMAIL_PATTERN, _handle_simple(_render_placeholder("EMAIL"), "EMAIL"))
        )

    if DETECTORS.get("scrub_url", True):
        rules.append(RegexRule(_URL_PATTERN, _handle_simple(_render_placeholder("URL"), "URL")))

    if DETECTORS.get("scrub_customer_id", True):
        rules.append(RegexRule(_CUSTOMER_ID_PATTERN, _handle_customer_id))

    if DETECTORS.get("scrub_phone", False):
        rules.append(
            RegexRule(
                _PHONE_PATTERN, _handle_simple(_render_placeholder("PHONE_NUMBER"), "PHONE_NUMBER")
            )
        )

    for entry in config.get("custom_regex") or []:
        pattern_entry = entry.get("pattern")
        if not pattern_entry:
            raise click.ClickException("custom_regex entries require a 'pattern'")
        compiled = _compile_pattern_entry(entry)
        placeholder_name = entry.get("placeholder")
        replacement = entry.get("replacement")
        if placeholder_name and not replacement:
            replacement = _render_placeholder(str(placeholder_name).upper())
        if not replacement:
            raise click.ClickException(
                "custom_regex entries require a 'replacement' or 'placeholder'"
            )
        stat_key = str(entry.get("stat") or placeholder_name or "CUSTOM")

        def _make_handler(rep: str, stat: str) -> Callable[[re.Match[str], ScrubStats], str]:
            def _handler(match: re.Match[str], stats: ScrubStats) -> str:
                stats.increment(stat)
                return rep

            return _handler

        rules.append(RegexRule(compiled, _make_handler(replacement, stat_key)))

    REGEX_RULES = rules


def _load_and_configure(config_path: Path | None) -> None:
    base_config = _load_default_config()
    merged = deepcopy(base_config)
    if USER_CONFIG_PATH.exists():
        merged = _deep_merge(merged, _load_yaml_file(USER_CONFIG_PATH))
    if config_path is not None:
        if not config_path.exists():
            raise click.ClickException(f"Config file '{config_path}' not found")
        merged = _deep_merge(merged, _load_yaml_file(config_path))
    _configure_runtime(merged)


def _is_transaction_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    patterns = TRANSACTION_PATTERNS or _DEFAULT_TRANSACTION_PATTERNS
    return any(pattern.search(stripped) for pattern in patterns)


def _handle_card(match: re.Match[str], stats: ScrubStats) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if 13 <= len(digits) <= 19 and _luhn_checksum(digits):
        stats.increment("CARD_NUMBER")
        suffix = digits[-4:]
        return _render_placeholder("CARD_NUMBER_LAST4", last4=suffix)
    return raw


def _handle_routing(match: re.Match[str], stats: ScrubStats) -> str:
    prefix, digits = match.groups()
    stats.increment("ROUTING_NUMBER")
    return f"{prefix}{_render_placeholder('ROUTING_NUMBER')}"


def _handle_account(match: re.Match[str], stats: ScrubStats) -> str:
    prefix, digits = match.groups()
    stats.increment("ACCOUNT_NUMBER")
    return f"{prefix}{_render_placeholder('ACCOUNT_NUMBER')}"


def _handle_simple(placeholder: str, key: str) -> Callable[[re.Match[str], ScrubStats], str]:
    def _inner(match: re.Match[str], stats: ScrubStats) -> str:
        stats.increment(key)
        return placeholder

    return _inner


def _handle_customer_id(match: re.Match[str], stats: ScrubStats) -> str:
    prefix, value = match.groups()
    stats.increment("CUSTOMER_ID")
    return f"{prefix}{_render_placeholder('CUSTOMER_ID')}"


def _handle_card_suffix(match: re.Match[str], stats: ScrubStats) -> str:
    prefix, last4 = match.groups()
    stats.increment("ACCOUNT_LAST4")
    return f"{prefix}{_render_placeholder('ACCOUNT_LAST4', last4=last4)}"


def _handle_name_match(match: re.Match[str], stats: ScrubStats) -> str:
    candidate = match.group(0)
    tokens = [token.lower() for token in re.findall(r"[A-Za-z']+", candidate)]
    if not tokens:
        return candidate
    if all(token in NAME_SKIP_WORDS for token in tokens):
        return candidate
    stats.increment("NAME")
    return _render_placeholder("NAME")


def _mask_embedded_card_numbers(text: str, stats: ScrubStats) -> str:
    result: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        if text[i].isdigit():
            matched = None
            for size in range(19, 12, -1):  # 19 down to 13
                end = i + size
                if end > length:
                    continue
                snippet = text[i:end]
                if not snippet.isdigit():
                    continue
                if _luhn_checksum(snippet):
                    matched = snippet
                    break
            if matched:
                stats.increment("CARD_NUMBER")
                result.append(_render_placeholder("CARD_NUMBER_LAST4", last4=matched[-4:]))
                i += len(matched)
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


_scrubber = None


def _get_scrubber():
    global _scrubber
    if _scrubber is not None:
        return _scrubber
    try:
        import scrubadub
    except ImportError as exc:
        raise click.ClickException(
            "Missing dependencies for fin-scrub. Install with 'pip install fin-cli[pii]'."
        ) from exc

    _scrubber = scrubadub.Scrubber()
    try:
        from scrubadub.detectors import TextBlobNameDetector
    except ImportError:
        TextBlobNameDetector = None  # type: ignore[assignment]

    if TextBlobNameDetector is not None:
        _scrubber.add_detector(TextBlobNameDetector())
    return _scrubber


def _apply_regex_rules(text: str, stats: ScrubStats) -> str:
    text = _mask_embedded_card_numbers(text, stats)
    for rule in REGEX_RULES:
        text = rule.apply(text, stats)
    return text


def _apply_scrubadub(text: str, stats: ScrubStats) -> str:
    scrubber = _get_scrubber()
    try:
        filths = list(scrubber.iter_filth(text))
    except Exception as exc:  # pragma: no cover - defensive guard
        missing_corpora = getattr(exc, "__class__", None).__name__ == "MissingCorpusError"
        if missing_corpora:
            raise click.ClickException(
                "TextBlob corpora missing. Run 'python -m textblob.download_corpora' to enable name detection."
            ) from exc
        raise
    if not filths:
        return text
    cleaned = text
    for filth in sorted(filths, key=lambda item: item.beg, reverse=True):
        filth_type = getattr(filth, "type", None)
        if filth_type in DISABLED_FILTH_TYPES:
            continue
        mapping = SCRUBADUB_PLACEHOLDERS.get(filth_type) or SCRUBADUB_PLACEHOLDERS.get("default")
        if not mapping:
            continue
        placeholder, stat_key, placeholder_name = mapping
        segment = cleaned[filth.beg : filth.end]
        if "[" in segment and "]" in segment:
            continue
        if placeholder_name == "NAME":
            token = segment.strip().lower()
            if token in NAME_SKIP_WORDS:
                continue
        cleaned = cleaned[: filth.beg] + placeholder + cleaned[filth.end :]
        stats.increment(stat_key)
    return cleaned


def _scrub_text(raw_text: str, stats: ScrubStats) -> str:
    pages = raw_text.split("\f")
    cleaned_pages: list[str] = []

    for page_text in pages:
        lines = page_text.splitlines()
        cleaned_lines: list[str] = []
        in_transaction_block = False

        header_patterns = PAGE_HEADER_PATTERNS or _DEFAULT_PAGE_HEADER_PATTERNS
        footer_patterns = PAGE_FOOTER_PATTERNS or _DEFAULT_PAGE_FOOTER_PATTERNS

        for line in lines:
            if any(pattern.search(line) for pattern in header_patterns) or any(
                pattern.search(line) for pattern in footer_patterns
            ):
                in_transaction_block = False

            if not in_transaction_block and _is_transaction_line(line):
                in_transaction_block = True

            if in_transaction_block:
                cleaned_lines.append(line)
                continue

            if not line.strip():
                cleaned_lines.append(line)
                continue

            stage_one = _apply_regex_rules(line, stats)
            stage_two = _apply_scrubadub(stage_one, stats)
            cleaned_lines.append(stage_two)

        cleaned_pages.append("\n".join(cleaned_lines))

    return "\f".join(cleaned_pages)


def _read_pdf(path: Path, engine: str) -> str:
    document = load_pdf_document_with_engine(
        path=path, engine=engine, enable_camelot_fallback=False
    )
    return document.text


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    slug = slug.strip("-_")
    return slug or "statement"


def _derive_scrubbed_filename(source: Path | None) -> str:
    if source is None:
        base = "stdin"
    else:
        base = source.stem
    base = base.rstrip("-_ ")
    slug = _slugify(base)
    if slug.endswith("-scrubbed"):
        slug = slug[: -len("-scrubbed")]
    return f"{slug}-scrubbed.txt"


SOURCE_HASH_HEADER_PREFIX = "# SOURCE_FILE_HASH: "


def parse_source_file_hash(scrubbed_content: str) -> str | None:
    """
    Extract the source file hash from scrubbed content if present.

    Returns the SHA256 hash string or None if not found.
    """
    if not scrubbed_content:
        return None
    first_line = scrubbed_content.split("\n", 1)[0]
    if first_line.startswith(SOURCE_HASH_HEADER_PREFIX):
        return first_line[len(SOURCE_HASH_HEADER_PREFIX) :].strip()
    return None


def parse_source_file_hash_from_path(path: Path) -> str | None:
    """
    Extract the source file hash from a scrubbed file.

    Reads only the first line to avoid loading the entire file.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            first_line = f.readline()
        if first_line.startswith(SOURCE_HASH_HEADER_PREFIX):
            return first_line[len(SOURCE_HASH_HEADER_PREFIX) :].strip()
    except (OSError, UnicodeDecodeError):
        pass
    return None


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_path", type=click.Path(path_type=Path), required=False)
@click.option(
    "--output", "output_path", type=click.Path(path_type=Path), help="Write scrubbed text to file."
)
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(path_type=Path),
    help="Directory where the scrubbed file should be written using an auto-generated name.",
)
@click.option("--stdout", "use_stdout", is_flag=True, help="Write scrubbed text to stdout.")
@click.option(
    "--stdin", "use_stdin", is_flag=True, help="Read raw text from stdin instead of a file."
)
@click.option(
    "--engine",
    type=click.Choice(["auto", "pdfplumber"], case_sensitive=False),
    default="auto",
    show_default=True,
    help="PDF parsing engine to use when reading PDFs (auto uses pdfplumber with Camelot fallback).",
)
@click.option("--report", is_flag=True, help="Emit counts of redacted entities to stderr.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    help="Path to a YAML configuration file overriding defaults.",
)
@click.option(
    "--no-source-hash",
    "skip_source_hash",
    is_flag=True,
    help="Do not embed the source file hash in the scrubbed output.",
)
def main(
    input_path: Path | None,
    output_path: Path | None,
    output_dir: Path | None,
    use_stdout: bool,
    use_stdin: bool,
    engine: str,
    report: bool,
    config_path: Path | None,
    skip_source_hash: bool,
) -> None:
    """Redact PII from bank statements and emit scrubbed text."""

    if use_stdin and input_path is not None:
        raise click.ClickException("Specify either an input file or --stdin, not both.")
    if not use_stdin and input_path is None:
        raise click.ClickException("Provide an input PDF/text file or use --stdin.")
    if output_path is not None and output_dir is not None:
        raise click.ClickException("Specify either --output or --output-dir, not both.")
    if (output_path or output_dir) and use_stdout:
        raise click.ClickException("Use either file output options or --stdout, not both.")

    _load_and_configure(config_path)

    # Compute source file hash before reading content (for idempotent import tracking)
    source_file_hash: str | None = None
    if not use_stdin and not skip_source_hash and input_path is not None:
        source_file_hash = compute_file_sha256(input_path)

    if use_stdin:
        raw_text = sys.stdin.read()
    else:
        if input_path.suffix.lower() == ".pdf":
            raw_text = _read_pdf(input_path, engine=engine)
        else:
            raw_text = input_path.read_text()

    stats = ScrubStats()
    scrubbed = _scrub_text(raw_text, stats)

    # Prepend source hash header if computed
    if source_file_hash:
        scrubbed = f"{SOURCE_HASH_HEADER_PREFIX}{source_file_hash}\n{scrubbed}"

    if output_dir is not None:
        # Keep scrubbed outputs flat in the requested directory so downstream
        # skills can glob for `*-scrubbed.txt` without remembering a subfolder.
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / _derive_scrubbed_filename(input_path if not use_stdin else None)

    if output_path:
        output_path.write_text(scrubbed)
    if use_stdout or not output_path:
        click.echo(scrubbed, nl=False)

    if report:
        report_lines = ["Redaction counts:"]
        for key, value in sorted(stats.counts.items()):
            report_lines.append(f"  {key}: {value}")
        click.echo("\n".join(report_lines), err=True)


if __name__ == "__main__":  # pragma: no cover
    main()
