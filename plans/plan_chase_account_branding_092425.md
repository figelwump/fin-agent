# plan_chase_account_branding_092425

## Context & Notes
- Currently `ChaseExtractor` sets `StatementMetadata.account_name` to a generic "Chase Account".
- Many Chase statement PDFs (e.g., Amazon Prime Visa) include prominent product branding in the textual header.
- Goal: infer a more descriptive account name when safe, without exposing sensitive digits.

## Phase 1 — Branding Heuristics Design
- [x] Catalogue branding markers from the provided statement (and other known Chase card templates if available). — Statement text includes phrases like "Amazon Prime Visa", "www.chase.com/amazon", and "Prime Visa Points" suitable for matching.
- [x] Define a lightweight pattern → display-name mapping, ensuring case-insensitive matching and avoiding false positives. — Added `_ACCOUNT_NAME_PATTERNS` with regex-powered matching based on `_contains_keyword` for robustness against duplicated glyphs.
- [x] Decide fallbacks (e.g., retain "Chase Account" when no marker matches). — Helper `_infer_account_name` returns the friendly name when patterns match, otherwise defaults to "Chase Account".

## Phase 2 — Extraction Updates & Tests
- [x] Implement a helper in `chase.py` to derive account name from document text using the pattern mapping. — `_infer_account_name` now scans `_ACCOUNT_NAME_PATTERNS` using `_contains_keyword`.
- [x] Update metadata assignment inside `extract()` to use the helper. — `StatementMetadata.account_name` is sourced from `_infer_account_name(document.text)`.
- [x] Extend/adjust unit tests (e.g., `test_chase_extractor_extracts_transactions`) and add a new fixture covering the Amazon Prime Visa text. — Tests now assert metadata names and include Amazon-branded fixtures for both standard and duplicated glyph cases.

## Phase 3 — Validation & Documentation
- [x] Run targeted pytest suite (`tests/fin_extract/test_chase_extractor.py`) to ensure behaviour. — Suite passes with new metadata assertions.
- [x] Dry-run `fin-extract statements/20250717-statements-4537-.pdf --dry-run` to confirm the branded name is emitted. — Output now reports "Amazon Prime Visa" in the account line.
- [ ] Note the branding heuristic in relevant docs/specs if necessary (or leave as internal comment if change is limited to extractor).

## Open Questions
- Should we let users opt into including last-four digits later via config?
- Do we need to expose the detected branding in CLI logs for dry-run clarity?
