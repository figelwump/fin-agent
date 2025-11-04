"""fin-export CLI entrypoint."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import click

from fin_cli.fin_export import (
    ExportError,
    build_report,
    infer_format,
    render_json,
    render_markdown,
    resolve_section_specs,
)
from fin_cli.shared.cli import (
    CLIContext,
    common_cli_options,
    handle_cli_errors,
)


@click.command(help="Export financial analyses as Markdown or JSON reports.")
@click.option("--month", type=str, help="Month to export (YYYY-MM).")
@click.option(
    "--period", type=str, help="Relative period (e.g., 3m, 12w) covering the report window."
)
@click.option("--sections", type=str, help="Comma-separated sections to include (default all).")
@click.option(
    "--format",
    "export_format",
    type=click.Choice(["markdown", "json"]),
    help="Output format for the report (defaults to Markdown unless output path implies JSON).",
)
@click.option("--output", type=click.Path(path_type=str), help="Output file path (default stdout).")
@click.option("--template", type=click.Path(path_type=str), help="Custom Markdown template path.")
@click.option("--threshold", type=float, help="Significance threshold for analyzer comparisons.")
@click.option("--no-compare", is_flag=True, help="Skip comparison against the preceding window.")
@common_cli_options
@handle_cli_errors
def cli(
    month: str | None,
    period: str | None,
    sections: str | None,
    export_format: str,
    output: str | None,
    template: str | None,
    threshold: float | None,
    no_compare: bool,
    cli_ctx: CLIContext,
) -> None:
    """Generate Markdown or JSON financial reports."""

    section_list = _parse_sections(sections)
    try:
        resolved_specs = resolve_section_specs(section_list)
    except ExportError as exc:
        raise click.ClickException(str(exc)) from exc

    output_path = Path(output).expanduser() if output else None
    format_choice = export_format or infer_format(output_path, None)
    if format_choice is None:
        format_choice = "markdown"
    if format_choice not in {"markdown", "json"}:
        raise click.ClickException(f"Unsupported format '{format_choice}'.")

    if output_path:
        _validate_output_suffix(output_path, format_choice)

    template_path = Path(template).expanduser() if template else None
    if template_path and not template_path.exists():
        raise click.ClickException(f"Template path '{template_path}' does not exist.")

    compare = not no_compare

    try:
        metadata, section_outputs = build_report(
            cli_ctx,
            sections=resolved_specs,
            month=month,
            period=period,
            compare=compare,
            threshold=threshold,
        )
    except ExportError as exc:
        raise click.ClickException(str(exc)) from exc

    if format_choice == "json":
        rendered = render_json(metadata, section_outputs)
    else:
        rendered = render_markdown(metadata, section_outputs, template_path=template_path)

    _write_output(rendered, output_path)

    if output_path:
        section_labels = ", ".join(section.slug for section in section_outputs)
        cli_ctx.logger.info(
            f"Generated fin-export report ({format_choice}) → {output_path} [sections: {section_labels}]"
        )
    else:
        section_labels = ", ".join(section.slug for section in section_outputs)
        cli_ctx.logger.debug(
            f"Generated fin-export report ({format_choice}) → stdout [sections: {section_labels}]"
        )


def main() -> None:
    """Entry point for console_scripts."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()


def _parse_sections(raw: str | None) -> Sequence[str] | None:
    if raw is None:
        return None
    parts = [segment.strip() for segment in raw.split(",") if segment.strip()]
    return parts or None


def _validate_output_suffix(path: Path, format_choice: str) -> None:
    suffix = path.suffix.lower()
    if format_choice == "json" and suffix not in {".json"}:
        raise click.ClickException("Use a .json extension when --format json.")
    if format_choice == "markdown" and suffix not in {".md", ".markdown"}:
        raise click.ClickException("Use a .md or .markdown extension for Markdown output.")


def _write_output(content: str, path: Path | None) -> None:
    if path is None:
        click.echo(content, nl=False)
        if not content.endswith("\n"):
            click.echo()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
