## plan_fin_extract_docling_and_custom_extractors_100425

Goal: Evaluate and (optionally) integrate Docling for PDF parsing to minimize custom parsing surface area, and add an agent-driven “learn a new bank extractor” workflow that writes user-local plugins under `~/.finagent/extractors` and iterates until results pass validation.

### Context Snapshot (as of 2025-10-04)
- Current extractor stack: `pdfplumber` primary + optional `camelot` fallback (see `fin_cli/fin_extract/parsers/pdf_loader.py`).
- Extractors implement `StatementExtractor` with `supports()` and `extract()` (see `fin_cli/fin_extract/extractors/*`, `base.py`).
- Registry is static + programmatic `register_extractor()`; no user plugin discovery yet (see `fin_cli/fin_extract/extractors/__init__.py`).
- CLI: `fin-extract <pdf> [--stdout|--output]` plus config for supported banks and camelot fallback.

Key hypothesis: Using Docling for table + text extraction reduces per-bank parsing complexity; most custom logic then becomes bank-specific column mapping, date/amount normalization, and sign classification—shrinking the surface area of bespoke code.

### Decisions (confirmed 2025-10-04)
- Default engine: Docling-first (`engine: auto` tries Docling before pdfplumber/camelot).
- Plugin root: `~/.finagent/extractors` (approved).
- Approach: Declarative-first for new/ported extractors; fall back to Python when needed.
- Priority: Port existing banks with Docling + declarative specs in this order: Chase → BofA → Mercury.

---

## Current Status (2025-10-09)

**Phase 1: Complete with findings**
- ✅ Docling adapter infrastructure complete
- ✅ Engine selection and CLI integration complete
- ✅ Fallback logic verified with pdfplumber
- ✅ PyTorch + Docling installed (Python 3.12 venv)
- ✅ Tested Docling on Chase + BofA PDFs with normalized headers

**Test Results:**
- **Performance:** Docling ~45–50s per Chase PDF vs pdfplumber ~instant (ML pipeline cost)
- **Accuracy:** Docling now extracts 41/41 Chase transactions and 6/6 BofA transactions (parity with pdfplumber)
- **Key fixes:** Adapter synthesizes ledger headers, decodes `/uniXXXX` glyphs, and Chase extractor infers statement-year context for `MM/DD` dates
- **Trade-off:** Docling remains heavy but becomes a reliable fallback when pdfplumber misreads layout

**Phase 3 validation snapshot (2025-10-10):**
- BofA declarative spec vs. Python extractor  
  - `eStmt_2025-09-22.pdf`: Python 117 rows, spec 116 (missing line is a `TARGET` refund; exclusion is correct, but double-check there aren’t other gaps).  
  - `eStmt_2025-08-22.pdf`: Python 99 rows, spec 98 (same refund pattern).  
  - Action: confirm parity after account-type inference fix (now outputs `Bank of America Credit Card` instead of checking); no changes needed for refund filtering.
- Mercury declarative spec (`vishal-kapur-and-sneha-kapur-2550-monthly-statement-2025-09.pdf`):  
  - Declarative runtime now shares the single-column expansion fallback; spec matches Python output on April–September 2025 statements (4 spend-only rows per PDF).  
  - Action: add automated parity coverage so future Docling/Camelot changes don’t regress the fallback.

**Findings:**
- Docling tables differ from pdfplumber, but normalized headers now align with extractor expectations
- Normalization retains the first data row so downstream extractors remain unchanged
- Unicode glyph decoding is mandatory for BofA statements (`Date/uni002F...` → `Date`)
- Chase extractor needs context-derived year hints when Docling emits `MM/DD`

**Decision Point:**
1. **Option A:** Keep Docling enabled in `auto` mode now that accuracy matches pdfplumber (recommended)
2. **Option B:** Use pdfplumber-first for performance-sensitive runs and fall back to Docling as needed
3. **Option C:** N/A — earlier blockers resolved by adapter/extractor updates

**Branch:** `feature/docling-integration` (merged to main)

---

**Phase 2: Complete**
- ✅ Declarative runtime implemented (`fin_cli/fin_extract/declarative.py`)
- ✅ Full YAML schema documented (`docs/declarative_extractor_schema.md`)
- ✅ CLI integration via `--spec` flag on `fin-extract`
- ✅ Chase declarative spec created (`~/.finagent/extractors/chase.yaml`)
- ✅ Validated perfect parity with Python Chase extractor

**Key Implementation Details:**
- Full-featured runtime supporting column mapping, date parsing with year inference, sign classification, filtering, multi-line handling
- Year boundary logic correctly handles Dec→Jan transitions by extracting both month and year from statement text
- Tested on chase-credit-20240106 statement: identical output to Python extractor (41 transactions)

---

**Phase 3: In Progress**
- ✅ BofA and Mercury YAML specs created
- [ ] Testing BofA declarative spec across sample PDFs  
  - 2025-09 + 2025-08 statements each drop a single row: the `TARGET.COM BROOKLYN PARKMN` line is a refund (credit) and should stay excluded.  
  - 2025-10-09 PM: Updated Python + declarative account-name inference to emit `Bank of America Credit Card` (previously mis-labeled as checking when autopay text mentioned the funding account).
- [x] Mercury declarative validation  
  - Sample statements for 2025-04 through 2025-09 live under `statements/mercury/`.  
  - Declarative spec now uses the shared fallback and matches the Python extractor across the current dataset; still need automated regression coverage.
- [ ] Parity validation vs Python extractors pending (blocked by the two issues above).

**Next:** Fix declarative negative-charge handling, add Mercury row segmentation/text fallback, then rerun parity tests before moving to Phase 4 (User Plugin System).

---

## Phases & Tasks

### Phase 1 — Docling Adapter, Default Engine, Chase First
- [x] Add optional Docling dependency (exact package/pin to confirm) under a new extras group (e.g., `[pdf_docling]`).
  - Added `pdf_docling = ["docling>=2.55.1"]` to pyproject.toml
- [x] Implement adapter `fin_cli/fin_extract/parsers/docling_loader.py` returning our `PdfDocument`/`PdfTable` types.
  - Created `docling_loader.py` with `load_pdf_with_docling()` that converts Docling tables to PdfTable format
  - Uses `DocumentConverter().convert()` and `table.export_to_dataframe()`
- [x] Extend config with `extraction.engine: auto|docling|pdfplumber` (default `auto` → Docling-first) and `extraction.fallbacks`.
  - Added `engine` field to ExtractionSettings
  - Default is "auto" which tries Docling first, falls back to pdfplumber
  - Added env override: FINCLI_EXTRACTION_ENGINE
- [x] Update CLI (`fin-extract`) to honor `--engine` and log which engine succeeded.
  - Added `--engine` flag with choices: auto, docling, pdfplumber
  - Added logging to show engine selection and fallback behavior
  - Created `load_pdf_document_with_engine()` function with fallback logic
- [x] Create a small benchmark harness over `statements/` to measure tables found, transactions parsed, error cases, runtime.
  - **COMPLETED:** `debug_docling.py` compares Docling vs pdfplumber; post-fix runs confirm parity
- [x] Port Chase extractor for Docling output (adjust header predicates if needed). Validate parity with current output.
  - **COMPLETED:** Chase extractor now infers year for Docling `MM/DD` rows; extracts 41 transactions
- [ ] Document Mac/Linux prerequisites for Docling/OCR and graceful fallbacks.
  - TODO: Capture install notes (PyTorch, docling extras) in README/docs
- [x] Validate Docling against non-Chase issuer (BofA) to confirm heuristics are issuer-agnostic.
  - **COMPLETED:** BofA Oct 2024 statement parses 6 transactions after glyph decoding



Notes
- Adapter will normalize Docling tables to our `PdfTable(headers, rows)` with conservative header detection so extractors remain unchanged.
- If Docling is unavailable or fails, we fall back to `pdfplumber` then optional `camelot`.

Acceptance
- [x] On Chase samples, Docling path extracts ≥ current approach with ≤ error rate.
  - **RESULT:** 41/41 transactions captured with correct signs/dates after adapter + extractor fixes
  - **FOLLOW-UP:** Document performance expectations (~50s runtime) in docs
- [x] Engine default `auto` behaves deterministically and falls back cleanly when Docling fails.
  - **VERIFIED:** Docling-first succeeds; on forced failure it falls back to pdfplumber with clear logging
  - **NOTE:** Leave `auto` as default but mention performance trade-off in README

---

### Phase 2 — Declarative Runtime + Chase Spec (Declarative-first) ✅ COMPLETE
- [x] Introduce `fin_cli/fin_extract/declarative.py` to support a YAML/JSON spec that maps headers, date formats, and sign rules.
  - Created full declarative runtime with data classes matching schema
  - Supports all features: column mapping, date parsing, sign classification, filtering, multi-line handling
- [x] Author `~/.finagent/extractors/chase.yaml` implementing Chase via the declarative path.
  - Created chase.yaml with full feature parity to Python extractor
- [x] Provide `fin-extract dev:validate-spec` to validate a spec against sample PDFs.
  - Implemented as `--spec` flag on main `fin-extract` command (simpler than separate command)
- [x] Compare `chase.yaml` output vs. Python extractor; ensure parity or better. Keep Python as fallback.
  - Validated against Chase statement: identical output achieved
  - Fixed year boundary inference bug to handle Dec→Jan transitions correctly

Notes
- Keep `PdfDocument` naming for now; extractors remain engine-agnostic.
- Prefer declarative for maintainability and agent authoring.
- Schema documented at `docs/declarative_extractor_schema.md`
- Fixed year inference: now extracts both month and year from statement text for accurate year boundary handling

Acceptance
- [x] `chase.yaml` passes the spec validator and produces identical CSV rows to the Python extractor on samples.
  - Validated on chase-credit-20240106: perfect parity with Python extractor
- [x] Validator confirms spend-only output (no credits/payments/transfers included).
  - Sign classification working correctly; only spend transactions included

---

### Phase 3 — Port BofA and Mercury to Declarative
- [x] Create `bofa.yaml` and `mercury.yaml` specs under `~/.finagent/extractors` with header aliases, date formats, and sign rules.
  - Created bofa.yaml with dual-column support, account name inference, extensive row filtering (Oct 7, 15:35)
  - Created mercury.yaml with money in/out columns, account number inference (Oct 7, 15:35)
- [ ] Test BofA extractor against available statements (3 BofA PDFs in statements/)
  - 2025-10-09: `eStmt_2025-09-22.pdf` → Python 117 rows vs spec 116; `eStmt_2025-08-22.pdf` → Python 99 vs spec 98. The missing row is a refund and should remain filtered; ensure no other gaps exist.
- [x] Obtain Mercury sample PDFs for testing
  - 2025-10-09: `statements/mercury/` now contains April–September 2025 statements for validation.
- [ ] Test Mercury extractor once sample PDFs are available
  - 2025-10-10: Declarative runtime now shares the blob-expansion fallback; both Python and declarative paths return 4 spend transactions on the 2025-09 statement. Need to extend validation to other months + ensure spec-level tests cover the fallback logic.
- [ ] Extend validator to cover BofA/Mercury-specific heuristics (e.g., summary row suppression, period inference).
- [ ] Validate parity vs. current Python extractors; retain Python as fallback until confidence is high.
  - Blocked until Mercury row segmentation issues are resolved.
  - Also need to ensure BofA declarative spec (and Python inference) emit `account_type: credit` for these card statements; current heuristics see the word “checking” in autopay text and mislabel the account.

**Current Status (2025-10-09):**
- BofA + Mercury specs authored; validation now underway with findings above
- Mercury samples available locally (2025-04…2025-09)
- Declarative runtime requires negative-debit handling fix + blob-row splitting before parity testing can pass
- No automated harness yet for these issuers

Acceptance
- [ ] Declarative specs for BofA and Mercury match or exceed current extraction quality on provided samples.
- [ ] Validator confirms spend-only output (no credits/payments/transfers included).

---

### Phase 4 — User Plugin System for Custom Extractors
- [ ] Define plugin search path: `~/.finagent/extractors/**/*.py` and optional `~/.finagent/extractors/**/*.yaml` (for declarative specs).
- [ ] Implement `fin_cli/fin_extract/plugins/loader.py` that:
  - discovers modules/specs under the user dir
  - imports safely (module namespace `fin_user_plugins.<hash>`) and finds subclasses of `StatementExtractor`
  - registers them via `register_extractor()` at startup
- [ ] Add config: `extraction.plugin_paths` (defaults to the path above). Env override supported.
- [ ] Ensure registry includes built-ins + user plugins; built-ins win on name collisions unless user explicitly allows override via config.

Security/Isolation Notes
- Code executes locally; we’ll surface warnings and require explicit user opt-in the first time plugins are discovered.
- Add `--no-plugins` CLI switch to disable loading for a run; add allowlist by extractor name.

Acceptance
- [ ] Dropping a new `capitalone.yaml` or `capitalone.py` in `~/.finagent/extractors` makes it available without editing package code.

---

### Phase 5 — “Learn This Bank” Agent Workflow
- [ ] Detection: when `detect_extractor()` raises `UnsupportedFormatError`, capture PDF path and prompt the user: “Learn extractor for <detected guess or ‘unknown’>?”
- [ ] Scaffolder: `fin-extract dev:scaffold-extractor --name capitalone --from <pdf>` generates:
  - Python template `~/.finagent/extractors/capitalone.py` (implements `supports()` + `extract()`), heavily commented for LLMs.
  - Optional `capitalone.yaml` spec if the declarative path seems viable.
- [ ] Test harness: `fin-extract dev:test-extractor --name capitalone --pdf <path>` runs extraction and validates against schema + heuristics (non-zero txns, plausible dates, amounts parse, few rejected rows, optional balance reconciliation if detectable).
- [ ] Iteration loop: expose a simple JSON “diagnostics” report the agent can read to refine code/spec and re-run until thresholds pass.
- [ ] On first success, persist a tiny `metadata.json` with sample hashes and version for reproducibility.

Validation Rules (initial set)
- required columns present: date, merchant, amount, original_description
- amounts numeric; dates contiguous within statement period if detected
- spend-only: exclude credits, payments, and transfers (validator re-classifies all rows and fails if any would be credit/payment/transfer)
- optional: sum(purchases) ≈ statement subtotals if recoverable

Acceptance
- [ ] From an unsupported PDF, the guided flow produces a working declarative spec first; falls back to Python only if needed.

---

### Phase 6 — CLI UX, Docs, and E2E Tests
- [ ] CLI: add `--engine`, `--no-plugins`, `--allow <names>`, `dev:*` commands noted above.
- [ ] README + docs: engine selection, plugin directory, safety considerations, learn flow walkthrough.
- [ ] Tests: unit tests for plugin loader, docling adapter, declarative extractor, and the validation harness (use synthetic PDFs or fixtures).

Acceptance
- [ ] CI passes; smoke-test across `statements/` succeeds with `--engine auto`.

---

## Architecture Notes

### Engine Abstraction
- Keep `PdfDocument(text: str, tables: list[PdfTable])` as the stable interface for extractors.
- Implement `docling_loader.load_document()` that fills the same dataclasses. If Docling provides structural spans (e.g., multi-line cell joins), normalize them in the adapter.
- Selection policy:
  1. If `engine==docling`, try Docling; on failure optionally fall back (controlled by `extraction.fallbacks: [pdfplumber, camelot]`).
  2. If `engine==pdfplumber`, use current path with optional camelot.
  3. If `engine==auto`, try Docling → pdfplumber → camelot.

### Declarative Extractors
- Minimal YAML schema example:
  ```yaml
  name: capitalone
  account_type: credit
  headers:
    date: ["transaction date", "date", "post date"]
    description: ["description", "merchant name"]
    amount: ["amount", "transaction amount"]
    debit: ["withdrawals", "debits", "charges"]
    credit: ["deposits", "credits", "payments"]
  date_formats: ["%m/%d/%Y", "%m/%d/%y"]
  sign_rules:
    charge_keywords: ["purchase", "sale", "debit"]
    credit_keywords: ["payment", "refund", "credit"]
  drop_rows_if_description_matches:
    - "^continued on next page$"
  ```
- A small runtime translates the spec into the same flow used by our Python extractors.

### Plugin Loader
- Discovers `.py` files, imports in isolated module namespaces, finds subclasses of `StatementExtractor`, and registers them.
- Also supports `.yaml` specs by wrapping them with a generic `DeclarativeExtractor` at load time.
- Respects config `extraction.supported_banks` as an allowlist.

### Agent Loop I/O
- Emits a machine-readable JSON diagnostics file for each test run:
  ```json
  {
    "version": "1.0",
    "pdf": "/path/to.pdf",
    "extractor": "capitalone",
    "transactions": 142,
    "rejected_rows": 3,
    "issues": [
      {"type": "date_parse_error", "count": 2, "examples": ["13/32/2024", "--"]},
      {"type": "missing_amount", "count": 1}
    ]
  }
  ```
- The agent edits the plugin/spec and re-runs `dev:test-extractor` until thresholds pass.

---

## Decisions & Tradeoffs
- Docling adds dependencies and may slow first-run due to OCR; we keep it optional and behind `engine:auto` with fallback + explicit disable switches.
- Declarative specs accelerate long-tail support and are safer for agent-authoring than arbitrary Python.
- For complex banks, Python plugins remain available; templates include guardrails and heavy docstrings for LLMs.
- User privacy: learning occurs locally; no statement content leaves the machine. We will not auto-upload samples.

---

## Open Questions for Review
1. Also support a project-local `.finagent/extractors` alongside the home directory?
2. Minimum viable validation thresholds (e.g., require ≥10 transactions?) and whether to expose them as CLI flags.
3. Any additional Chase/BofA/Mercury PDFs you want included for parity testing?
4. Should we tighten BofA `supports()` heuristics (or registry ordering) so Mercury statements with "Bank of America" ACH rows don’t get misclassified?

---

## Impacted Files (planned)
- `pyproject.toml`: new extra(s) for Docling; possibly new scripts for dev commands.
- `fin_cli/shared/config.py`: add `engine`, `plugin_paths`, optional fallback policy flags.
- `fin_cli/fin_extract/parsers/docling_loader.py`: new adapter.
- `fin_cli/fin_extract/plugins/loader.py`: user plugin discovery + registration.
- `fin_cli/fin_extract/main.py`: engine selection, fallbacks, new `--engine/--no-plugins` flags.
- `fin_cli/fin_extract/declarative.py`: spec schema + runtime.
- `tests/`: unit tests for adapter, loader, and declarative runtime.
- `README.md` + docs: usage, prerequisites, learn workflow.

---

## Rollout Plan
- Ship behind config flags; keep default behavior unchanged in first PR.
- Provide “try it now” instructions for Docling engine and plugin loading.
- Iterate on banks where Docling clearly improves table detection.

---

## Review Checklist
- [ ] Scope and phases look right
- [ ] Defaults and safety switches acceptable
- [ ] Plugin directory/location approved
- [ ] Validation/acceptance criteria sufficient
- [ ] Open questions resolved

---

## Changelog / Notes for Future LLMs
- This plan proposes optional Docling integration via an adapter, not a wholesale rewrite. Extractor contracts remain stable.
- User-authored extractors live under `~/.finagent/extractors` and are auto-discovered; disable with `--no-plugins`.
- Prefer declarative specs for long-tail banks; fall back to Python when necessary.
- 2025-10-09: Declarative BofA spec currently drops negative-charge rows (needs spend-only fix) and Mercury spec returns 0 rows because transaction tables arrive as single-column blobs; detection also routes Mercury PDFs through the BofA extractor.
- 2025-10-09 (PM): Updated BofA account-type inference (Python + YAML) to default to credit card statements and tightened registry detection so Mercury PDFs aren’t hijacked by other extractors.
- 2025-10-10: Mercury Python extractor and declarative runtime both expand single-column Docling tables into structured rows; YAML specs now match Python output on the provided statement set.
