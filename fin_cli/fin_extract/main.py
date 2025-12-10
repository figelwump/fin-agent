"""fin-extract CLI entrypoint."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import replace
from io import StringIO
from pathlib import Path

import click

from fin_cli.fin_edit.main import _process_asset_payload
from fin_cli.shared.cli import CLIContext, common_cli_options, handle_cli_errors, pass_cli_context
from fin_cli.shared.database import connect
from fin_cli.shared.models import compute_account_key

from .asset_contract import validate_asset_payload


class ExtractDefaultGroup(click.Group):
    """Click group that falls back to a default command when none is provided."""

    def __init__(self, *args, default_command: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._default_command = default_command

    def resolve_command(self, ctx: click.Context, args: list[str]):
        if self._default_command is None:
            return super().resolve_command(ctx, args)

        if not args:
            return super().resolve_command(ctx, [self._default_command])

        cmd = super().get_command(ctx, args[0])
        if cmd is not None:
            return super().resolve_command(ctx, args)

        return super().resolve_command(ctx, [self._default_command] + args)


from .declarative import DeclarativeExtractor, load_spec
from .extractors import REGISTRY, detect_extractor, ensure_bundled_specs_loaded
from .parsers.pdf_loader import PdfDocument, load_pdf_document_with_engine
from .plugin_loader import PluginLoadReport, load_user_plugins
from .types import ExtractedTransaction, ExtractionResult, StatementMetadata


def load_pdf_document(
    pdf_file: str | Path,
    *,
    engine: str,
    enable_camelot_fallback: bool = False,
) -> PdfDocument:
    """Backward-compatible wrapper around `load_pdf_document_with_engine`.

    Older tests and integrations monkeypatch `fin_cli.fin_extract.main.load_pdf_document`.
    Keeping this thin proxy preserves that surface while forwarding to the engine-aware loader.
    """

    return load_pdf_document_with_engine(
        pdf_file,
        engine=engine,
        enable_camelot_fallback=enable_camelot_fallback,
    )


@click.group(
    help="Extract transactions from financial PDFs.",
    invoke_without_command=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    cls=ExtractDefaultGroup,
    default_command="extract",
)
@click.option("--no-plugins", is_flag=True, help="Disable loading user plugins for this run.")
@click.option(
    "--allow-plugin",
    "allowed_plugins",
    multiple=True,
    help="Only load the specified plugin names (case-insensitive).",
)
@common_cli_options(run_migrations_on_start=False)
@click.pass_context
@handle_cli_errors
def main(
    ctx: click.Context,
    no_plugins: bool,
    allowed_plugins: tuple[str, ...],
    cli_ctx: CLIContext,
) -> None:
    plugin_args = {
        "disable_plugins": no_plugins,
        "allowed_plugins": allowed_plugins,
    }
    cli_ctx.state["fin_extract_plugin_cli_args"] = plugin_args

    return


@main.command("extract", hidden=True)
@click.argument("pdf_file", type=click.Path(path_type=str), required=True)
@click.option("--output", "output_path", type=click.Path(path_type=str), help="Output CSV to file.")
@click.option("--stdout", is_flag=True, help="Output CSV to stdout.")
@click.option("--account-name", type=str, help="Override auto-detected account name.")
@click.option(
    "--engine",
    type=click.Choice(["auto", "pdfplumber"], case_sensitive=False),
    help="PDF parsing engine to use (default: from config or 'auto')",
)
@click.option(
    "--spec",
    type=click.Path(exists=True, path_type=str),
    help="Use a declarative YAML spec instead of built-in extractors.",
)
@click.option(
    "--dry-run",
    "_dry_run_flag",
    is_flag=True,
    expose_value=False,
    help="Preview actions without side effects.",
    callback=lambda ctx, param, value: _mark_dry_run(ctx, value),
)
@handle_cli_errors
@pass_cli_context
def extract_command(
    cli_ctx: CLIContext,
    pdf_file: str,
    output_path: str | None,
    stdout: bool,
    account_name: str | None,
    engine: str | None,
    spec: str | None,
) -> None:
    plugin_args = cli_ctx.state.get(
        "fin_extract_plugin_cli_args",
        {"disable_plugins": False, "allowed_plugins": ()},
    )
    _run_extract(
        pdf_file=pdf_file,
        output_path=output_path,
        stdout=stdout,
        account_name=account_name,
        engine=engine,
        spec=spec,
        cli_ctx=cli_ctx,
        disable_plugins=plugin_args.get("disable_plugins", False),
        allowed_plugins=plugin_args.get("allowed_plugins", ()),
    )


def _run_extract(
    *,
    pdf_file: str,
    output_path: str | None,
    stdout: bool,
    account_name: str | None,
    engine: str | None,
    spec: str | None,
    cli_ctx: CLIContext,
    disable_plugins: bool,
    allowed_plugins: Sequence[str],
) -> None:
    selected_engine = engine if engine else cli_ctx.config.extraction.engine

    cli_ctx.logger.info(f"Using PDF engine: {selected_engine}")

    plugin_report = _initialize_plugins(
        cli_ctx,
        disable_plugins=disable_plugins,
        cli_allowed_plugins=allowed_plugins,
    )

    document = load_pdf_document(
        pdf_file,
        engine=selected_engine,
        enable_camelot_fallback=cli_ctx.config.extraction.camelot_fallback_enabled,
    )

    if spec:
        cli_ctx.logger.info(f"Loading declarative spec: {spec}")
        spec_obj = load_spec(spec)
        extractor = DeclarativeExtractor(spec_obj)
        cli_ctx.logger.info(f"Using declarative extractor: {extractor.name}")
    else:
        if plugin_report is not None:
            cli_ctx.logger.debug(
                "Plugin discovery registered "
                f"{_count_registered(plugin_report)} extractors "
                f"({_count_registered(plugin_report, kind='user_yaml')} YAML, "
                f"{_count_registered(plugin_report, kind='python')} Python)."
            )
        extractor = detect_extractor(
            document,
            allowed_institutions=cli_ctx.config.extraction.supported_banks,
        )
        extractor_kind = _humanize_kind(getattr(extractor, "__plugin_kind__", "builtin_python"))
        cli_ctx.logger.info(f"Detected format: {extractor.name} ({extractor_kind})")

    result = extractor.extract(document)
    if not result.transactions:
        raise click.ClickException("No transactions were extracted from the document.")

    if account_name:
        result = replace(result, metadata=replace(result.metadata, account_name=account_name))

    cli_ctx.logger.info(
        f"Account: {result.metadata.account_name} ({result.metadata.institution}) | "
        f"Transactions: {len(result.transactions)}"
    )

    if cli_ctx.dry_run:
        _emit_dry_run_summary(cli_ctx, extractor.name, result)
        return

    auto_output_path: Path | None = None
    if not output_path and not stdout:
        default_dir = Path("output")
        auto_output_path = default_dir / (Path(pdf_file).stem + ".csv")
        output_path = str(auto_output_path)
        cli_ctx.logger.info(
            f"No --output provided; defaulting to {auto_output_path} in the output directory."
        )
    if output_path and stdout:
        raise click.UsageError("Cannot use both --output and --stdout simultaneously.")

    use_stdout = stdout and not output_path
    _write_csv_output(result, output_path if not use_stdout else None, cli_ctx)
    destination = "sent to stdout" if use_stdout else f"written to {output_path}"
    cli_ctx.logger.success(f"Extraction complete. Output {destination}.")


@main.command("asset-json")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional path to write validated/normalised JSON.",
)
@click.option(
    "--apply",
    "apply_import",
    is_flag=True,
    help="If set, import into the DB via fin-edit asset ingest (otherwise validation only).",
)
@handle_cli_errors
@pass_cli_context
def asset_json(
    cli_ctx: CLIContext,
    input_path: Path,
    output_path: Path | None,
    apply_import: bool,
) -> None:
    """Validate a normalized asset JSON payload and optionally import it."""

    raw_text = input_path.read_text()
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - surfaced via Click
        raise click.ClickException(f"Invalid JSON: {exc}") from exc

    errors = validate_asset_payload(payload)
    if errors:
        formatted = "\n - " + "\n - ".join(errors)
        raise click.ClickException(f"Asset payload invalid:{formatted}")

    if output_path:
        output_path.write_text(json.dumps(payload, indent=2))
        cli_ctx.logger.info(f"Wrote validated payload to {output_path}")

    preview = cli_ctx.dry_run or not apply_import
    if not apply_import:
        cli_ctx.logger.success("Payload validated (no import performed). Use --apply to ingest.")
        return

    with connect(cli_ctx.config, read_only=False) as connection:
        inserted = _process_asset_payload(
            connection, payload=payload, preview=preview, logger=cli_ctx.logger
        )
    if not preview:
        cli_ctx.logger.success(f"Imported asset payload rows: holding_values={inserted}")


def _mark_dry_run(ctx: click.Context, value: bool) -> None:
    if value and isinstance(ctx.obj, CLIContext):
        ctx.obj.dry_run = True


def _describe_registry() -> Iterable[dict[str, object]]:
    primary_types = set(REGISTRY.iter_types())
    for extractor_cls in REGISTRY.iter_types(include_alternates=True):
        origin = getattr(extractor_cls, "__origin__", extractor_cls.__module__)
        kind = _humanize_kind(getattr(extractor_cls, "__plugin_kind__", "builtin_python"))
        yield {
            "name": extractor_cls.name,
            "origin": origin,
            "kind": kind,
            "primary": extractor_cls in primary_types,
        }


def _humanize_kind(raw_kind: str) -> str:
    mapping = {
        "builtin_python": "built-in python",
        "bundled_yaml": "bundled yaml",
        "user_yaml": "user yaml",
        "python_user": "user python",
    }
    return mapping.get(raw_kind, raw_kind)


@main.group("dev")
@pass_cli_context
def dev_group(cli_ctx: CLIContext) -> None:
    """Developer tooling for plugin workflows."""
    cli_ctx.state.setdefault(
        "fin_extract_plugin_cli_args",
        {"disable_plugins": False, "allowed_plugins": ()},
    )


@dev_group.command("list-plugins")
@pass_cli_context
def dev_list_plugins(cli_ctx: CLIContext) -> None:
    """List all registered extractors and their plugin origins."""

    plugin_args = cli_ctx.state.get(
        "fin_extract_plugin_cli_args",
        {"disable_plugins": False, "allowed_plugins": ()},
    )
    report = _initialize_plugins(
        cli_ctx,
        disable_plugins=plugin_args.get("disable_plugins", False),
        cli_allowed_plugins=plugin_args.get("allowed_plugins", ()),
    )

    entries = list(_describe_registry())
    if not entries:
        cli_ctx.logger.info("No extractors registered.")
        return

    cli_ctx.logger.info("Registered extractors:")
    for entry in entries:
        status = "primary" if entry["primary"] else "alternate"
        cli_ctx.logger.info(
            f"  - {entry['name']} ({status}) → {entry['kind']} [source: {entry['origin']}]"
        )

    if report:
        for failure in report.failures:
            cli_ctx.logger.warning(
                f"Plugin load failure for {failure.source}: {failure.message or 'unknown error'}"
            )
        for skipped in report.skipped:
            if skipped.message:
                cli_ctx.logger.debug(f"Skipped plugin {skipped.source}: {skipped.message}")


@dev_group.command("validate-spec")
@click.argument("yaml_path", type=click.Path(exists=True, path_type=str))
@pass_cli_context
def dev_validate_spec(cli_ctx: CLIContext, yaml_path: str) -> None:
    """Validate a declarative extractor spec without registering it."""

    cli_ctx.logger.info(f"Validating spec: {yaml_path}")
    try:
        spec = load_spec(yaml_path)
    except Exception as exc:  # pragma: no cover - validation errors bubble up
        raise click.ClickException(f"Spec validation failed: {exc}") from exc

    DeclarativeExtractor(spec)
    cli_ctx.logger.info(
        f"Spec '{spec.name}' loaded successfully for institution '{spec.institution}'."
    )

    existing_names = {cls.name for cls in REGISTRY.iter_types(include_alternates=True)}
    if spec.name in existing_names:
        cli_ctx.logger.warning(
            "An extractor with this name is already registered; installing this spec will override the existing version."
        )

    fields_missing = [
        field
        for field in ("columns", "dates", "sign_classification", "detection")
        if not getattr(spec, field)
    ]
    if fields_missing:
        cli_ctx.logger.warning(
            "The spec is missing optional sections: " + ", ".join(fields_missing)
        )
    else:
        cli_ctx.logger.success("Spec structure validated successfully.")

    sample_keys = ["keywords_all", "keywords_any"]
    missing_detection = [key for key in sample_keys if not getattr(spec.detection, key)]
    if missing_detection:
        cli_ctx.logger.warning(
            "Consider populating detection." + " Missing: " + ", ".join(missing_detection)
        )
    else:
        cli_ctx.logger.debug("Detection keywords provided.")


def _emit_dry_run_summary(
    cli_ctx: CLIContext,
    extractor_name: str,
    result: ExtractionResult,
) -> None:
    cli_ctx.logger.info("Dry run summary:")
    cli_ctx.logger.info(f"  Format detected: {extractor_name}")
    cli_ctx.logger.info(f"  Account name: {result.metadata.account_name}")
    cli_ctx.logger.info(f"  Institution: {result.metadata.institution}")
    cli_ctx.logger.info(f"  Account type: {result.metadata.account_type}")
    cli_ctx.logger.info(f"  Transactions: {len(result.transactions)}")
    if result.metadata.start_date and result.metadata.end_date:
        cli_ctx.logger.info(
            f"  Date range: {result.metadata.start_date.isoformat()} to {result.metadata.end_date.isoformat()}"
        )


def _write_csv_output(
    result: ExtractionResult,
    output_path: str | None,
    cli_ctx: CLIContext,
) -> None:
    rows = _render_csv_rows(result.transactions, result.metadata)
    header = [
        "date",
        "merchant",
        "amount",
        "original_description",
        "account_name",
        "institution",
        "account_type",
        "account_key",
    ]
    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
    else:
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        writer.writerows(rows)
        click.echo(buffer.getvalue().strip())


def _render_csv_rows(
    transactions: Iterable[ExtractedTransaction],
    metadata: StatementMetadata,
) -> list[list[str]]:
    rows: list[list[str]] = []
    account_key = compute_account_key(
        metadata.account_name, metadata.institution, metadata.account_type
    )
    for txn in transactions:
        rows.append(
            [
                txn.date.isoformat(),
                txn.merchant,
                f"{txn.amount:.2f}",
                txn.original_description,
                metadata.account_name,
                metadata.institution,
                metadata.account_type,
                account_key,
            ]
        )
    return rows


if __name__ == "__main__":  # pragma: no cover
    main()


def _initialize_plugins(
    cli_ctx: CLIContext,
    *,
    disable_plugins: bool,
    cli_allowed_plugins: Sequence[str],
) -> PluginLoadReport | None:
    ensure_bundled_specs_loaded()

    # Avoid loading multiple times if already done during this invocation.
    state_key = "fin_extract_plugin_report"
    if state_key in cli_ctx.state:
        return cli_ctx.state[state_key]

    extraction_cfg = cli_ctx.config.extraction
    if not extraction_cfg.enable_plugins or disable_plugins:
        cli_ctx.logger.info("Plugin discovery disabled (configuration or CLI override).")
        cli_ctx.state[state_key] = None
        return None

    allowed: set[str] | None
    if cli_allowed_plugins:
        allowed = {name.lower() for name in cli_allowed_plugins}
    elif extraction_cfg.plugin_allowlist:
        allowed = {name.lower() for name in extraction_cfg.plugin_allowlist}
    else:
        allowed = None

    blocked = {name.lower() for name in extraction_cfg.plugin_blocklist}

    plugin_paths = tuple(str(path) for path in extraction_cfg.plugin_paths)
    report = load_user_plugins(
        REGISTRY,
        plugin_paths,
        allowed_names=allowed,
        blocked_names=blocked,
    )

    registered_total = _count_registered(report)
    yaml_registered = _count_registered(report, kind="user_yaml")
    python_registered = _count_registered(report, kind="python")
    if registered_total:
        cli_ctx.logger.info(
            "Loaded %d plugin extractors (%d YAML, %d Python).",
            registered_total,
            yaml_registered,
            python_registered,
        )
        for event in report.registered:
            cli_ctx.logger.debug(
                f"Registered plugin {event.name} from {event.source} ({_humanize_kind(event.kind)})"
            )
    else:
        cli_ctx.logger.info("No user plugins discovered.")

    for failure in report.failures:
        cli_ctx.logger.warning(
            "Plugin load failure for %s: %s",
            failure.source,
            failure.message or "unknown error",
        )

    cli_ctx.state[state_key] = report
    return report


def _count_registered(report: PluginLoadReport, *, kind: str | None = None) -> int:
    if kind is None:
        return len(report.registered)
    return sum(1 for event in report.registered if event.kind == kind)
