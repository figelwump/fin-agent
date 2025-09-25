from __future__ import annotations

import json
from io import StringIO

import pytest

from fin_cli.fin_analyze import render
from fin_cli.fin_analyze.types import AnalysisResult, TableSeries
from fin_cli.shared.logging import get_logger


@pytest.fixture()
def sample_result() -> AnalysisResult:
    table = TableSeries(
        name="sample",
        columns=["Col A", "Col B"],
        rows=[["foo", 1], ["bar", 2]],
        metadata={"unit": "USD"},
    )
    return AnalysisResult(
        title="Sample Analysis",
        summary=["First insight", "Second insight"],
        tables=[table],
        json_payload={"meta": {"key": "value"}},
    )


def test_render_text(sample_result: AnalysisResult) -> None:
    buffer = StringIO()
    render.render_result(
        sample_result,
        output_format="text",
        logger=get_logger(verbose=False),
        stream=buffer,
    )
    output = buffer.getvalue()
    assert "Sample Analysis" in output
    assert "First insight" in output
    assert "Col A" in output


def test_render_json(sample_result: AnalysisResult) -> None:
    buffer = StringIO()
    render.render_result(
        sample_result,
        output_format="json",
        logger=get_logger(verbose=False),
        stream=buffer,
    )
    payload = json.loads(buffer.getvalue())
    assert payload["title"] == "Sample Analysis"
    assert payload["summary"] == sample_result.summary
    assert payload["payload"]["meta"]["key"] == "value"
    assert payload["tables"][0]["name"] == "sample"

