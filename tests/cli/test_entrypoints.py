"""Smoke tests verifying CLI entry points load without the repo virtualenv."""

from __future__ import annotations

import importlib
from typing import Callable

import pytest
from click.testing import CliRunner


@pytest.mark.parametrize(
    "module_path, attr_name, prog_name",
    [
        ("fin_cli.fin_scrub.main", "main", "fin-scrub"),
        ("fin_cli.fin_edit.main", "main", "fin-edit"),
        ("fin_cli.fin_query.main", "cli", "fin-query"),
        ("fin_cli.fin_analyze.main", "main", "fin-analyze"),
        ("fin_cli.fin_extract.main", "main", "fin-extract"),
        ("fin_cli.fin_enhance.main", "main", "fin-enhance"),
        ("fin_cli.fin_export.main", "cli", "fin-export"),
    ],
)
def test_cli_entrypoint_help(module_path: str, attr_name: str, prog_name: str) -> None:
    module = importlib.import_module(module_path)
    cli: Callable[..., object] = getattr(module, attr_name)

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"], prog_name=prog_name)

    assert result.exit_code == 0, result.output
    assert "Usage" in result.output
