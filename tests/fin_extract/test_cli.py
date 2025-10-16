from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_extract.main import main
from fin_cli.fin_extract.parsers.pdf_loader import PdfDocument, PdfTable


def _strip_ansi(value: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", value)


def _fake_document() -> PdfDocument:
    headers = ("Transaction Date", "Description", "Type", "Amount")
    rows = [("11/01/2024", "SWEETGREEN #123", "Sale", "18.47")]
    return PdfDocument(text="Chase Statement", tables=[PdfTable(headers=headers, rows=rows)])


def test_cli_dry_run(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        "fin_cli.fin_extract.main.load_pdf_document",
        lambda *args, **kwargs: _fake_document(),
    )

    runner = CliRunner()
    result = runner.invoke(main, [str(pdf_path), "--dry-run"])
    assert result.exit_code == 0
    assert "Transactions: 1" in _strip_ansi(result.output)
    assert "Institution: Chase" in result.output


def test_cli_defaults_output_path(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "bofa.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    monkeypatch.setattr(
        "fin_cli.fin_extract.main.load_pdf_document",
        lambda *args, **kwargs: _fake_document(),
    )

    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, [str(pdf_path)])
    assert result.exit_code == 0

    expected_output = tmp_path / "output" / "bofa.csv"
    assert expected_output.exists()
    assert "SWEETGREEN" in expected_output.read_text()
