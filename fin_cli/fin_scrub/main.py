"""fin-scrub CLI entrypoint."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Tuple

import click

from fin_cli.fin_extract.parsers.pdf_loader import load_pdf_document_with_engine

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

    counts: Dict[str, int] = field(default_factory=dict)

    def increment(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1

    def merge(self, other: "ScrubStats") -> None:
        for key, value in other.counts.items():
            self.counts[key] = self.counts.get(key, 0) + value


class RegexRule:
    """Applies a compiled regex and replacement callback."""

    def __init__(self, pattern: re.Pattern[str], handler: Callable[[re.Match[str], ScrubStats], str]):
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
_NAME_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){1,2}\b"
)
_TRANSACTION_LINE_RE = re.compile(
    r"^\s*\d{1,2}/\d{1,2}(?:\s+\d{1,2}/\d{1,2})?\s+.+?\s+[-\$\(\)0-9.,]+$"
)
_TRANSACTION_MONTH_RE = re.compile(
    r"^\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?!\d)",
    re.IGNORECASE,
)


def _handle_card(match: re.Match[str], stats: ScrubStats) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if 13 <= len(digits) <= 19 and _luhn_checksum(digits):
        stats.increment("CARD_NUMBER")
        suffix = digits[-4:]
        return f"[CARD_NUMBER_LAST4:{suffix}]"
    return raw


def _handle_routing(match: re.Match[str], stats: ScrubStats) -> str:
    prefix, digits = match.groups()
    stats.increment("ROUTING_NUMBER")
    return f"{prefix}[ROUTING_NUMBER]"


def _handle_account(match: re.Match[str], stats: ScrubStats) -> str:
    prefix, digits = match.groups()
    stats.increment("ACCOUNT_NUMBER")
    return f"{prefix}[ACCOUNT_NUMBER]"


def _handle_simple(placeholder: str, key: str) -> Callable[[re.Match[str], ScrubStats], str]:
    def _inner(match: re.Match[str], stats: ScrubStats) -> str:
        stats.increment(key)
        return placeholder

    return _inner


def _handle_customer_id(match: re.Match[str], stats: ScrubStats) -> str:
    prefix, value = match.groups()
    stats.increment("CUSTOMER_ID")
    return f"{prefix}[CUSTOMER_ID]"


def _handle_card_suffix(match: re.Match[str], stats: ScrubStats) -> str:
    prefix, last4 = match.groups()
    stats.increment("ACCOUNT_LAST4")
    return f"{prefix}[ACCOUNT_LAST4:{last4}]"


def _handle_name_match(match: re.Match[str], stats: ScrubStats) -> str:
    candidate = match.group(0)
    tokens = [token.lower() for token in re.findall(r"[A-Za-z']+", candidate)]
    if not tokens:
        return candidate
    if all(token in _NAME_SKIP_WORDS for token in tokens):
        return candidate
    stats.increment("NAME")
    return "[NAME]"


_REGEX_RULES: Iterable[RegexRule] = (
    RegexRule(_CARD_PATTERN, _handle_card),
    RegexRule(_ROUTING_PATTERN, _handle_routing),
    RegexRule(_ACCOUNT_PATTERN, _handle_account),
    RegexRule(_CARD_SUFFIX_PATTERN, _handle_card_suffix),
    RegexRule(_STREET_PATTERN, _handle_simple("[ADDRESS]", "ADDRESS")),
    RegexRule(_CITY_STATE_PATTERN, _handle_simple("[ADDRESS]", "ADDRESS")),
    RegexRule(_NAME_PATTERN, _handle_name_match),
    RegexRule(_SSN_PATTERN, _handle_simple("[SSN]", "SSN")),
    # Phone numbers often appear in transaction support lines; leave them intact.
    RegexRule(_EMAIL_PATTERN, _handle_simple("[EMAIL]", "EMAIL")),
    RegexRule(_URL_PATTERN, _handle_simple("[URL]", "URL")),
    RegexRule(_CUSTOMER_ID_PATTERN, _handle_customer_id),
)

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
    for rule in _REGEX_RULES:
        text = rule.apply(text, stats)
    return text


_SCRUBADUB_PLACEHOLDERS: Dict[str, Tuple[str, str]] = {
    "email": ("[EMAIL]", "EMAIL"),
    "name": ("[NAME]", "NAME"),
    "address": ("[ADDRESS]", "ADDRESS"),
    "location": ("[ADDRESS]", "ADDRESS"),
    "street": ("[ADDRESS]", "ADDRESS"),
    "credit_card": ("[CARD_NUMBER]", "CARD_NUMBER"),
    "ssn": ("[SSN]", "SSN"),
    "ipv4": ("[IP]", "IP"),
    "ipv6": ("[IP]", "IP"),
    "password": ("[SECRET]", "SECRET"),
    "default": ("[PII]", "PII"),
}

_NAME_SKIP_WORDS = {
    # Prevent over-scrubbing common ledger vocabulary while still masking real names.
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
    "of",
    "america",
    "statement",
    "closing",
    "date",
    "available",
    "line",
    "credit",
    "minimum",
    "payment",
    "warning",
    "billing",
    "cycle",
    "september",
    "sep",
    "oct",
    "nov",
    "dec",
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
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
    "target.com",
    "target",
    "com",
    "inc",
    "corp",
    "llc",
    "service",
    "information",
    "wilmington",
    "dallas",
    "texas",
    "california",
    "menlo",
    "park",
    "san",
    "francisco",
    "pacific",
    "dermatol",
    "coast",
    "visa",
    "signature",
    "payment",
    "due",
    "balance",
}


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
        placeholder, key = _SCRUBADUB_PLACEHOLDERS.get(
            getattr(filth, "type", None), _SCRUBADUB_PLACEHOLDERS["default"]
        )
        segment = cleaned[filth.beg : filth.end]
        if "[" in segment and "]" in segment:
            continue
        if key == "PHONE_NUMBER":
            continue
        if key == "PII":
            cleaned_segment = segment.strip()
            if re.fullmatch(r"[0-9\-()\s\.]+", cleaned_segment):
                continue
        if key == "NAME":
            token = segment.strip().lower()
            if token in _NAME_SKIP_WORDS:
                continue
        cleaned = cleaned[: filth.beg] + placeholder + cleaned[filth.end :]
        stats.increment(key)
    return cleaned


def _scrub_text(raw_text: str, stats: ScrubStats) -> str:
    cleaned_lines: list[str] = []
    in_transaction_block = False
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            in_transaction_block = False
            continue
        month_line = _TRANSACTION_MONTH_RE.match(stripped) and "$" in line
        if _TRANSACTION_LINE_RE.match(stripped) or month_line:
            cleaned_lines.append(line)
            in_transaction_block = True
            continue
        if in_transaction_block:
            cleaned_lines.append(line)
            continue
        stage_one = _apply_regex_rules(line, stats)
        stage_two = _apply_scrubadub(stage_one, stats)
        cleaned_lines.append(stage_two)
    return "\n".join(cleaned_lines)


def _read_pdf(path: Path, engine: str) -> str:
    document = load_pdf_document_with_engine(path=path, engine=engine, enable_camelot_fallback=False)
    return document.text


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_path", type=click.Path(path_type=Path), required=False)
@click.option("--output", "output_path", type=click.Path(path_type=Path), help="Write scrubbed text to file.")
@click.option("--stdout", "use_stdout", is_flag=True, help="Write scrubbed text to stdout.")
@click.option("--stdin", "use_stdin", is_flag=True, help="Read raw text from stdin instead of a file.")
@click.option("--engine", type=click.Choice(["auto", "docling", "pdfplumber"], case_sensitive=False), default="auto", show_default=True, help="PDF parsing engine to use when reading PDFs.")
@click.option("--report", is_flag=True, help="Emit counts of redacted entities to stderr.")
def main(input_path: Path | None, output_path: Path | None, use_stdout: bool, use_stdin: bool, engine: str, report: bool) -> None:
    """Redact PII from bank statements and emit scrubbed text."""

    if use_stdin and input_path is not None:
        raise click.ClickException("Specify either an input file or --stdin, not both.")
    if not use_stdin and input_path is None:
        raise click.ClickException("Provide an input PDF/text file or use --stdin.")
    if output_path is not None and use_stdout:
        raise click.ClickException("Use either --output or --stdout, not both.")

    if use_stdin:
        raw_text = sys.stdin.read()
    else:
        if input_path.suffix.lower() == ".pdf":
            raw_text = _read_pdf(input_path, engine=engine)
        else:
            raw_text = input_path.read_text()

    stats = ScrubStats()
    scrubbed = _scrub_text(raw_text, stats)

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
