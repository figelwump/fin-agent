from __future__ import annotations

from fin_cli.shared.logging import get_logger


def test_logger_info_routes_to_stderr(capfd) -> None:
    logger = get_logger()

    logger.info("structured log to stderr")

    captured = capfd.readouterr()
    assert "structured log to stderr" in captured.err
    assert "structured log to stderr" not in captured.out
