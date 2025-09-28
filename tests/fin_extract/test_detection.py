from __future__ import annotations

import pytest

from fin_cli.fin_extract.extractors import detect_extractor
from fin_cli.fin_extract.parsers.pdf_loader import PdfDocument, PdfTable
from fin_cli.shared.exceptions import UnsupportedFormatError


def test_detection_respects_configured_supported_banks() -> None:
    document = PdfDocument(
        text="Bank of America Statement Period: 08/01/2024 - 08/31/2024",
        tables=[
            PdfTable(
                headers=("Date", "Description", "Amount"),
                rows=[("08/01/2024", "Sample", "12.34")],
            )
        ],
    )

    with pytest.raises(UnsupportedFormatError) as exc:
        detect_extractor(document, allowed_institutions=("chase",))

    assert "Bank of America" in str(exc.value)


def test_detection_unknown_institution() -> None:
    document = PdfDocument(
        text="Wells Fargo Statement Period: 08/01/2024 - 08/31/2024",
        tables=[
            PdfTable(
                headers=("Date", "Details", "Amount"),
                rows=[("08/01/2024", "Sample", "$15.00")],
            )
        ],
    )

    with pytest.raises(UnsupportedFormatError) as exc:
        detect_extractor(document)

    assert "Unsupported statement format" in str(exc.value)
