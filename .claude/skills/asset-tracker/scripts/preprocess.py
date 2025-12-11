"""Prompt builder for the asset-tracker skill.

Builds extraction prompts for investment/brokerage statements by loading
asset class taxonomy and existing instruments from the database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from fin_cli.shared.config import AppConfig, load_config
from fin_cli.shared.database import connect, run_migrations


def _resolve_templates_dir() -> Path:
    """Locate templates directory relative to this script."""
    candidates = [
        Path(__file__).with_name("templates"),
        Path(__file__).resolve().parent.parent / "templates",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Unable to locate prompt templates. Expected directories:\n"
        + "\n".join(str(path) for path in candidates)
    )


TEMPLATES_DIR = _resolve_templates_dir()
_TEMPLATE_FILE = "asset_extraction_prompt.txt"

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


def _ensure_database_ready(config: AppConfig) -> None:
    """Ensure the database exists and migrations are run."""
    db_path = config.database.path
    if not db_path.exists():
        run_migrations(config)


def _load_asset_classes(config: AppConfig) -> list[dict[str, object]]:
    """Load asset class taxonomy from the database."""
    with connect(config, read_only=True) as conn:
        cursor = conn.execute(
            """
            SELECT main_class, sub_class, vehicle_type_default
            FROM asset_classes
            ORDER BY main_class, sub_class
            """
        )
        rows = cursor.fetchall()
        return [
            {
                "main_class": row[0],
                "sub_class": row[1],
                "vehicle_type_default": row[2],
            }
            for row in rows
        ]


def _load_existing_instruments(config: AppConfig, limit: int = 100) -> list[dict[str, object]]:
    """Load existing instruments from the database for symbol matching."""
    with connect(config, read_only=True) as conn:
        cursor = conn.execute(
            """
            SELECT name, symbol, vehicle_type, currency
            FROM instruments
            ORDER BY name
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "name": row[0],
                "symbol": row[1],
                "vehicle_type": row[2],
                "currency": row[3],
            }
            for row in rows
        ]


def _render_prompt(
    *,
    statement: StatementChunk,
    asset_classes: list[dict[str, object]],
    existing_instruments: list[dict[str, object]],
) -> str:
    """Render the extraction prompt with taxonomy context."""
    template = _JINJA_ENV.get_template(_TEMPLATE_FILE)
    context = {
        "asset_classes": asset_classes,
        "existing_instruments": existing_instruments,
        "statement_text": f"## {statement.label}\n{statement.text}",
    }
    return template.render(context)


def build_prompt(
    scrubbed_text: str,
    *,
    label: str = "Statement",
    config: AppConfig | None = None,
    max_instruments: int = 100,
) -> str:
    """Build an asset extraction prompt from scrubbed statement text.

    Args:
        scrubbed_text: The PII-scrubbed statement text.
        label: Label for the statement (usually filename stem).
        config: Optional config; loads default if not provided.
        max_instruments: Maximum existing instruments to include for context.

    Returns:
        The rendered prompt ready to send to an LLM.
    """
    effective_config = config or load_config()
    _ensure_database_ready(effective_config)

    asset_classes = _load_asset_classes(effective_config)
    existing_instruments = _load_existing_instruments(effective_config, limit=max_instruments)

    statement = StatementChunk(label=label, text=scrubbed_text.strip())

    return _render_prompt(
        statement=statement,
        asset_classes=asset_classes,
        existing_instruments=existing_instruments,
    )


def _write_output(prompt: str, output_path: Path) -> None:
    """Write prompt to file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    required=False,
    help="Scrubbed statement text file.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Optional file path to write the prompt.",
)
@click.option(
    "--workdir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Asset-tracker workspace root. Auto-discovers inputs/outputs when provided.",
)
@click.option(
    "--max-instruments",
    type=int,
    default=100,
    show_default=True,
    help="Maximum existing instruments to include for context.",
)
@click.option(
    "--emit-json",
    is_flag=True,
    help="Print the taxonomy payload as JSON instead of rendering prompts.",
)
def cli(
    *,
    input_path: Path | None,
    output: Path | None,
    workdir: Path | None,
    max_instruments: int,
    emit_json: bool,
) -> None:
    """Build asset extraction prompts for scrubbed investment statements."""

    # Resolve workspace
    if workdir is not None:
        workdir = workdir.expanduser().resolve()
        if not workdir.exists():
            raise click.ClickException(f"Workspace {workdir} does not exist. Create it first with mkdir -p.")

        # Auto-discover input if not provided
        if input_path is None:
            candidates = sorted(workdir.glob("*-scrubbed.txt"))
            if not candidates:
                raise click.ClickException(f"No scrubbed statements found in {workdir}.")
            if len(candidates) > 1:
                raise click.ClickException(
                    f"Multiple scrubbed statements found. Specify --input or process one at a time."
                )
            input_path = candidates[0]

        # Auto-derive output
        if output is None:
            output = workdir / f"{input_path.stem.replace('-scrubbed', '')}-prompt.txt"

    if input_path is None:
        raise click.ClickException("Either --input or --workdir is required.")

    config = load_config()
    _ensure_database_ready(config)

    # Load taxonomy data
    asset_classes = _load_asset_classes(config)
    existing_instruments = _load_existing_instruments(config, limit=max_instruments)

    if emit_json:
        payload = {
            "asset_classes": asset_classes,
            "existing_instruments": existing_instruments,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    # Read and build prompt
    scrubbed_text = input_path.read_text(encoding="utf-8")
    prompt = build_prompt(
        scrubbed_text,
        label=input_path.stem.replace("-scrubbed", ""),
        config=config,
        max_instruments=max_instruments,
    )

    if output:
        _write_output(prompt, output)
        click.echo(f"Wrote prompt to {output}")
    else:
        click.echo(prompt)


if __name__ == "__main__":
    cli()
