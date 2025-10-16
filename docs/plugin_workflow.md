# Plugin Workflow Guide

This guide describes how to author, validate, and install custom extractors for
`fin-extract`. It is written for both human developers and LLM-powered agents
that need deterministic instructions.

## Plugin Types

There are two supported plugin surfaces. You can mix both in a single
directory; the loader will pick them up automatically.

1. **Declarative specs** (`*.yaml`): Pure YAML configs interpreted by
   `DeclarativeExtractor`. Best for column-mapping problems and light-weight
   rule tweaks.
2. **Python extractors** (`*.py`): Classes inheriting from
   `StatementExtractor`. Use when custom parsing logic is unavoidable.

Both formats may coexist with the built-in extractors. At runtime, fin-extract
loads bundled specs, then user plugins located under the configured plugin
paths (defaults to `~/.finagent/extractors`).

## Directory Layout

User plugins live in one or more directories. The default path is
`~/.finagent/extractors`, but you can add more via
`extraction.plugin_paths` in `config.yaml` or with environment variables:

```yaml
extraction:
  enable_plugins: true
  plugin_paths:
    - ~/.finagent/extractors
    - ~/work/fin-plugins
```

At runtime you can narrow the set of active plugins:

- `fin-extract --no-plugins …` – disables discovery for this run
- `fin-extract --allow-plugin chase_yaml …` – only load specific names

Name comparisons are case-insensitive. Allow/deny lists are also available in
`config.yaml` (`plugin_allowlist`, `plugin_blocklist`).

## Declarative Spec Skeleton

Start from the bundled examples (`fin_cli/fin_extract/bundled_specs/`). The
loader expects the structure defined in
`docs/declarative_extractor_schema.md`. A minimal spec should include:

```yaml
name: example_bank
institution: Example Bank
account_type: checking

columns:
  date:
    aliases: ["date"]
  description:
    aliases: ["description"]
  amount:
    aliases: ["amount"]

dates:
  formats: ["%m/%d/%Y"]

sign_classification:
  method: "keywords"
  charge_keywords: []
  credit_keywords: []
  transfer_keywords: []
  interest_keywords: []
  card_payment_keywords: []

detection:
  keywords_all: ["example bank"]
  table_required: true
  header_requires: ["date", "description", "amount"]
```

Save this as `~/.finagent/extractors/example_bank.yaml`. Run

```bash
fin-extract dev validate-spec ~/.finagent/extractors/example_bank.yaml
```

for structural validation. The command loads the spec and reports missing
sections, detection hints, and potential name collisions.

## Python Extractor Skeleton

Python plugins must define a `StatementExtractor` subclass with unique `name`.
When possible, reuse helpers from `fin_cli.fin_extract.utils`.

```python
from __future__ import annotations

from fin_cli.fin_extract.extractors.base import StatementExtractor
from fin_cli.fin_extract.parsers.pdf_loader import PdfDocument
from fin_cli.fin_extract.types import ExtractionResult, StatementMetadata


class ExampleBankExtractor(StatementExtractor):
    name = "example_bank_py"

    def supports(self, document: PdfDocument) -> bool:
        return "example bank" in document.text.lower()

    def extract(self, document: PdfDocument) -> ExtractionResult:
        # TODO: replace with real parsing logic
        metadata = StatementMetadata(
            institution="Example Bank",
            account_name="Example Account",
            account_type="checking",
            start_date=None,
            end_date=None,
        )
        return ExtractionResult(metadata=metadata, transactions=[])
```

Place the file at `~/.finagent/extractors/example_bank.py`. Use

```bash
fin-extract dev list-plugins
```

to confirm the loader sees the new extractor. The output lists each extractor
with its origin (`user yaml`, `user python`, `bundled yaml`, `built-in python`).

## Testing Your Plugin

1. **Dry run** – always start with `--dry-run` to verify detection and metadata:

   ```bash
   fin-extract statement.pdf --dry-run --allow-plugin example_bank
   ```

2. **CSV inspection** – write output to a temp directory and inspect the rows:

   ```bash
   fin-extract statement.pdf --output tmp/example.csv --allow-plugin example_bank
   ```

3. **Automated tests** – create fixtures under `tests/` that import your plugin
   from disk. Use `CliRunner` to simulate CLI runs, mirroring
   `tests/fin_extract/test_dev_commands.py`.

## LLM Authoring Tips

- Use deterministic placeholders and TODO comments to highlight sections that
  require human validation.
- Prefer declarative specs when the PDF tables are regular; fall back to Python
  only when necessary.
- When inferring detection keywords, read the PDF text and choose stable
  phrases (e.g., statements headers, institution names).
- Keep extractor names lowercase with underscores (`example_bank`) to align
  with existing conventions.
- After generating a spec, immediately run
  `fin-extract dev validate-spec` to capture schema errors before shipping the
  file.

## Troubleshooting

- `Plugin discovery disabled` – either `--no-plugins` was passed or
  `enable_plugins` is `false` in config.
- `not in allowed plugin list` – adjust `--allow-plugin` arguments or remove
  entries from the allowlist.
- `blocked by configuration` – remove the extractor name from `plugin_blocklist`.
- Import errors from Python plugins are logged; use the stack trace printed in
  `fin-extract dev list-plugins` output to debug.

## Next Steps

- Review the full declarative schema reference for advanced features such as
  multi-line handling, merchant cleanup, and statement period parsing.
- Consider contributing reusable specs back into the bundled collection in
  `fin_cli/fin_extract/bundled_specs/` once validated.
