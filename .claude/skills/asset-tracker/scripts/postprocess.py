"""Postprocessor for the asset-tracker skill.

Validates LLM-extracted asset JSON, auto-classifies instruments,
and prepares the payload for import via fin-extract asset-json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from fin_cli.fin_extract.asset_contract import validate_asset_payload
from fin_cli.shared.config import AppConfig, load_config
from fin_cli.shared.database import connect, run_migrations
from fin_cli.shared.utils import compute_file_sha256


# Auto-classification rules based on security name and vehicle type
_CLASSIFICATION_RULES: list[tuple[str, str, str, str | None]] = [
    # (pattern, main_class, sub_class, vehicle_type_hint)
    # Cash/Money Market (use MMF vehicle type - 'cash' is not a valid vehicle_type)
    (r"(?i)sweep|fdic|deposit", "cash", "cash sweep", "MMF"),
    (r"(?i)money market|treasury fund|SIOXX|SWVXX|VMFXX", "cash", "money market", "MMF"),
    (r"(?i)savings", "cash", "savings", None),

    # Alternatives - Private Equity
    (r"(?i)private equity|PE fund", "alternatives", "private equity", "fund_LP"),
    (r"(?i)canyon|SL partners|strategic value|icapital|K5 private", "alternatives", "private equity", "fund_LP"),
    (r"(?i)venture|VC|angel", "alternatives", "VC/Angel", "fund_LP"),

    # Alternatives - Real Estate
    (r"(?i)real estate|REIT|BREIT|blackstone.*income trust", "alternatives", "real estate fund", "fund_LP"),

    # Alternatives - Credit/BDC
    (r"(?i)BDC|debt solutions|private credit|tactical.*credit|apollo.*debt", "alternatives", "private equity", "fund_LP"),

    # Alternatives - Hedge Funds
    (r"(?i)hedge fund|distressed|dislocation|opportunit", "alternatives", "hedge fund", "fund_LP"),

    # Alternatives - Commodities
    (r"(?i)gold|silver|platinum|palladium|bullion", "alternatives", "commodities", "note"),
    (r"(?i)commodity|GLD|SLV|IAU", "alternatives", "commodities", "ETF"),

    # Alternatives - Crypto
    (r"(?i)bitcoin|ethereum|crypto|BTC|ETH", "alternatives", "crypto", "crypto"),

    # Bonds
    (r"(?i)treasury|T-bill|T-note|govt bond", "bonds", "treasury", "bond"),
    (r"(?i)municipal|muni", "bonds", "muni", "bond"),
    (r"(?i)corporate.*bond|investment grade", "bonds", "corporate IG", "bond"),
    (r"(?i)high yield|junk bond", "bonds", "corporate HY", "bond"),
    (r"(?i)TIPS|inflation", "bonds", "TIPS", "bond"),

    # Equities - ETFs (check before individual stocks)
    (r"(?i)iShares|Vanguard.*ETF|SPDR|Schwab.*ETF", "equities", "US equity", "ETF"),
    (r"(?i)(?:^|\s)ETF(?:$|\s)|exchange.traded", "equities", "US equity", "ETF"),
    (r"(?i)ACWI|VTI|SPY|QQQ|VIG|SCHB|VOO", "equities", "US equity", "ETF"),
    (r"(?i)emerging|EEM|VWO|IEMG", "equities", "emerging markets", "ETF"),
    (r"(?i)international|intl|foreign|EFA|VEA|VXUS", "equities", "intl equity", "ETF"),
    (r"(?i)small.cap|IWM|VB|SCHA", "equities", "small cap", "ETF"),

    # Equities - Individual Stocks
    (r"(?i)(?:Inc\.|Corp\.|Corporation|Company|Ltd|LLC)$", "equities", "US equity", "stock"),

    # Options
    (r"(?i)call|put|option|strike|expir", "other", "options", "option"),

    # Structured Products
    (r"(?i)structured|note|linked", "other", "structured product", "note"),
]


def _classify_instrument(name: str, vehicle_type: str | None) -> tuple[str, str] | None:
    """
    Auto-classify an instrument based on its name and vehicle type.

    Returns (main_class, sub_class) or None if no rule matches.
    """
    # Check each rule
    for pattern, main_class, sub_class, vt_hint in _CLASSIFICATION_RULES:
        if re.search(pattern, name):
            # Rule has a vehicle_type hint - only match if actual type matches the hint
            # (or if no actual type is known)
            if vt_hint is not None:
                if vehicle_type is not None and vehicle_type != vt_hint:
                    # Pattern matched but vehicle type doesn't - skip this rule
                    continue
            # vt_hint is None (any type) OR vehicle types match
            return (main_class, sub_class)

    # Fallback based on vehicle_type alone
    vt_fallbacks = {
        "stock": ("equities", "US equity"),
        "ETF": ("equities", "US equity"),
        "bond": ("bonds", "corporate IG"),
        "MMF": ("cash", "money market"),
        "fund_LP": ("alternatives", "private equity"),
        "note": ("alternatives", "commodities"),  # Gold/commodities are usually "note" type
        "option": ("other", "options"),
        "crypto": ("alternatives", "crypto"),
    }

    if vehicle_type and vehicle_type in vt_fallbacks:
        return vt_fallbacks[vehicle_type]

    return None


def _ensure_database_ready(config: AppConfig) -> None:
    """Ensure the database exists and migrations are run."""
    db_path = config.database.path
    if not db_path.exists():
        run_migrations(config)


def _get_asset_class_id(conn, main_class: str, sub_class: str) -> int | None:
    """Look up asset_class_id from the database."""
    cursor = conn.execute(
        "SELECT id FROM asset_classes WHERE main_class = ? AND sub_class = ?",
        (main_class, sub_class),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def enrich_payload(
    payload: dict,
    *,
    document_path: Path | None = None,
    config: AppConfig | None = None,
    auto_classify: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Enrich and validate an asset payload.

    - Computes document_hash from document_path if provided
    - Auto-classifies instruments based on name/vehicle_type
    - Validates the payload structure

    Args:
        payload: Raw LLM-extracted JSON payload
        document_path: Optional path to original statement for hash computation
        config: App config for database access
        auto_classify: Whether to add classification metadata
        verbose: Whether to print classification details

    Returns:
        Enriched payload ready for import
    """
    effective_config = config or load_config()
    _ensure_database_ready(effective_config)

    # Compute document hash if path provided
    if document_path and document_path.exists():
        computed_hash = compute_file_sha256(document_path)
        doc_block = payload.setdefault("document", {})
        doc_block.setdefault("document_hash", computed_hash)
        doc_block.setdefault("file_path", str(document_path))

        # Apply hash to holding_values
        for value in payload.get("holding_values") or []:
            value.setdefault("document_hash", computed_hash)

        if verbose:
            click.echo(f"Computed document_hash: {computed_hash}")

    # Auto-classify instruments
    if auto_classify:
        classifications: dict[str, tuple[str, str]] = {}

        for inst in payload.get("instruments") or []:
            name = inst.get("name", "")
            symbol = inst.get("symbol", "")
            vehicle_type = inst.get("vehicle_type")

            classification = _classify_instrument(name, vehicle_type)
            if classification:
                main_class, sub_class = classification
                classifications[symbol] = classification

                # Store classification in instrument metadata for reference
                inst_metadata = inst.setdefault("metadata", {})
                inst_metadata["auto_class"] = {"main": main_class, "sub": sub_class}

                if verbose:
                    click.echo(f"Classified {symbol} ({name}): {main_class}/{sub_class}")
            else:
                if verbose:
                    click.echo(f"No classification for {symbol} ({name})")

        # Summary
        if verbose and classifications:
            click.echo(f"\nClassified {len(classifications)}/{len(payload.get('instruments', []))} instruments")

    return payload


def validate_and_report(payload: dict, *, strict: bool = True) -> list[str]:
    """
    Validate payload and return list of errors.

    Args:
        payload: The asset payload to validate
        strict: If True, raises on validation errors

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = validate_asset_payload(payload)

    if errors and strict:
        formatted = "\n - " + "\n - ".join(errors)
        raise click.ClickException(f"Payload validation failed:{formatted}")

    return errors


def detect_potential_transfers(
    payload: dict,
    *,
    config: AppConfig | None = None,
    verbose: bool = False,
) -> list[dict]:
    """
    Detect potential transfers by checking if any instruments in the payload
    already have active holdings at different accounts.

    This helps identify when assets have moved between custodians.

    Args:
        payload: The asset payload to check
        config: App config for database access
        verbose: Whether to print detection details

    Returns:
        List of potential transfers with suggested commands
    """
    effective_config = config or load_config()
    potential_transfers = []

    # Get unique (account_key, symbol) pairs from payload
    payload_holdings = {}
    for holding in payload.get("holdings") or []:
        account_key = holding.get("account_key")
        symbol = holding.get("symbol")
        if account_key and symbol:
            payload_holdings[(account_key, symbol)] = holding

    if not payload_holdings:
        return []

    with connect(effective_config, read_only=True) as conn:
        # For each symbol in the payload, check for existing active holdings
        # at different accounts
        symbols = set(h[1] for h in payload_holdings.keys())

        for symbol in symbols:
            # Get payload's account for this symbol
            payload_accounts = [
                ak for ak, sym in payload_holdings.keys() if sym == symbol
            ]

            # Find active holdings for this symbol in the database
            cursor = conn.execute(
                """
                SELECT
                    h.id as holding_id,
                    a.name as account_name,
                    i.name as instrument_name,
                    i.symbol
                FROM holdings h
                JOIN accounts a ON h.account_id = a.id
                JOIN instruments i ON h.instrument_id = i.id
                WHERE i.symbol = ? AND h.status = 'active'
                """,
                (symbol,),
            )
            existing = cursor.fetchall()

            for row in existing:
                existing_account = row["account_name"]
                # Check if this is a different account than what's in the payload
                if existing_account not in payload_accounts:
                    potential_transfers.append({
                        "symbol": symbol,
                        "instrument_name": row["instrument_name"],
                        "existing_account": existing_account,
                        "existing_holding_id": row["holding_id"],
                        "new_accounts": payload_accounts,
                    })

    return potential_transfers


def print_transfer_warnings(transfers: list[dict]) -> None:
    """Print warnings about potential transfers with suggested commands."""
    if not transfers:
        return

    click.echo()
    click.secho("⚠️  Potential transfers detected:", fg="yellow", bold=True)
    click.echo()

    for xfer in transfers:
        symbol = xfer["symbol"]
        name = xfer["instrument_name"]
        existing = xfer["existing_account"]
        new_accounts = xfer["new_accounts"]

        click.echo(f"  {symbol} ({name})")
        click.echo(f"    Currently active at: {existing}")
        click.echo(f"    Now appearing at: {', '.join(new_accounts)}")
        click.echo()

        # Suggest command for each new account
        for new_acct in new_accounts:
            click.echo(f"    Suggested command:")
            click.secho(
                f"      fin-edit --apply holdings-transfer --symbol {symbol} "
                f'--from "{existing}" --to "{new_acct}" --carry-cost-basis',
                fg="cyan",
            )
        click.echo()


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    required=False,
    help="LLM-extracted JSON file to process.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output path for enriched JSON.",
)
@click.option(
    "--document-path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Original statement file for hash computation.",
)
@click.option(
    "--workdir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Asset-tracker workspace root. Auto-discovers files when provided.",
)
@click.option(
    "--auto-classify/--no-auto-classify",
    default=True,
    show_default=True,
    help="Auto-classify instruments based on name/type.",
)
@click.option(
    "--detect-transfers/--no-detect-transfers",
    default=True,
    show_default=True,
    help="Check for potential transfers from other accounts.",
)
@click.option(
    "--validate-only",
    is_flag=True,
    help="Only validate, don't write output.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Print detailed classification information.",
)
def cli(
    *,
    input_path: Path | None,
    output: Path | None,
    document_path: Path | None,
    workdir: Path | None,
    auto_classify: bool,
    detect_transfers: bool,
    validate_only: bool,
    verbose: bool,
) -> None:
    """Validate and enrich LLM-extracted asset JSON."""

    # Resolve workspace
    if workdir is not None:
        workdir = workdir.expanduser().resolve()
        if not workdir.exists():
            raise click.ClickException(f"Workspace {workdir} does not exist.")

        # Auto-discover input (look for *-raw.json or *.json excluding enriched)
        if input_path is None:
            candidates = [
                p for p in workdir.glob("*.json")
                if not p.name.endswith("-enriched.json") and not p.name.endswith("-prompt.txt")
            ]
            if not candidates:
                raise click.ClickException(f"No JSON files found in {workdir}.")
            if len(candidates) > 1:
                # Prefer *-raw.json if available
                raw_candidates = [p for p in candidates if p.name.endswith("-raw.json")]
                if len(raw_candidates) == 1:
                    input_path = raw_candidates[0]
                else:
                    raise click.ClickException(
                        f"Multiple JSON files found. Specify --input explicitly."
                    )
            else:
                input_path = candidates[0]

        # Auto-derive output
        if output is None and not validate_only:
            base_name = input_path.stem.replace("-raw", "")
            output = workdir / f"{base_name}-enriched.json"

        # Look for document in workspace if not provided
        if document_path is None:
            doc_candidates = list(workdir.glob("*.pdf")) + list(workdir.glob("*-scrubbed.txt"))
            if len(doc_candidates) == 1:
                document_path = doc_candidates[0]

    if input_path is None:
        raise click.ClickException("Either --input or --workdir is required.")

    # Load payload
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON in {input_path}: {exc}") from exc

    if verbose:
        click.echo(f"Processing: {input_path}")
        click.echo(f"Instruments: {len(payload.get('instruments', []))}")
        click.echo(f"Holdings: {len(payload.get('holdings', []))}")
        click.echo(f"Values: {len(payload.get('holding_values', []))}")
        click.echo()

    # Enrich
    enriched = enrich_payload(
        payload,
        document_path=document_path,
        auto_classify=auto_classify,
        verbose=verbose,
    )

    # Validate
    errors = validate_and_report(enriched, strict=True)

    # Detect potential transfers
    if detect_transfers:
        transfers = detect_potential_transfers(enriched, verbose=verbose)
        print_transfer_warnings(transfers)

    if validate_only:
        click.echo("Payload is valid.")
        return

    # Write output
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(enriched, indent=2), encoding="utf-8")
        click.echo(f"Wrote enriched payload to {output}")
    else:
        click.echo(json.dumps(enriched, indent=2))


if __name__ == "__main__":
    cli()
