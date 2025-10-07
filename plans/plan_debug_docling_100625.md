
# plan_debug_docling_100625

## Phase 1 – Reproduce & Inspect Current Docling Output
- [x] Activate `.venv-py312` virtualenv and run `debug_docling.py` to capture current table structures. *(2025-10-06: reproduced zero-transaction issue; saw docling tables with numeric headers like `('0','1','2')` and ledger rows starting at index 4–5.)*
- [x] Inspect `fin_cli/fin_extract/parsers/docling_loader.py` and `fin_cli/fin_extract/extractors/chase.py` to understand header detection flow and mapping requirements. *(Reviewed header predicate expectations and existing `_headers_look_like_data` guard.)*

## Phase 2 – Adjust Docling Loader Normalization
- [x] Update Docling loader to preserve or synthesize semantic headers when Docling outputs data-like column names (e.g., `0,1,2`). *(2025-10-06: `fin_cli/fin_extract/parsers/docling_loader.py` now infers `Transaction Date`/`Description`/`Amount` headers from ledger-like rows.)*
- [x] Add inline comments explaining the fallback header logic for future maintainers/LLMs. *(Comment documents why the synthesized headers exist and how they protect extractors.)*

## Phase 3 – Verify Extraction End-to-End
- [x] Rerun `debug_docling.py` and ensure transactions are extracted from the docling engine. *(Now reports 41 transactions for the Chase sample; dates resolve across the year boundary.)*
- [x] If practical, run `fin-extract statements/chase-credit-20240106-statements-6033-.pdf --stdout --engine docling` to confirm CLI path uses the fixed logic. *(CLI outputs the expected CSV rows with Chase metadata.)*
- [x] Run the same verification on one of the new BofA statements in `statements/` to confirm the heuristics are issuer-agnostic. *(BofA October 23, 2024 statement yields 6 transactions after decoding `/uniXXXX` glyphs.)*
- [x] Document the plan updates with notes on changes and outcomes.

### Notes
- Chase (and similar) extractors expect headers containing terms like `date`, `description`, `amount`; fallback headers should align with that expectation.
- Keep numeric header override limited to transaction-like tables to avoid impacting non-ledger tables.
- Ensure we keep the original first data row when synthesizing headers so data is not lost.
- Add docstring/comments clarifying why docling fallback is needed when headers look like ordinals.
- `_DATE_NO_YEAR_RE` logic in `fin_cli/fin_extract/extractors/chase.py` now infers the year using statement context so Docling tables without year suffixes map to real dates.
- `_clean_docling_text` decodes `/uniXXXX` sequences so all extractors see normalized text across issuers.
