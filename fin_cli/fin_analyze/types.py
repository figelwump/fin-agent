"""Core datatypes and interfaces for `fin-analyze` analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable, Mapping, Sequence

from fin_cli.shared.cli import CLIContext
from fin_cli.shared.config import AppConfig


# ----- Exceptions ---------------------------------------------------------------------------


class AnalysisError(RuntimeError):
    """Base class for analyzer failures surfaced to the CLI."""


class AnalysisConfigurationError(AnalysisError):
    """Raised when analyzer options are invalid or incompatible."""


class AnalysisNotImplementedError(AnalysisError):
    """Raised when an analyzer has not yet been implemented."""


class AnalyzerHelpRequested(AnalysisError):
    """Internal control-flow exception to display analyzer-specific help."""


# ----- Data contracts -----------------------------------------------------------------------


@dataclass(frozen=True)
class TimeWindow:
    """Represents the inclusive start/exclusive end bounds for an analysis window."""

    label: str
    start: date
    end: date

    @property
    def days(self) -> int:
        """Return the number of days spanned by this window."""

        return (self.end - self.start).days


@dataclass(frozen=True)
class AnalysisContext:
    """Container passed to analyzers with all resolved execution inputs."""

    cli_ctx: CLIContext
    app_config: AppConfig
    window: TimeWindow
    comparison_window: TimeWindow | None
    output_format: str
    compare: bool
    threshold: float | None
    options: Mapping[str, Any]


@dataclass(frozen=True)
class AnalysisRequest:
    """High-level request details, useful for logging or rendering metadata."""

    analysis_type: str
    options: Mapping[str, Any]
    output_format: str
    compare: bool
    threshold: float | None
    window: TimeWindow
    comparison_window: TimeWindow | None


@dataclass(frozen=True)
class TableSeries:
    """Represents a tabular dataset emitted by an analyzer."""

    name: str
    columns: Sequence[str]
    rows: Sequence[Sequence[Any]]
    metadata: Mapping[str, Any] = field(default_factory=dict)



@dataclass(frozen=True)
class AnalysisResult:
    """Canonical return type from analyzers."""

    title: str
    summary: Sequence[str]
    tables: Sequence[TableSeries]
    json_payload: Mapping[str, Any]

    def is_empty(self) -> bool:
        """True when there is no tabular data and no summary content."""

        return not self.summary and not self.tables


DataFrameLike = Any


@dataclass(frozen=True)
class WindowFrameSet:
    """Bundle of current/comparison DataFrames tied to their time windows."""

    window: TimeWindow
    frame: DataFrameLike
    comparison_window: TimeWindow | None
    comparison_frame: DataFrameLike | None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def primary_empty(self) -> bool:
        """Return True when the primary frame has zero rows."""

        return getattr(self.frame, "empty", True)

    def comparison_empty(self) -> bool:
        """Return True when the comparison frame is missing or empty."""

        if self.comparison_frame is None:
            return True
        return getattr(self.comparison_frame, "empty", True)


# ----- Registry helpers ---------------------------------------------------------------------


AnalyzerCallable = Callable[[AnalysisContext], AnalysisResult]


@dataclass(frozen=True)
class AnalyzerOption:
    """Declarative specification for analyzer-specific CLI options."""

    name: str
    flags: Sequence[str]
    help: str
    type: Callable[[str], Any] | None = None
    default: Any = None
    choices: Iterable[Any] | None = None
    metavar: str | None = None
    is_flag: bool = False
    multiple: bool = False


@dataclass(frozen=True)
class AnalyzerSpec:
    """Registry entry describing an analyzer implementation."""

    slug: str
    title: str
    summary: str
    factory: AnalyzerCallable
    options: Sequence[AnalyzerOption] = field(default_factory=tuple)
    aliases: Sequence[str] = field(default_factory=tuple)

    def all_names(self) -> set[str]:
        """Return the canonical slug plus any aliases."""

        return {self.slug, *self.aliases}


Registry = Mapping[str, AnalyzerSpec]

