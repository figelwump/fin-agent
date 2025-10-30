"""fin-analyze CLI entrypoint."""

from __future__ import annotations

from typing import Sequence

import click

from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors

from . import registry, temporal
from . import render as result_render
from .types import (
    AnalysisConfigurationError,
    AnalysisContext,
    AnalysisError,
    AnalysisNotImplementedError,
    AnalysisRequest,
    AnalyzerHelpRequested,
)


HELP_TEXT = (
    "Run financial analyses against the local dataset.\n\n"
    "\b\n"  # Preserve the catalog formatting in Click's help output.
    + registry.format_catalog()
)


@click.command(help=HELP_TEXT, context_settings={'ignore_unknown_options': True})
@click.argument("analysis_type", type=str, required=False)
@click.argument("analysis_args", nargs=-1, type=str)
@click.option("--month", type=str, help="Analyse a specific month (YYYY-MM).")
@click.option("--period", type=str, help="Analyse a relative period, e.g., 3m, 6w, 30d.")
@click.option("--year", type=int, help="Analyse a specific calendar year (e.g., 2024).")
@click.option(
    "--last-12-months",
    "last_twelve_months",
    is_flag=True,
    help="Analyse the trailing 12 full months ending this month.",
)
@click.option(
    "--format",
    "output_format",
    default="text",
    show_default=True,
    type=click.Choice(["text", "json", "csv"]),
)
@click.option("--compare", is_flag=True, help="Compare against the immediately preceding window.")
@click.option("--threshold", type=float, help="Global minimum significance threshold.")
@click.option("--help-list", is_flag=True, help="List available analysis types and exit.")
@common_cli_options
@handle_cli_errors
def main(
    analysis_type: str | None,
    analysis_args: Sequence[str],
    month: str | None,
    period: str | None,
    year: int | None,
    last_twelve_months: bool,
    output_format: str,
    compare: bool,
    threshold: float | None,
    help_list: bool,
    cli_ctx: CLIContext,
) -> None:
    """Resolve CLI inputs, dispatch analyzers, and handle basic rendering orchestration."""

    if help_list:
        click.echo(registry.format_catalog())
        return

    if not analysis_type:
        raise click.ClickException("Specify an analysis type or use --help-list to see options.")

    spec = registry.get_spec(analysis_type)

    # Support `fin-analyze <type> --help` for analyzer-specific flags.
    try:
        parsed_analyzer_args = registry.parse_analyzer_args(spec, analysis_args)
    except AnalyzerHelpRequested as help_exc:
        click.echo(help_exc.args[0])
        return

    windows = temporal.resolve_windows(
        month=month,
        period=period,
        year=year,
        last_twelve_months=last_twelve_months,
        compare=compare,
        app_config=cli_ctx.config,
    )

    comparison_label = windows.comparison.label if windows.comparison else None
    debug_message = (
        f"Resolved analysis window {windows.window.label} ({windows.window.start} to {windows.window.end})"
    )
    if comparison_label is not None:
        debug_message += f", comparison={comparison_label}"
    cli_ctx.logger.debug(debug_message)

    request = AnalysisRequest(
        analysis_type=spec.slug,
        options=parsed_analyzer_args,
        output_format=output_format,
        compare=compare,
        threshold=threshold,
        window=windows.window,
        comparison_window=windows.comparison,
    )

    context = AnalysisContext(
        cli_ctx=cli_ctx,
        app_config=cli_ctx.config,
        window=windows.window,
        comparison_window=windows.comparison,
        output_format=output_format,
        compare=compare,
        threshold=threshold,
        options=parsed_analyzer_args,
    )

    cli_ctx.logger.debug(
        f"Dispatching analysis '{spec.slug}' with options {parsed_analyzer_args}"
    )
    analyzer = spec.factory
    try:
        result = analyzer(context)
        result_render.render_result(
            result,
            output_format=output_format,
            logger=cli_ctx.logger,
        )
    except AnalysisNotImplementedError as exc:
        raise click.ClickException(str(exc)) from exc
    except AnalysisConfigurationError:
        raise
    except AnalysisError as exc:
        raise click.ClickException(str(exc)) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except NotImplementedError as exc:  # pragma: no cover - defensive fallback
        raise click.ClickException(f"Analyzer '{spec.slug}' is not yet implemented.") from exc

    cli_ctx.state["last_analysis_result"] = result
    if cli_ctx.verbose:
        cli_ctx.logger.info(
            f"Analysis '{spec.slug}' completed (result stored for rendering)."
        )


if __name__ == "__main__":  # pragma: no cover
    main()
