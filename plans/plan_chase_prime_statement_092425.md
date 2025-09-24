# plan_chase_prime_statement_092425

## Context & Notes
- `fin-extract` currently auto-detects Chase statements by searching for the literal string "chase" or familiar table headers. The Amazon Prime Visa statement in `statements/20250717-statements-4537-.pdf` renders text with duplicated characters (e.g., `CChhaassee`), so the detector misses it and exits with "Unsupported statement format".
- Table extraction via `pdfplumber` does not yield the transaction table for this statement; extraction must rely on the text-mode fallback already present in `ChaseExtractor._extract_from_text`.
- Goal: Enhance the Chase extractor to recognize this variant and verify that transactions, including charge/credit polarity, are parsed correctly.

## Phase 1 — Format Analysis & Normalization Strategy
- [x] Inspect the problematic PDF to document recurring text quirks (duplicated characters, section headings, layout). — Confirmed Chase Amazon Prime PDF doubles alphabetic glyphs and lacks extractable tables, but plaintext section headers remain intact.
- [x] Design a normalization helper that collapses duplicated alphabetic characters without corrupting numeric data (needed for detection only). — Implemented `_contains_keyword` regex helper to tolerate duplicated glyphs while leaving numeric substrings untouched.
- [x] Identify any additional section headers (e.g., `PURCHASE`) or layout markers that should be considered during text parsing. — Verified existing `PURCHASE`/`PAYMENTS AND OTHER CREDITS` sections suffice for the Amazon Prime variant.

## Phase 2 — Detection & Extraction Updates
- [x] Update `ChaseExtractor.supports` to use the normalization helper when scanning text for Chase identifiers ("chase", "amazon", "account activity", etc.). — Detection now delegates to `_contains_keyword`, covering duplicated glyphs in keywords like "Chase" and "account activity".
- [x] Expose the normalization helper for reuse inside `_extract_from_text` if section matching needs it; ensure no regression for already-supported PDFs. — Section transitions now call `_contains_keyword`, preserving the prior behaviour while handling duplicated text lines.
- [x] Add guardrails/tests around normalization to confirm it transforms duplicated-letter samples while leaving regular text untouched. — Added unit coverage for `_contains_keyword` and a duplicated-glyph document fixture.

## Phase 3 — Verification & Regression Safety
- [x] Run `fin-extract` on the failing PDF to confirm successful detection and transaction count output in dry-run mode. — `fin-extract` now detects the Chase format and reports 11 transactions for `statements/20250717-statements-4537-.pdf`.
- [x] Execute existing unit/integration tests (or targeted subset) to ensure no regressions. — `pytest tests/fin_extract/test_chase_extractor.py` passes locally.
- [x] Document the fix rationale and empirical results (transaction count, detection string) in this plan and/or commit message notes. — Plan updated with detection helper details and dry-run metrics for future reference.

## Open Questions
- Does any other bank format exhibit similar duplicated glyphs that might benefit from the same normalization utility?
- Should we cache normalized text on `PdfDocument` to avoid recomputing during multi-stage parsing?
