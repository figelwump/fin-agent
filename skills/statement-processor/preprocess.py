"""Prompt builder utilities for the statement-processor skill."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import click
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from fin_cli.fin_query import executor
from fin_cli.shared.config import AppConfig, load_config

TEMPLATES_DIR = Path(__file__).with_name("templates")
_SINGLE_TEMPLATE = "extraction_prompt.txt"
_BATCH_TEMPLATE = "batch_extraction_prompt.txt"

_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
)


@dataclass(slots=True)
class StatementChunk:
    label: str
    text: str


def _load_merchants(
    *,
    config: AppConfig,
    limit: int | None,
    min_count: int,
) -> list[dict[str, object]]:
    result = executor.run_saved_query(
        config=config,
        name="merchants",
        runtime_params={"min_count": min_count},
        limit=limit,
    )
    if not result.rows:
        return []
    merchant_idx = result.columns.index("merchant")
    count_idx = result.columns.index("count")
    return [
        {
            "merchant": str(row[merchant_idx]),
            "count": int(row[count_idx]),
        }
        for row in result.rows
    ]


def _load_categories(*, config: AppConfig, limit: int | None = None) -> list[dict[str, object]]:
    runtime_params: dict[str, object] = {}
    if limit is not None:
        runtime_params["limit"] = limit
    result = executor.run_saved_query(
        config=config,
        name="categories",
        runtime_params=runtime_params,
        limit=limit,
    )
    if not result.rows:
        return []
    category_idx = result.columns.index("category")
    subcategory_idx = result.columns.index("subcategory")
    tx_count_idx = result.columns.index("transaction_count") if "transaction_count" in result.columns else None
    return [
        {
            "category": str(row[category_idx]),
            "subcategory": str(row[subcategory_idx]),
            "transaction_count": int(row[tx_count_idx]) if tx_count_idx is not None and row[tx_count_idx] is not None else None,
        }
        for row in result.rows
    ]


def _render_prompt(
    *,
    statements: Sequence[StatementChunk],
    categories: Sequence[dict[str, object]],
    merchants: Sequence[dict[str, object]],
) -> str:
    template_name = _SINGLE_TEMPLATE if len(statements) == 1 else _BATCH_TEMPLATE
    template = _JINJA_ENV.get_template(template_name)
    if len(statements) == 1:
        context = {
            "categories": categories,
            "merchants": merchants,
            "statement_text": statements[0].text,
        }
    else:
        context = {
            "categories": categories,
            "merchants": merchants,
            "statements": [
                {
                    "label": chunk.label,
                    "text": chunk.text,
                }
                for chunk in statements
            ],
        }
    return template.render(context)


def build_prompt(
    scrubbed_texts: Sequence[str],
    *,
    labels: Sequence[str] | None = None,
    config: AppConfig | None = None,
    max_merchants: int | None = None,
    min_merchant_count: int = 1,
    categories_only: bool = False,
    categories_limit: int | None = None,
    categories_data: Sequence[dict[str, object]] | None = None,
    merchants_data: Sequence[dict[str, object]] | None = None,
) -> str:
    if not scrubbed_texts:
        raise ValueError("At least one scrubbed statement is required.")
    if labels and len(labels) != len(scrubbed_texts):
        raise ValueError("labels length must match scrubbed_texts length when provided.")

    effective_config = config or load_config()
    categories = list(categories_data) if categories_data is not None else _load_categories(
        config=effective_config,
        limit=categories_limit,
    )
    merchants: list[dict[str, object]]
    if categories_only:
        merchants = [] if merchants_data is None else list(merchants_data)
    else:
        if merchants_data is not None:
            merchants = list(merchants_data)
        else:
            merchants = _load_merchants(
                config=effective_config,
                limit=max_merchants,
                min_count=min_merchant_count,
            )

    statements = [
        StatementChunk(
            label=labels[idx] if labels else f"Statement {idx + 1}",
            text=text.strip(),
        )
        for idx, text in enumerate(scrubbed_texts)
    ]

    if len(statements) == 1:
        single = statements[0]
        single_text = f"## {single.label}\n{single.text}"
        return _render_prompt(
            statements=[StatementChunk(label=single.label, text=single_text)],
            categories=categories,
            merchants=merchants,
        )

    return _render_prompt(statements=statements, categories=categories, merchants=merchants)


def _chunk_inputs(
    items: Sequence[StatementChunk],
    *,
    max_per_chunk: int | None,
) -> list[list[StatementChunk]]:
    if max_per_chunk is None or max_per_chunk <= 0 or len(items) <= max_per_chunk:
        return [list(items)]
    return [list(items[idx : idx + max_per_chunk]) for idx in range(0, len(items), max_per_chunk)]


def _read_inputs(paths: Iterable[Path]) -> list[StatementChunk]:
    chunks: list[StatementChunk] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        chunks.append(StatementChunk(label=path.stem, text=text.strip()))
    return chunks


def _write_output(prompt: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")


@click.command()
@click.option(
    "--input",
    "input_paths",
    multiple=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    required=True,
    help="Scrubbed statement text files to include in the prompt.",
)
@click.option("--output", type=click.Path(path_type=Path), help="Optional file path to write the prompt.")
@click.option("--batch", is_flag=True, help="Treat multiple inputs as a batch (default when >1 file).")
@click.option("--max-merchants", type=int, help="Limit the number of merchants included in the taxonomy block.")
@click.option("--min-merchant-count", type=int, default=1, show_default=True, help="Ignore merchants with fewer than this many transactions.")
@click.option("--categories-only", is_flag=True, help="Skip merchant taxonomy and include categories only.")
@click.option(
    "--max-statements-per-prompt",
    type=int,
    help="Auto-chunk batches larger than this many statements per prompt.",
)
@click.option(
    "--categories-limit",
    type=int,
    help="Optional upper bound on the number of categories to include.",
)
@click.option("--json", "--emit-json", "emit_json", is_flag=True, help="Print the taxonomy payload as JSON instead of rendering prompts.")
def cli(
    *,
    input_paths: tuple[Path, ...],
    output: Path | None,
    batch: bool,
    max_merchants: int | None,
    min_merchant_count: int,
    categories_only: bool,
    max_statements_per_prompt: int | None,
    categories_limit: int | None,
    emit_json: bool,
) -> None:
    """Build extraction prompts for scrubbed statement text."""

    statements = _read_inputs(input_paths)
    if len(statements) > 1 and not batch:
        batch = True

    config = load_config()
    categories = _load_categories(config=config, limit=categories_limit)
    merchants: list[dict[str, object]] = []
    if not categories_only:
        merchants = _load_merchants(config=config, limit=max_merchants, min_count=min_merchant_count)

    if emit_json:
        payload = {
            "categories": categories,
            "merchants": merchants,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    chunks = _chunk_inputs(statements, max_per_chunk=max_statements_per_prompt if batch else None)

    prompts: list[str] = []
    for chunk in chunks:
        chunk_labels = [s.label for s in chunk]
        chunk_texts = [s.text for s in chunk]
        prompt = build_prompt(
            chunk_texts,
            labels=chunk_labels,
            config=config,
            max_merchants=max_merchants,
            min_merchant_count=min_merchant_count,
            categories_only=categories_only,
            categories_limit=categories_limit,
            categories_data=categories,
            merchants_data=merchants,
        )
        prompts.append(prompt)

    if output:
        if len(prompts) == 1:
            _write_output(prompts[0], output)
            click.echo(f"Wrote prompt to {output}")
        else:
            base = output
            suffix = base.suffix
            stem = base.stem
            parent = base.parent
            for idx, prompt in enumerate(prompts, start=1):
                chunk_path = parent / f"{stem}-part{idx}{suffix or '.txt'}"
                _write_output(prompt, chunk_path)
                click.echo(f"Wrote prompt chunk {idx} to {chunk_path}")
    else:
        for idx, prompt in enumerate(prompts, start=1):
            if len(prompts) > 1:
                click.echo(f"----- PROMPT {idx}/{len(prompts)} -----")
            click.echo(prompt)
            if len(prompts) > 1 and idx != len(prompts):
                click.echo()


if __name__ == "__main__":  # pragma: no cover
    cli()
