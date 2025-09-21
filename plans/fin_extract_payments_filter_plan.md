# Plan — Filter "PAYMENTS AND OTHER CREDITS" Rows in fin-extract

## Context & Notes
- Scope limited to Chase extractor under `fin_cli/fin_extract/extractors/chase.py`.
- Goal: avoid emitting transactions whose description is the section label "PAYMENTS AND OTHER CREDITS" from PDF tables.
- Text-only parsing path already ignores section headers because they lack MM/DD prefix; confirm behaviour but expect no changes.

## Phase 1 — Understand Current Behaviour
- [x] Inspect table-driven parsing in `fin_cli/fin_extract/extractors/chase.py` to identify where headers could leak into transactions.
  - Notes: Table rows parsed via `_parse_row`; header descriptions can slip through before guard logic.
- [x] Review text-based fallback path to ensure no similar issue.
  - Notes: Text-only parsing relies on MM/DD lines, so section headers without dates are already ignored.

## Phase 2 — Implement Filtering Logic
- [x] Add guard in table parsing to skip rows with description matching "PAYMENTS AND OTHER CREDITS" (case-insensitive, trimmed).
  - Notes: Early return now prevents conversion into `ExtractedTransaction` when the description matches the section header.
- [x] Ensure guard applies before transaction creation to avoid downstream handling.
  - Notes: Guard executes right after trimming description so no transaction object is built.
- [x] Consider central post-filter if additional contexts appear; document decision in notes.
  - Notes: Added text-parser guard instead; broader filter deferred until new headers are confirmed.

## Phase 3 — Tests & Verification
- [x] Extend Chase extractor tests to include a table row containing the section label and assert it is ignored.
  - Notes: `_build_document` now seeds a synthetic header row with amount `0.00`.
- [x] Run relevant test suite (likely `pytest tests/fin_extract/test_chase_extractor.py`).
  - Notes: `pytest tests/fin_extract/test_chase_extractor.py` passes on 2025-09-20.
- [x] Update plan notes with outcomes and any follow-up considerations.
  - Notes: Plan annotated with guard decisions, skipped headers list, and test command outcomes.

## Follow-Up Ideas
- If future statements include other section headers (e.g., "FEES"), consider generalizing with a shared header-block list.
## Phase 4 — Skip Payment/Credit Transactions
- [x] Determine reliable indicators (table type, text section) for identifying credit entries.
  - Notes: Table rows expose transaction type (e.g., "Payment"), and text parsing tracks the current section via headings.
- [x] Update table parsing to drop rows when type indicates payment/credit (and note fallback for missing type).
  - Notes: `_is_credit_entry` now screens rows before sign handling, also covering description prefixes when type is missing.
- [x] Update text parsing to skip transactions while inside the credit section.
  - Notes: Parser now early-continues when `current_section == "credit"` and reuses `_is_credit_entry` for safety.
- [x] Extend tests to assert payments are excluded in both table and text flows.
  - Notes: Updated fixtures confirm only purchase rows remain across table and text scenarios.
- [x] Run targeted pytest suite and capture outcome.
  - Notes: `pytest tests/fin_extract/test_chase_extractor.py` passes on 2025-09-20 after credit filters.

