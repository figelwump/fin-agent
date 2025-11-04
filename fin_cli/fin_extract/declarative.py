"""Declarative statement extractor runtime.

This module provides a generic extractor that can be configured via YAML specs
instead of writing custom Python code for each bank.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from .parsers.pdf_loader import PdfDocument, PdfTable
from .types import ExtractedTransaction, ExtractionResult, StatementMetadata
from .utils import SignClassifier, normalize_pdf_table, normalize_token, parse_amount
from .utils.table import NormalizedTable

_SINGLE_COLUMN_MONTH_DAY_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b",
    re.IGNORECASE,
)
_SINGLE_COLUMN_NUMERIC_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}(?:/\d{2,4})?")
_SINGLE_COLUMN_AMOUNT_RE = re.compile(r"[\-−–]?\$[\d,]+(?:\.\d+)?")
_SINGLE_COLUMN_GLYPHS = ("\uea01", "\uea02", "\uea03", "\uea08")
_SINGLE_COLUMN_STOP_PREFIXES = (
    "total ",
    "interest disclosure",
    "banking services provided",
    "error resolution",
    "getting support",
)
_SINGLE_COLUMN_TYPE_SUFFIXES = (
    "ACH In",
    "ACH Pull",
    "Transfer Out",
    "Transfer In",
    "Check Deposit",
    "Interest Payment",
)


def _expand_single_column_table(table: PdfTable) -> NormalizedTable | None:
    cells: list[str] = []
    cells.extend(cell for cell in table.headers if cell)
    for row in table.rows:
        cells.extend(cell for cell in row if cell)

    if not cells:
        return None

    combined = "\n".join(cells).strip()
    lowered_combined = combined.lower()
    if "date" not in lowered_combined or "amount" not in lowered_combined:
        return None

    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    header_idx: int | None = None
    for idx, line in enumerate(lines):
        lowered = line.lower()
        if "date" in lowered and "description" in lowered and "amount" in lowered:
            header_idx = idx
            break
    if header_idx is None:
        return None

    data_lines = lines[header_idx + 1 :]
    rows: list[tuple[str, ...]] = []
    current_date: str | None = None

    for raw_line in data_lines:
        line = _clean_single_column_text(raw_line)
        if not line:
            continue

        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in _SINGLE_COLUMN_STOP_PREFIXES):
            break

        date_match = _SINGLE_COLUMN_MONTH_DAY_RE.match(
            line
        ) or _SINGLE_COLUMN_NUMERIC_DATE_RE.match(line)
        if date_match:
            current_date = date_match.group(0).strip()
            rest = line[date_match.end() :].strip()
        else:
            rest = line
            if current_date is None:
                continue

        if not rest:
            continue

        amount_matches = list(_SINGLE_COLUMN_AMOUNT_RE.finditer(rest))
        if not amount_matches:
            if rows:
                updated = list(rows[-1])
                updated[1] = f"{updated[1]} {rest}".strip()
                rows[-1] = tuple(updated)
            continue

        amount_match = amount_matches[0]
        amount_str = rest[amount_match.start() : amount_match.end()]
        amount_str = amount_str.replace("−", "-").replace("–", "-").replace("—", "-")
        before_amount = rest[: amount_match.start()].strip(" -")
        after_amount = rest[amount_match.end() :].strip()

        balance_str = ""
        if len(amount_matches) > 1:
            balance_match = amount_matches[1]
            balance_str = rest[balance_match.start() : balance_match.end()]
            balance_str = balance_str.replace("−", "-").replace("–", "-")
            after_amount = (
                rest[amount_match.end() : balance_match.start()] + rest[balance_match.end() :]
            ).strip()

        description = " ".join(part for part in [before_amount, after_amount] if part)
        description = _clean_single_column_text(description)
        description, type_value = _split_single_column_type(description)

        rows.append(
            (
                current_date or "",
                description,
                type_value,
                amount_str.strip(),
                balance_str.strip(),
            )
        )

    if not rows:
        return None

    headers = ("Date", "Description", "Type", "Amount", "Balance")
    return NormalizedTable(headers=headers, rows=rows)


def _clean_single_column_text(value: str) -> str:
    cleaned = value
    for glyph in _SINGLE_COLUMN_GLYPHS:
        cleaned = cleaned.replace(glyph, " ")
    cleaned = cleaned.replace("•", " ")
    cleaned = cleaned.replace("\u2013", "-").replace("\u2014", "-")
    cleaned = cleaned.replace("\u2212", "-")
    return " ".join(cleaned.split())


def _split_single_column_type(description: str) -> tuple[str, str]:
    lowered = description.lower()
    for suffix in _SINGLE_COLUMN_TYPE_SUFFIXES:
        suffix_lower = suffix.lower()
        if lowered.endswith(suffix_lower):
            trimmed = description[: -len(suffix)].strip(" -")
            return trimmed or description, suffix
    return description, ""


from .extractors.base import StatementExtractor

# ============================================================================
# Data Classes (match YAML schema)
# ============================================================================


@dataclass
class ColumnAliases:
    """Column aliases for finding columns in tables."""

    aliases: list[str]


@dataclass
class ColumnConfig:
    """Column mapping configuration."""

    date: ColumnAliases
    description: ColumnAliases
    amount: ColumnAliases | None = None
    debit: ColumnAliases | None = None
    credit: ColumnAliases | None = None
    type: ColumnAliases | None = None


@dataclass
class AmountResolutionConfig:
    """Amount resolution strategy for dual-column amounts."""

    priority: list[str] = field(default_factory=lambda: ["amount", "debit", "credit"])
    take_absolute: bool = True


@dataclass
class StatementPeriodPattern:
    """Pattern for extracting statement period dates."""

    regex: str
    start_group: int
    end_group: int
    format: str


@dataclass
class StatementPeriodConfig:
    """Configuration for extracting statement period."""

    patterns: list[StatementPeriodPattern] = field(default_factory=list)


@dataclass
class YearInferenceConfig:
    """Configuration for inferring year from incomplete dates."""

    enabled: bool = False
    source: str = "statement_period"  # "statement_period" or "statement_text"
    text_pattern: str | None = None


@dataclass
class YearBoundaryConfig:
    """Configuration for handling year boundaries in statements."""

    enabled: bool = False
    month_threshold: int = 1


@dataclass
class DateConfig:
    """Date parsing configuration."""

    formats: list[str]
    infer_year: YearInferenceConfig = field(default_factory=YearInferenceConfig)
    year_boundary: YearBoundaryConfig = field(default_factory=YearBoundaryConfig)


@dataclass
class SignClassificationConfig:
    """Sign classification configuration."""

    method: str = "keywords"  # "keywords", "columns", "hybrid"
    charge_keywords: list[str] = field(default_factory=list)
    credit_keywords: list[str] = field(default_factory=list)
    transfer_keywords: list[str] = field(default_factory=list)
    interest_keywords: list[str] = field(default_factory=list)
    card_payment_keywords: list[str] = field(default_factory=list)
    column_determines_sign: bool = False


@dataclass
class TableFilterCondition:
    """Condition for filtering tables."""

    contains: list[str] = field(default_factory=list)
    not_contains: list[str] = field(default_factory=list)


@dataclass
class TableFiltersConfig:
    """Table-level filtering configuration."""

    skip_if_all: list[TableFilterCondition] = field(default_factory=list)


@dataclass
class RowFiltersConfig:
    """Row-level filtering configuration."""

    skip_descriptions_exact: list[str] = field(default_factory=list)
    skip_descriptions_pattern: list[str] = field(default_factory=list)
    spend_only: bool = True


@dataclass
class MultilineConfig:
    """Multi-line transaction handling configuration."""

    enabled: bool = False
    append_to: str = "previous"
    skip_append_if_summary: bool = True


@dataclass
class MerchantCleanupConfig:
    """Merchant text cleanup configuration."""

    remove_patterns: list[str] = field(default_factory=list)
    trim: bool = True


@dataclass
class AccountNamePattern:
    """Pattern for inferring account name."""

    keywords: list[str] | None = None
    regex: str | None = None
    name: str | None = None
    name_template: str | None = None
    account_type: str | None = None


@dataclass
class AccountNameInferenceConfig:
    """Account name inference configuration."""

    patterns: list[AccountNamePattern] = field(default_factory=list)
    default: str = "Account"


@dataclass
class DetectionConfig:
    """Detection rules for supports() method."""

    keywords_all: list[str] = field(default_factory=list)
    keywords_any: list[str] = field(default_factory=list)
    table_required: bool = True
    header_requires: list[str] = field(default_factory=list)


@dataclass
class DeclarativeSpec:
    """Root specification for declarative extractor."""

    name: str
    institution: str
    account_type: str
    columns: ColumnConfig
    dates: DateConfig
    sign_classification: SignClassificationConfig
    amount_resolution: AmountResolutionConfig = field(default_factory=AmountResolutionConfig)
    statement_period: StatementPeriodConfig = field(default_factory=StatementPeriodConfig)
    table_filters: TableFiltersConfig = field(default_factory=TableFiltersConfig)
    row_filters: RowFiltersConfig = field(default_factory=RowFiltersConfig)
    multiline: MultilineConfig = field(default_factory=MultilineConfig)
    merchant_cleanup: MerchantCleanupConfig = field(default_factory=MerchantCleanupConfig)
    account_name_inference: AccountNameInferenceConfig = field(
        default_factory=AccountNameInferenceConfig
    )
    detection: DetectionConfig = field(default_factory=DetectionConfig)


# ============================================================================
# YAML Loading
# ============================================================================


def load_spec(yaml_path: str | Path) -> DeclarativeSpec:
    """Load and parse a declarative extractor spec from YAML.

    Args:
        yaml_path: Path to YAML spec file

    Returns:
        Parsed DeclarativeSpec

    Raises:
        ValueError: If spec is invalid
        FileNotFoundError: If file doesn't exist
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {yaml_path}")

    with path.open("r") as f:
        data = yaml.safe_load(f)

    return _parse_spec(data)


def _parse_spec(data: dict[str, Any]) -> DeclarativeSpec:
    """Parse YAML data into DeclarativeSpec."""
    # Required fields
    name = data.get("name")
    institution = data.get("institution")
    account_type = data.get("account_type")

    if not name or not institution or not account_type:
        raise ValueError("Missing required fields: name, institution, account_type")

    # Parse columns (required)
    columns_data = data.get("columns", {})
    columns = _parse_columns(columns_data)

    # Parse dates (required)
    dates_data = data.get("dates", {})
    dates = _parse_dates(dates_data)

    # Parse sign classification (required)
    sign_data = data.get("sign_classification", {})
    sign_classification = _parse_sign_classification(sign_data)

    # Parse optional sections
    amount_resolution = _parse_amount_resolution(data.get("amount_resolution", {}))
    statement_period = _parse_statement_period(data.get("statement_period", {}))
    table_filters = _parse_table_filters(data.get("table_filters", {}))
    row_filters = _parse_row_filters(data.get("row_filters", {}))
    multiline = _parse_multiline(data.get("multiline", {}))
    merchant_cleanup = _parse_merchant_cleanup(data.get("merchant_cleanup", {}))
    account_name_inference = _parse_account_name_inference(data.get("account_name_inference", {}))
    detection = _parse_detection(data.get("detection", {}))

    return DeclarativeSpec(
        name=name,
        institution=institution,
        account_type=account_type,
        columns=columns,
        dates=dates,
        sign_classification=sign_classification,
        amount_resolution=amount_resolution,
        statement_period=statement_period,
        table_filters=table_filters,
        row_filters=row_filters,
        multiline=multiline,
        merchant_cleanup=merchant_cleanup,
        account_name_inference=account_name_inference,
        detection=detection,
    )


def _parse_columns(data: dict[str, Any]) -> ColumnConfig:
    """Parse columns configuration."""

    def parse_aliases(col_data: dict[str, Any] | None) -> ColumnAliases | None:
        if not col_data:
            return None
        aliases = col_data.get("aliases", [])
        if not aliases:
            return None
        return ColumnAliases(aliases=aliases)

    date = parse_aliases(data.get("date"))
    description = parse_aliases(data.get("description"))

    if not date or not description:
        raise ValueError("columns.date and columns.description are required")

    amount = parse_aliases(data.get("amount"))
    debit = parse_aliases(data.get("debit"))
    credit = parse_aliases(data.get("credit"))
    type_col = parse_aliases(data.get("type"))

    # Must have either amount OR (debit/credit)
    if not amount and not (debit or credit):
        raise ValueError("Must specify either columns.amount or columns.debit/credit")

    return ColumnConfig(
        date=date,
        description=description,
        amount=amount,
        debit=debit,
        credit=credit,
        type=type_col,
    )


def _parse_dates(data: dict[str, Any]) -> DateConfig:
    """Parse dates configuration."""
    formats = data.get("formats", [])
    if not formats:
        raise ValueError("dates.formats is required")

    infer_year_data = data.get("infer_year", {})
    infer_year = YearInferenceConfig(
        enabled=infer_year_data.get("enabled", False),
        source=infer_year_data.get("source", "statement_period"),
        text_pattern=infer_year_data.get("text_pattern"),
    )

    year_boundary_data = data.get("year_boundary", {})
    year_boundary = YearBoundaryConfig(
        enabled=year_boundary_data.get("enabled", False),
        month_threshold=year_boundary_data.get("month_threshold", 1),
    )

    return DateConfig(
        formats=formats,
        infer_year=infer_year,
        year_boundary=year_boundary,
    )


def _parse_sign_classification(data: dict[str, Any]) -> SignClassificationConfig:
    """Parse sign classification configuration."""
    return SignClassificationConfig(
        method=data.get("method", "keywords"),
        charge_keywords=data.get("charge_keywords", []),
        credit_keywords=data.get("credit_keywords", []),
        transfer_keywords=data.get("transfer_keywords", []),
        interest_keywords=data.get("interest_keywords", []),
        card_payment_keywords=data.get("card_payment_keywords", []),
        column_determines_sign=data.get("column_determines_sign", False),
    )


def _parse_amount_resolution(data: dict[str, Any]) -> AmountResolutionConfig:
    """Parse amount resolution configuration."""
    return AmountResolutionConfig(
        priority=data.get("priority", ["amount", "debit", "credit"]),
        take_absolute=data.get("take_absolute", True),
    )


def _parse_statement_period(data: dict[str, Any]) -> StatementPeriodConfig:
    """Parse statement period configuration."""
    patterns_data = data.get("patterns", [])
    patterns = [
        StatementPeriodPattern(
            regex=p["regex"],
            start_group=p["start_group"],
            end_group=p["end_group"],
            format=p["format"],
        )
        for p in patterns_data
    ]
    return StatementPeriodConfig(patterns=patterns)


def _parse_table_filters(data: dict[str, Any]) -> TableFiltersConfig:
    """Parse table filters configuration."""
    skip_if_all_data = data.get("skip_if_all", [])
    skip_if_all = [
        TableFilterCondition(
            contains=cond.get("contains", []),
            not_contains=cond.get("not_contains", []),
        )
        for cond in skip_if_all_data
    ]
    return TableFiltersConfig(skip_if_all=skip_if_all)


def _parse_row_filters(data: dict[str, Any]) -> RowFiltersConfig:
    """Parse row filters configuration."""
    return RowFiltersConfig(
        skip_descriptions_exact=data.get("skip_descriptions_exact", []),
        skip_descriptions_pattern=data.get("skip_descriptions_pattern", []),
        spend_only=data.get("spend_only", True),
    )


def _parse_multiline(data: dict[str, Any]) -> MultilineConfig:
    """Parse multiline configuration."""
    return MultilineConfig(
        enabled=data.get("enabled", False),
        append_to=data.get("append_to", "previous"),
        skip_append_if_summary=data.get("skip_append_if_summary", True),
    )


def _parse_merchant_cleanup(data: dict[str, Any]) -> MerchantCleanupConfig:
    """Parse merchant cleanup configuration."""
    return MerchantCleanupConfig(
        remove_patterns=data.get("remove_patterns", []),
        trim=data.get("trim", True),
    )


def _parse_account_name_inference(data: dict[str, Any]) -> AccountNameInferenceConfig:
    """Parse account name inference configuration."""
    patterns_data = data.get("patterns", [])
    patterns = [
        AccountNamePattern(
            keywords=p.get("keywords"),
            regex=p.get("regex"),
            name=p.get("name"),
            name_template=p.get("name_template"),
            account_type=p.get("account_type"),
        )
        for p in patterns_data
    ]
    return AccountNameInferenceConfig(
        patterns=patterns,
        default=data.get("default", "Account"),
    )


def _parse_detection(data: dict[str, Any]) -> DetectionConfig:
    """Parse detection configuration."""
    return DetectionConfig(
        keywords_all=data.get("keywords_all", []),
        keywords_any=data.get("keywords_any", []),
        table_required=data.get("table_required", True),
        header_requires=data.get("header_requires", []),
    )


# ============================================================================
# Helper Classes
# ============================================================================


@dataclass(slots=True)
class _ColumnMapping:
    """Resolved column indices for a table."""

    date_index: int
    description_index: int
    amount_index: int | None = None
    debit_index: int | None = None
    credit_index: int | None = None
    type_index: int | None = None


@dataclass(slots=True)
class _StatementPeriod:
    """Parsed statement period."""

    start_date: date | None
    end_date: date | None

    def infer_year(self, month: int) -> int:
        """Infer year for a given month based on statement period."""
        if self.start_date and self.end_date:
            # Normal case: start_month <= end_month
            if self.start_date.month <= self.end_date.month:
                if self.start_date.month <= month <= self.end_date.month:
                    return self.start_date.year
                return self.end_date.year
            # Year boundary case: December to January
            if month >= self.start_date.month:
                return self.start_date.year
            return self.end_date.year
        if self.end_date:
            return self.end_date.year
        if self.start_date:
            return self.start_date.year
        return datetime.today().year


# ============================================================================
# Declarative Extractor Implementation
# ============================================================================


class DeclarativeExtractor(StatementExtractor):
    """Generic extractor driven by declarative YAML spec."""

    def __init__(self, spec: DeclarativeSpec):
        """Initialize extractor with spec.

        Args:
            spec: Declarative specification
        """
        self.spec = spec
        self.name = spec.name

        # Build sign classifier from spec
        self._sign_classifier = SignClassifier(
            charge_keywords=set(spec.sign_classification.charge_keywords),
            credit_keywords=set(spec.sign_classification.credit_keywords),
            transfer_keywords=set(spec.sign_classification.transfer_keywords),
            interest_keywords=set(spec.sign_classification.interest_keywords),
            card_payment_keywords=set(spec.sign_classification.card_payment_keywords),
        )

        # Compile regex patterns
        self._row_skip_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in spec.row_filters.skip_descriptions_pattern
        ]

    def supports(self, document: PdfDocument) -> bool:
        """Check if this extractor supports the document.

        Args:
            document: PDF document to check

        Returns:
            True if extractor supports this document
        """
        text = document.text.lower()

        # Check required keywords
        for keyword in self.spec.detection.keywords_all:
            if keyword.lower() not in text:
                return False

        # Check optional keywords (at least one must match)
        if self.spec.detection.keywords_any:
            if not any(keyword.lower() in text for keyword in self.spec.detection.keywords_any):
                return False

        # Check table requirement
        if self.spec.detection.table_required:
            for table in document.tables:
                normalized = normalize_pdf_table(
                    table, header_predicate=lambda h: self._is_valid_header(h)
                )
                if self._find_column_mapping(normalized.headers):
                    return True
            return False

        return True

    def extract(self, document: PdfDocument) -> ExtractionResult:
        """Extract transactions from document.

        Args:
            document: PDF document to extract from

        Returns:
            Extraction result with metadata and transactions
        """
        # Parse statement period
        period = self._parse_statement_period(document.text)

        # Extract year and month hints for date parsing
        year_hint, statement_month_hint = self._extract_year_and_month_hint(document.text, period)

        # Extract transactions from tables
        transactions: list[ExtractedTransaction] = []
        for table in document.tables:
            # Skip filtered tables
            if self._should_skip_table(table):
                continue

            normalized = normalize_pdf_table(
                table, header_predicate=lambda h: self._is_valid_header(h)
            )
            mapping = self._find_column_mapping(normalized.headers)
            rows: Sequence[tuple[str, ...]] = normalized.rows

            if not mapping:
                expanded = _expand_single_column_table(table)
                if expanded:
                    mapping = self._find_column_mapping(expanded.headers)
                    if mapping:
                        rows = expanded.rows

            if not mapping:
                continue

            transactions.extend(
                self._parse_rows(
                    rows,
                    mapping,
                    period=period,
                    year_hint=year_hint,
                    statement_month_hint=statement_month_hint,
                )
            )

        # Deduplicate transactions (pdfplumber sometimes extracts duplicate tables)
        seen = set()
        deduplicated = []
        for txn in transactions:
            key = (txn.date, txn.merchant, txn.amount, txn.original_description)
            if key not in seen:
                seen.add(key)
                deduplicated.append(txn)
        transactions = deduplicated

        # Infer account name
        account_name, account_type_override = self._infer_account_name(document.text)
        account_type = account_type_override or self.spec.account_type

        metadata = StatementMetadata(
            institution=self.spec.institution,
            account_name=account_name,
            account_type=account_type,
            start_date=period.start_date,
            end_date=period.end_date,
        )

        return ExtractionResult(metadata=metadata, transactions=transactions)

    def _is_valid_header(self, header: tuple[str, ...]) -> bool:
        """Check if header row is valid based on detection rules."""
        if not self.spec.detection.header_requires:
            return True

        normalized = [cell.lower() for cell in header if cell]
        for requirement in self.spec.detection.header_requires:
            req_lower = requirement.lower()
            if not any(req_lower in cell for cell in normalized):
                return False
        return True

    def _find_column_mapping(self, headers: Sequence[str]) -> _ColumnMapping | None:
        """Find column indices by matching aliases.

        Args:
            headers: Table headers

        Returns:
            Column mapping if found, None otherwise
        """
        normalized = [" ".join(h.strip().lower().split()) for h in headers]

        date_idx = self._find_index(normalized, self.spec.columns.date.aliases)
        desc_idx = self._find_index(normalized, self.spec.columns.description.aliases)

        if date_idx is None or desc_idx is None:
            return None

        amount_idx = None
        debit_idx = None
        credit_idx = None
        type_idx = None

        if self.spec.columns.amount:
            amount_idx = self._find_index(normalized, self.spec.columns.amount.aliases)

        if self.spec.columns.debit:
            debit_idx = self._find_index(normalized, self.spec.columns.debit.aliases)

        if self.spec.columns.credit:
            credit_idx = self._find_index(normalized, self.spec.columns.credit.aliases)

        if self.spec.columns.type:
            type_idx = self._find_index(normalized, self.spec.columns.type.aliases)

        # Must have either amount OR (debit/credit)
        if amount_idx is None and debit_idx is None and credit_idx is None:
            return None

        distinct_indices = {
            idx
            for idx in (
                date_idx,
                desc_idx,
                amount_idx,
                debit_idx,
                credit_idx,
                type_idx,
            )
            if idx is not None
        }
        if len(distinct_indices) <= 2:
            return None

        return _ColumnMapping(
            date_index=date_idx,
            description_index=desc_idx,
            amount_index=amount_idx,
            debit_index=debit_idx,
            credit_index=credit_idx,
            type_index=type_idx,
        )

    def _find_index(self, headers: list[str], aliases: list[str]) -> int | None:
        """Find column index by matching aliases.

        Args:
            headers: Normalized header strings
            aliases: List of aliases to match

        Returns:
            Index if found, None otherwise
        """
        for idx, header in enumerate(headers):
            for alias in aliases:
                alias_lower = alias.lower()
                # Exact match
                if header == alias_lower:
                    return idx
                # Partial match
                if alias_lower in header:
                    return idx
        return None

    def _should_skip_table(self, table) -> bool:
        """Check if table should be skipped based on filters.

        Args:
            table: PDF table

        Returns:
            True if table should be skipped
        """
        if not self.spec.table_filters.skip_if_all:
            return False

        header_text = " ".join(str(cell) for row in table.headers for cell in row).lower()

        for condition in self.spec.table_filters.skip_if_all:
            # Check if ALL conditions match
            all_match = True

            # Check contains
            for keyword in condition.contains:
                if keyword.lower() not in header_text:
                    all_match = False
                    break

            if not all_match:
                continue

            # Check not_contains
            for keyword in condition.not_contains:
                if keyword.lower() in header_text:
                    all_match = False
                    break

            if all_match:
                return True

        return False

    def _parse_rows(
        self,
        rows: Sequence[tuple[str, ...]],
        mapping: _ColumnMapping,
        period: _StatementPeriod,
        year_hint: int | None,
        statement_month_hint: int | None = None,
    ) -> list[ExtractedTransaction]:
        """Parse table rows into transactions.

        Args:
            rows: Table rows
            mapping: Column mapping
            period: Statement period
            year_hint: Year hint for date parsing

        Returns:
            List of extracted transactions
        """
        transactions: list[ExtractedTransaction] = []
        last_transaction: ExtractedTransaction | None = None
        current_date: date | None = None
        last_resolved_date: date | None = None

        for row in rows:
            cells = list(row)
            if len(cells) <= max(mapping.date_index, mapping.description_index):
                continue

            date_value = self._get_cell(cells, mapping.date_index)
            description = self._get_cell(cells, mapping.description_index)
            type_value = self._get_cell(cells, mapping.type_index)

            # Parse date
            if date_value:
                try:
                    current_date = self._parse_date(
                        date_value,
                        period=period,
                        year_hint=year_hint,
                        statement_month_hint=statement_month_hint,
                        last_date=last_resolved_date,
                    )
                    last_resolved_date = current_date
                except ValueError:
                    current_date = None

            if current_date is None:
                continue

            if not description:
                continue

            # Check row filters
            if self._should_skip_row(description):
                continue

            # Resolve amount
            amount, source_column, original_amount = self._resolve_amount(cells, mapping)

            # Handle multi-line transactions
            if amount is None:
                if self.spec.multiline.enabled and last_transaction is not None:
                    # Check if we should skip appending
                    if self.spec.multiline.skip_append_if_summary and self._should_skip_row(
                        description
                    ):
                        continue

                    appended = f"{last_transaction.merchant} {description.strip()}".strip()
                    last_transaction.merchant = appended
                    last_transaction.original_description = (
                        f"{last_transaction.original_description} {description.strip()}".strip()
                    )
                continue

            # If original amount is negative, it's a credit/refund - filter it out
            if source_column == "credit" and original_amount is not None and original_amount < 0:
                continue

            # Classify sign
            signed_amount = self._classify_sign(
                amount,
                description=description,
                type_value=type_value,
                source_column=source_column,
                mapping=mapping,
            )

            # Filter non-spend transactions
            if self.spec.row_filters.spend_only and (signed_amount is None or signed_amount <= 0):
                continue

            # Clean up merchant name
            merchant = self._cleanup_merchant(description)

            txn = ExtractedTransaction(
                date=current_date,
                merchant=merchant,
                amount=signed_amount if signed_amount is not None else amount,
                original_description=description.strip(),
            )
            transactions.append(txn)
            last_transaction = txn

        return transactions

    def _get_cell(self, cells: Sequence[str], index: int | None) -> str:
        """Get cell value safely.

        Args:
            cells: Row cells
            index: Column index

        Returns:
            Cell value or empty string
        """
        if index is None or index < 0 or index >= len(cells):
            return ""
        return cells[index].strip()

    def _resolve_amount(
        self, cells: Sequence[str], mapping: _ColumnMapping
    ) -> tuple[float | None, str | None, float | None]:
        """Resolve amount from cells based on priority.

        Args:
            cells: Row cells
            mapping: Column mapping

        Returns:
            Tuple of (amount, source_column_name, original_amount) or (None, None, None)
            where original_amount preserves the sign before abs() is applied
        """
        for col_name in self.spec.amount_resolution.priority:
            if col_name == "amount" and mapping.amount_index is not None:
                value = self._get_cell(cells, mapping.amount_index)
                if value:
                    try:
                        parsed = parse_amount(value)
                        amount = (
                            abs(parsed) if self.spec.amount_resolution.take_absolute else parsed
                        )
                        return amount, "amount", parsed
                    except ValueError:
                        pass

            elif col_name == "debit" and mapping.debit_index is not None:
                value = self._get_cell(cells, mapping.debit_index)
                if value:
                    try:
                        parsed = parse_amount(value)
                        amount = (
                            abs(parsed) if self.spec.amount_resolution.take_absolute else parsed
                        )
                        return amount, "debit", parsed
                    except ValueError:
                        pass

            elif col_name == "credit" and mapping.credit_index is not None:
                value = self._get_cell(cells, mapping.credit_index)
                if value:
                    try:
                        parsed = parse_amount(value)
                        amount = (
                            abs(parsed) if self.spec.amount_resolution.take_absolute else parsed
                        )
                        return amount, "credit", parsed
                    except ValueError:
                        pass

        return None, None, None

    def _classify_sign(
        self,
        amount: float,
        description: str,
        type_value: str,
        source_column: str | None,
        mapping: _ColumnMapping,
    ) -> float | None:
        """Classify transaction sign based on configuration.

        Args:
            amount: Absolute amount
            description: Transaction description
            type_value: Transaction type value
            source_column: Which column the amount came from
            mapping: Column mapping

        Returns:
            Signed amount or None if should be filtered
        """
        method = self.spec.sign_classification.method

        # Column-based classification
        if method in ("columns", "hybrid") and self.spec.sign_classification.column_determines_sign:
            if source_column == "debit":
                return amount  # Positive = spend
            elif source_column == "credit":
                return -amount  # Negative = not spend
            # Fall through to keywords if hybrid

        # Keyword-based classification
        if method in ("keywords", "hybrid"):
            # Get additional context for classification
            money_in_value = ""
            money_out_value = ""
            if mapping.credit_index is not None:
                money_in_value = self._get_cell([description], 0)  # Placeholder
            if mapping.debit_index is not None:
                money_out_value = self._get_cell([description], 0)  # Placeholder

            return self._sign_classifier.classify(
                amount,
                description=description,
                type_value=type_value,
                money_in_value=money_in_value,
                money_out_value=money_out_value,
            )

    def _should_skip_row(self, description: str) -> bool:
        """Check if row should be skipped based on filters.

        Args:
            description: Transaction description

        Returns:
            True if row should be skipped
        """
        description_lower = description.lower()
        normalized = normalize_token(description)

        # Check exact matches
        for skip_desc in self.spec.row_filters.skip_descriptions_exact:
            if normalized == normalize_token(skip_desc):
                return True

        # Check pattern matches
        for pattern in self._row_skip_patterns:
            if pattern.search(description_lower):
                return True

        return False

    def _cleanup_merchant(self, description: str) -> str:
        """Clean up merchant name based on configuration.

        Args:
            description: Raw merchant description

        Returns:
            Cleaned merchant name
        """
        merchant = description

        # Remove patterns
        for pattern in self.spec.merchant_cleanup.remove_patterns:
            pattern_lower = pattern.lower()
            merchant_lower = merchant.lower()
            if pattern_lower in merchant_lower:
                idx = merchant_lower.find(pattern_lower)
                merchant = merchant[:idx] + merchant[idx + len(pattern) :]

        # Trim whitespace
        if self.spec.merchant_cleanup.trim:
            merchant = merchant.strip()

        return merchant

    def _parse_date(
        self,
        value: str,
        period: _StatementPeriod,
        year_hint: int | None,
        statement_month_hint: int | None,
        last_date: date | None,
    ) -> date:
        """Parse date value based on configuration.

        Args:
            value: Date string
            period: Statement period
            year_hint: Year hint from text
            statement_month_hint: Statement month hint from text
            last_date: Last successfully parsed date

        Returns:
            Parsed date

        Raises:
            ValueError: If date cannot be parsed
        """
        value = value.strip()

        # Try configured formats
        for fmt in self.spec.dates.formats:
            needs_year_padding = "%Y" not in fmt and "%y" not in fmt
            adjusted_value = value
            adjusted_fmt = fmt
            if needs_year_padding:
                if not self.spec.dates.infer_year.enabled:
                    continue
                adjusted_value = f"{value} 1900"
                adjusted_fmt = f"{fmt} %Y"
            try:
                parsed = datetime.strptime(adjusted_value, adjusted_fmt).date()

                # If year is 1900 (default from formats without year like "%b %d"), apply year inference
                if parsed.year == 1900 and self.spec.dates.infer_year.enabled:
                    base_year = self._infer_year_for_month(
                        parsed.month, period, year_hint, statement_month_hint, last_date
                    )
                    return date(base_year, parsed.month, parsed.day)

                return parsed
            except ValueError:
                continue

        # Try inferring year for MM/DD format
        if self.spec.dates.infer_year.enabled:
            match = re.match(r"^(\d{1,2})/(\d{1,2})$", value)
            if match:
                month = int(match.group(1))
                day = int(match.group(2))
                base_year = self._infer_year_for_month(
                    month, period, year_hint, statement_month_hint, last_date
                )
                return date(base_year, month, day)

        raise ValueError(f"Unrecognized date format: {value}")

    def _infer_year_for_month(
        self,
        month: int,
        period: _StatementPeriod,
        year_hint: int | None,
        statement_month_hint: int | None,
        last_date: date | None,
    ) -> int:
        """Infer year for a given month based on configuration.

        Args:
            month: Month number (1-12)
            period: Statement period
            year_hint: Year hint from text
            statement_month_hint: Statement month hint from text
            last_date: Last successfully parsed date

        Returns:
            Inferred year
        """
        # Determine base year
        if self.spec.dates.infer_year.source == "statement_period":
            base_year = period.infer_year(month)
        else:
            base_year = year_hint or datetime.today().year

        # Apply year boundary logic
        if self.spec.dates.year_boundary.enabled:
            threshold = self.spec.dates.year_boundary.month_threshold

            # Check against statement period end date if available
            if period.end_date and month > period.end_date.month:
                if month - period.end_date.month > threshold:
                    base_year -= 1
            # Check against statement month hint (e.g., "January 2024")
            elif statement_month_hint is not None and month > statement_month_hint:
                if month - statement_month_hint > threshold:
                    base_year -= 1
            # Fall back to last_date comparison
            elif last_date:
                if month > last_date.month and month - last_date.month > 6:
                    base_year = last_date.year - 1
                elif month < last_date.month and last_date.month - month > 6:
                    base_year = last_date.year + 1

        return base_year

    def _parse_statement_period(self, text: str) -> _StatementPeriod:
        """Parse statement period from text.

        Args:
            text: PDF text

        Returns:
            Statement period
        """
        for pattern_config in self.spec.statement_period.patterns:
            regex = re.compile(pattern_config.regex, re.IGNORECASE)
            match = regex.search(text)
            if match:
                start_str = match.group(pattern_config.start_group)
                end_str = match.group(pattern_config.end_group)

                try:
                    # Handle both 2-digit and 4-digit years
                    fmt = pattern_config.format
                    start_date = datetime.strptime(start_str.strip(), fmt).date()
                    end_date = datetime.strptime(end_str.strip(), fmt).date()
                    return _StatementPeriod(start_date, end_date)
                except ValueError:
                    # Try alternate format for 2-digit years
                    if "/%Y" in fmt:
                        try:
                            alt_fmt = fmt.replace("/%Y", "/%y")
                            start_date = datetime.strptime(start_str.strip(), alt_fmt).date()
                            end_date = datetime.strptime(end_str.strip(), alt_fmt).date()
                            return _StatementPeriod(start_date, end_date)
                        except ValueError:
                            pass

        return _StatementPeriod(None, None)

    def _extract_year_and_month_hint(
        self, text: str, period: _StatementPeriod
    ) -> tuple[int | None, int | None]:
        """Extract year and month hints from text.

        Args:
            text: PDF text
            period: Statement period

        Returns:
            Tuple of (year_hint, statement_month_hint) or (None, None)
        """
        if not self.spec.dates.infer_year.enabled:
            return None, None

        if self.spec.dates.infer_year.source == "statement_period":
            if period.end_date:
                return period.end_date.year, period.end_date.month
            if period.start_date:
                return period.start_date.year, period.start_date.month

        elif self.spec.dates.infer_year.text_pattern:
            pattern = re.compile(self.spec.dates.infer_year.text_pattern, re.IGNORECASE)
            match = pattern.search(text)
            if match:
                month_name = None
                year = None

                # Extract month name (first group)
                if len(match.groups()) >= 1 and match.group(1):
                    month_name = match.group(1)

                # Extract year (last group that's a 4-digit number)
                for group in reversed(match.groups()):
                    if group and group.isdigit() and len(group) == 4:
                        year = int(group)
                        break

                # Convert month name to number
                statement_month = None
                if month_name:
                    month_map = {
                        "january": 1,
                        "february": 2,
                        "march": 3,
                        "april": 4,
                        "may": 5,
                        "june": 6,
                        "july": 7,
                        "august": 8,
                        "september": 9,
                        "october": 10,
                        "november": 11,
                        "december": 12,
                    }
                    statement_month = month_map.get(month_name.lower())

                return year, statement_month

        return None, None

    def _infer_account_name(self, text: str) -> tuple[str, str | None]:
        """Infer account name from text.

        Args:
            text: PDF text

        Returns:
            Tuple of (account_name, account_type_override)
        """
        for pattern in self.spec.account_name_inference.patterns:
            # Keyword-based matching
            if pattern.keywords:
                if all(kw.lower() in text.lower() for kw in pattern.keywords):
                    if pattern.name:
                        return pattern.name, pattern.account_type
                    elif pattern.name_template:
                        return pattern.name_template, pattern.account_type

            # Regex-based matching
            if pattern.regex:
                regex = re.compile(pattern.regex, re.IGNORECASE)
                match = regex.search(text)
                if match:
                    if pattern.name_template:
                        # Format template with capture groups
                        name = pattern.name_template
                        for i, group in enumerate(match.groups(), start=1):
                            name = name.replace(f"{{{i}}}", group or "")
                        return name, pattern.account_type
                    elif pattern.name:
                        return pattern.name, pattern.account_type

        return self.spec.account_name_inference.default, None
