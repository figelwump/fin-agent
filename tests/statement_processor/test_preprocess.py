from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from click.testing import CliRunner

from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations

MODULE_PATH = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "statement-processor" / "preprocess.py"
spec = importlib.util.spec_from_file_location("statement_processor_preprocess", MODULE_PATH)
preprocess = importlib.util.module_from_spec(spec)
assert spec and spec.loader  # narrow type checker; loader exists when spec resolves.
sys.modules[spec.name] = preprocess
spec.loader.exec_module(preprocess)


def _prepare_config(tmp_path: Path):
    db_path = tmp_path / "preprocess.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    return config, env


def _seed_sample_data(config):
    with connect(config) as connection:
        shopping_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Shopping", "Online"),
        ).fetchone()[0]
        dining_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Food & Dining", "Coffee"),
        ).fetchone()[0]

        account_id = connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?) RETURNING id",
            ("Chase Prime Visa", "Chase", "credit"),
        ).fetchone()[0]
        transactions = [
            (
                "2025-09-01",
                "Amazon",
                -45.67,
                shopping_id,
                account_id,
                "AMZN Mktp US*7X51S5QT3",
                "2025-09-05T10:15:00",
                0.95,
                "rule:pattern",
                "2025-09-01--45.67-Amazon",
            ),
            (
                "2025-09-02",
                "Amazon",
                -23.99,
                shopping_id,
                account_id,
                "AMZN Mktp US*8Y",
                "2025-09-05T11:20:00",
                0.9,
                "rule:pattern",
                "2025-09-02--23.99-Amazon",
            ),
            (
                "2025-09-03",
                "Starbucks",
                -5.25,
                dining_id,
                account_id,
                "STARBUCKS #1234",
                "2025-09-05T12:00:00",
                0.8,
                "rule:pattern",
                "2025-09-03--5.25-Starbucks",
            ),
        ]
        connection.executemany(
            """
            INSERT INTO transactions (
                date, merchant, amount, category_id, account_id, original_description,
                import_date, categorization_confidence, categorization_method, fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            transactions,
        )


def test_build_prompt_single_statement(tmp_path: Path) -> None:
    config, _ = _prepare_config(tmp_path)
    categories = [
        {"category": "Shopping", "subcategory": "Online", "transaction_count": 128},
        {"category": "Food & Dining", "subcategory": "Coffee", "transaction_count": 52},
    ]
    merchants = [
        {"merchant": "Amazon", "count": 27},
        {"merchant": "Starbucks", "count": 14},
    ]
    text = """Statement Header\n09/01 Amazon 45.67 AMZN Mktp US*7X51S5QT3"""

    prompt = preprocess.build_prompt(
        [text],
        labels=["Chase_2025-09"],
        config=config,
        categories_data=categories,
        merchants_data=merchants,
    )

    assert "date,merchant,amount" in prompt
    assert "Known Merchants" in prompt
    assert "Chase_2025-09" in prompt
    assert "Amazon" in prompt


def test_build_prompt_batch(tmp_path: Path) -> None:
    config, _ = _prepare_config(tmp_path)
    categories = [
        {"category": "Shopping", "subcategory": "Online", "transaction_count": 128},
    ]
    merchants: list[dict[str, object]] = []
    texts = [
        "Header A\n08/01 Merchant A 10.00",
        "Header B\n08/02 Merchant B 20.00",
    ]

    prompt = preprocess.build_prompt(
        texts,
        labels=["Account-A", "Account-B"],
        config=config,
        categories_data=categories,
        merchants_data=merchants,
        categories_only=True,
    )

    assert "## Statement 1: Account-A" in prompt
    assert "## Statement 2: Account-B" in prompt
    assert "Known Merchants" not in prompt


def test_cli_writes_chunked_prompts(tmp_path: Path) -> None:
    config, env = _prepare_config(tmp_path)
    _seed_sample_data(config)

    inputs = []
    for idx in range(3):
        path = tmp_path / f"stmt_{idx + 1}.txt"
        path.write_text(f"Header {idx + 1}\n09/0{idx + 1} Example Merchant {idx}", encoding="utf-8")
        inputs.append(path)

    runner = CliRunner()
    output_path = tmp_path / "prompt.txt"
    result = runner.invoke(
        preprocess.cli,
        [
            *(arg for path in inputs for arg in ("--input", str(path))),
            "--batch",
            "--max-statements-per-prompt",
            "2",
            "--output",
            str(output_path),
            "--max-merchants",
            "5",
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    part1 = tmp_path / "prompt-part1.txt"
    part2 = tmp_path / "prompt-part2.txt"
    assert part1.exists()
    assert part2.exists()
    contents = part1.read_text(encoding="utf-8")
    assert "Known Merchants" in contents
    assert "Statement 1" in contents


def test_cli_writes_auto_named_prompt(tmp_path: Path) -> None:
    config, env = _prepare_config(tmp_path)
    (tmp_path / "statements").mkdir()
    scrubbed = tmp_path / "statements" / "demo-scrubbed.txt"
    scrubbed.write_text("Header\n09/01 Sample 10.00", encoding="utf-8")

    runner = CliRunner()
    workdir = tmp_path / "workspace"
    result = runner.invoke(
        preprocess.cli,
        [
            "--input",
            str(scrubbed),
            "--output-dir",
            str(workdir),
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    prompt_files = list((workdir / "prompts").glob("*.txt"))
    assert prompt_files, result.output
    prompt_path = prompt_files[0]
    assert prompt_path.name.endswith("-prompt.txt")
    text = prompt_path.read_text(encoding="utf-8")
    assert "date,merchant,amount" in text
