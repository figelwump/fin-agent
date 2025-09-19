"""fin-export CLI entrypoint (stub)."""

import click


@click.group(help="Export financial data (implementation pending).")
def cli() -> None:
    """Top-level command group."""


@cli.command("markdown")
@click.option("--month", type=str, help="Month to export (YYYY-MM).")
@click.option("--output", type=click.Path(path_type=str), help="Output file path (default stdout).")
@click.option("--sections", type=str, help="Comma-separated sections to include.")
@click.option("--period", type=str, help="Include multi-period trends (e.g., 6m).")
@click.option("--template", type=click.Path(path_type=str), help="Custom Markdown template path.")
@click.option("--db", type=click.Path(path_type=str), help="Override database path.")
def export_markdown(month: str | None, output: str | None, sections: str | None, period: str | None, template: str | None, db: str | None) -> None:
    """Placeholder for Markdown export functionality."""
    raise click.ClickException("fin-export markdown generation arrives in Phase 9.")


def main() -> None:
    """Entry point for console_scripts."""
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()
