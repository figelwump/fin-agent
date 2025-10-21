Branch: main
Plan: plans/plan_fin_extract_docling_and_custom_extractors_100425.md
Last Updated: 2025-10-07

## Status

Phase 2 complete. Declarative extractor runtime implemented with Chase YAML spec validated against Python extractor (perfect parity).

## What's Done

- ✅ Full declarative runtime (`fin_cli/fin_extract/declarative.py`)
- ✅ Schema documentation (`docs/declarative_extractor_schema.md`)
- ✅ CLI `--spec` flag integration
- ✅ Chase spec (`~/.finagent/extractors/chase.yaml`)
- ✅ Validation: identical output to Python extractor

## Next Steps

Phase 3: Port BofA and Mercury to declarative specs
