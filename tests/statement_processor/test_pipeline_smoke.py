from __future__ import annotations

import csv
from pathlib import Path

from click.testing import CliRunner

from tests.statement_processor.test_categorize_leftovers import categorize
from tests.statement_processor.test_postprocess import _sample_row, postprocess
from tests.statement_processor.test_preprocess import _prepare_config, _seed_sample_data, preprocess


def test_statement_processor_pipeline(tmp_path: Path) -> None:
    config, env = _prepare_config(tmp_path)
    _seed_sample_data(config)

    runner = CliRunner()

    # Preprocess: create prompt from synthetic scrubbed text
    scrubbed_dir = tmp_path / "statements"
    scrubbed_dir.mkdir()
    scrubbed_path = scrubbed_dir / "sample-scrubbed.txt"
    scrubbed_path.write_text(
        """Statement Header\n09/01 Sample Merchant 42.50 SAMPLE DESCRIPTOR""",
        encoding="utf-8",
    )

    preprocess_output = tmp_path / "preprocess-output"
    result = runner.invoke(
        preprocess.cli,
        [
            "--input",
            str(scrubbed_path),
            "--output-dir",
            str(preprocess_output),
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    prompt_files = list(preprocess_output.rglob("*.txt"))
    assert prompt_files, "Expected preprocess prompt file"

    # Postprocess: convert LLM CSV to enriched transactions
    llm_path = tmp_path / "sample-llm.csv"
    headers = list(_sample_row().keys())
    with llm_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerow(_sample_row())

    enriched_dir = tmp_path / "enriched"
    result = runner.invoke(
        postprocess.cli,
        [
            "--input",
            str(llm_path),
            "--output-dir",
            str(enriched_dir),
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    enriched_files = list(enriched_dir.glob("*-enriched.csv"))
    assert enriched_files, "Expected enriched CSV output"

    # Prepare leftovers CSV with blank categories to trigger prompt creation
    leftover_csv = tmp_path / "leftovers.csv"
    with (
        enriched_files[0].open("r", encoding="utf-8") as src,
        leftover_csv.open("w", encoding="utf-8", newline="") as dst,
    ):
        reader = csv.DictReader(src)
        fieldnames = reader.fieldnames or []
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            row["category"] = ""
            row["subcategory"] = ""
            writer.writerow(row)

    categorize_dir = tmp_path / "leftovers"
    categorize_dir.mkdir(parents=True, exist_ok=True)
    output_path = categorize_dir / "leftovers-prompt.txt"
    result = runner.invoke(
        categorize.cli,
        [
            "--input",
            str(leftover_csv),
            "--output",
            str(output_path),
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists(), "Expected leftover prompt output"
