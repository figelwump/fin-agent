"""Rich-based logging helpers shared across CLI tools."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.theme import Theme
from rich.traceback import install

install(show_locals=False)

_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "debug": "dim",
    }
)

# Rich consoles separate stdout (for structured payloads) and stderr (for log chatter).
#
# We disable Rich's built-in syntax highlighting for plain strings to keep output stable.
# When highlighting is enabled, Rich may apply additional styles to numbers / punctuation
# within a message (e.g., account names like "UBS-INV-001"), which can inject ANSI
# sequences inside the string. This makes tests that assert on CLI output brittle in
# environments that force color output (e.g., `FORCE_COLOR=1`).
_stdout_console = Console(theme=_THEME, highlight=False)
_stderr_console = Console(stderr=True, theme=_THEME, highlight=False)
_verbose_console = Console(stderr=True, theme=_THEME, highlight=False)


@dataclass(slots=True)
class Logger:
    """Lightweight logger facade backed by Rich consoles."""

    verbose: bool = False

    @property
    def console(self) -> Console:
        return _stdout_console

    def info(self, message: str) -> None:
        _stderr_console.print(message, style="info", markup=False)

    def success(self, message: str) -> None:
        _stderr_console.print(message, style="success", markup=False)

    def warning(self, message: str) -> None:
        _stderr_console.print(message, style="warning", markup=False)

    def error(self, message: str) -> None:
        _stderr_console.print(message, style="error", markup=False)

    def debug(self, message: str) -> None:
        if self.verbose:
            _verbose_console.print(message, style="debug", markup=False)


def get_logger(verbose: bool = False) -> Logger:
    """Return a configured Logger instance."""
    return Logger(verbose=verbose)
