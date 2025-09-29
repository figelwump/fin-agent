# plan_extractor_refactor_092825

- [x] **Phase 1 – Identify Shared Patterns**
  - [x] Catalogue overlapping logic across existing extractors (BofA, Mercury, Chase) around table normalization, header detection, amount parsing, and transaction filtering.
    - Notes (2025-09-28):
      - BofA & Mercury both rebuild headers by merging multi-line rows, clean cells, and then iterate through table rows with continuation handling; Chase performs simpler column matching but could reuse the same normalization helpers.
      - Amount parsing exists in three flavors (`_parse_amount` in Chase, BofA, Mercury) differing only in symbol cleanup and negative detection—prime candidate for a shared utility.
      - Filtering decisions (credits vs. spend, transfers, interest) appear in each extractor with keyword sets; logic structure is similar enough to centralize while leaving extractor-specific keyword dictionaries.
      - Shared need for keyword normalization (`_normalize_token`) and pattern caching already duplicated across extractors.
  - [x] Note extractor-specific quirks that must remain bespoke so shared utilities stay flexible.
    - Notes (2025-09-28):
      - Chase relies on text-mode fallback parsing for glyph-doubled statements—should keep bespoke logic there, with shared utilities only for table paths.
      - BofA statements require statement-period parsing and year inference tied to summary text; Mercury uses savings vs. checking heuristics and positive-only output, so shared helpers must accept hooks/overrides.

- [x] **Phase 2 – Design Shared Utilities**
  - [x] Sketch API for a reusable table-normalization helper (multi-line headers, row cleaning).
    - Proposal (2025-09-28): create `fin_extract/utils/table.py` with `build_normalized_table(raw_rows, header_scan=6)` returning `(headers, data_rows)`; includes `merge_rows`, `_normalize_cell`, and optional `header_predicate` callback so extractors can override detection.
  - [x] Outline common amount/sign parsing helpers and keyword-based filters (transfers, interest, credits).
    - Proposal: `fin_extract/utils/amounts.py` exporting `parse_amount(value: str)` + `class SignClassifier` that accepts keyword sets (`credits`, `debits`, `transfers`, `interest`, `card_payments`) and returns signed float or `None` for filtered entries.
    - Provide default keyword sets plus extension hooks per extractor (e.g., Chase extends with `_SECTION_HEADER_DESCRIPTIONS`).
  - [x] Plan integration points so each extractor opts in without breaking current behavior.
    - Plan: Refactor BofA & Mercury first (they already share patterns) using new helpers; Chase adopts amount parsing + optional table helper but keeps text fallback separate.
    - Introduce `ExtractorContext` helper allowing per-extractor overrides (e.g., convert positive spending vs. negative credits) and keep filters configurable to avoid breaking current expectations.

- [x] **Phase 3 – Implement Shared Modules**
  - [x] Add new helpers under `fin_extract/utils.py` (or similar) with unit coverage.
    - Notes (2025-09-28): introduced `fin_extract/utils/table.py` and `fin_extract/utils/amounts.py` with `normalize_pdf_table`, `parse_amount`, and `SignClassifier`; utility behaviour exercised via updated extractor tests.
  - [x] Update extractors incrementally to use the shared helpers while preserving bank-specific overrides.
    - Notes: Bank of America and Mercury now consume the shared helpers; Chase left untouched for fallback text parsing but can adopt `parse_amount` later.
  - [x] Ensure Mercury and BofA filters leverage shared keyword sets without regressing existing tests.
    - Notes: unified keyword-driven filters drop transfers, interest, and credit-card payments; regression suite confirms BofA/Mercury expectations.

- [x] **Phase 4 – Regression Validation**
  - [x] Run `pytest tests/fin_extract` plus targeted CLI dry-runs on sample statements (Chase, BofA, Mercury).
    - Notes (2025-09-28): `pytest tests/fin_extract tests/fin_export/test_cli.py` passes; `fin-extract` on real BofA credit and Mercury savings PDFs succeed with clean output.
  - [x] Capture follow-up notes (future extractor targets, remaining bespoke logic) in this plan.
    - Notes: Chase still relies on bespoke text fallback; future work may adopt shared normalization for table paths and expose configurable keyword sets via config.
    - Notes update (2025-09-28, PM): Added text fallback for BofA checking statements to capture debit lines when tables are deposit-only; ensured transfer ACHs (e.g., MercuryACH) are filtered while legitimate card charges remain.
