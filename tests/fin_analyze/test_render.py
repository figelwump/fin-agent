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


def test_render_csv_single_table(sample_result: AnalysisResult) -> None:
    buffer = StringIO()
    render.render_result(
        sample_result,
        output_format="csv",
        logger=get_logger(verbose=False),
        stream=buffer,
    )
    lines = [line.strip() for line in buffer.getvalue().splitlines() if line.strip()]
    assert lines[0] == "title,Sample Analysis"
    assert "summary,First insight" in lines
    assert "table,sample" in lines
    assert "Col A,Col B" in lines


def test_render_csv_multiple_tables(sample_result: AnalysisResult) -> None:
    extra_table = TableSeries(
        name="extra",
        columns=["Foo", "Bar"],
        rows=[["baz", 3]],
        metadata={"unit": "USD"},
    )
    multi_result = AnalysisResult(
        title=sample_result.title,
        summary=sample_result.summary,
        tables=[*sample_result.tables, extra_table],
        json_payload=sample_result.json_payload,
    )

    buffer = StringIO()
    render.render_result(
        multi_result,
        output_format="csv",
        logger=get_logger(verbose=False),
        stream=buffer,
    )
    output = buffer.getvalue().splitlines()
    # Ensure blank separator between table sections for easy parsing.
    separator_indices = [index for index, line in enumerate(output) if line.strip() == ""]
    assert separator_indices, "Expected at least one blank separator line"
    assert "table,sample" in output
    assert "table,extra" in output
