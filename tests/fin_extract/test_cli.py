from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_extract.main import main
from fin_cli.fin_extract.parsers.pdf_loader import PdfDocument, PdfTable


def _fake_document() -> PdfDocument:
    headers = ("Transaction Date", "Description", "Type", "Amount")
    rows = [("11/01/2024", "SWEETGREEN #123", "Sale", "18.47")]
    return PdfDocument(text="Chase Statement", tables=[PdfTable(headers=headers, rows=rows)])


def test_cli_dry_run(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_text("fake", encoding="utf-8")

    monkeypatch.setattr("fin_cli.fin_extract.main.load_pdf_document", lambda _: _fake_document())

    runner = CliRunner()
    result = runner.invoke(main, [str(pdf_path), "--dry-run"])
    assert result.exit_code == 0
    assert "Transactions: 1" in result.output
    assert "Institution: Chase" in result.output
