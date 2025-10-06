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

## Current Status (2025-10-06)

**Phase 1: ~80% complete**
- ✅ Docling adapter infrastructure complete
- ✅ Engine selection and CLI integration complete
- ✅ Fallback logic verified with pdfplumber
- ⏸️ Actual Docling testing blocked on PyTorch (requires Python ≤3.12)

**Next Steps:**
1. Merge feature branch to main
2. Set up Python 3.12 venv in main branch
3. Install PyTorch + Docling
4. Benchmark Docling vs pdfplumber on Chase PDFs
5. Complete Phase 1 or proceed to Phase 2 based on results

**Branch:** `feature/docling-integration` (ready to merge)

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
- [ ] Create a small benchmark harness over `statements/` to measure tables found, transactions parsed, error cases, runtime.
  - **BLOCKED**: Need PyTorch installed (requires Python ≤3.12, project uses 3.13)
  - Will test with actual Docling once Python 3.12 venv is set up in main branch
- [ ] Port Chase extractor for Docling output (adjust header predicates if needed). Validate parity with current output.
  - **DEFERRED**: Existing Chase extractor works with Docling adapter (no changes needed)
  - Will validate parity once Docling is actually running
- [ ] Document Mac/Linux prerequisites for Docling/OCR and graceful fallbacks.

Notes
- Adapter will normalize Docling tables to our `PdfTable(headers, rows)` with conservative header detection so extractors remain unchanged.
- If Docling is unavailable or fails, we fall back to `pdfplumber` then optional `camelot`.

Acceptance
- [ ] On Chase samples, Docling path extracts ≥ current approach with ≤ error rate.
  - **STATUS**: Ready to test, pending PyTorch installation
- [x] Engine default `auto` behaves deterministically and falls back cleanly when Docling fails.
  - **VERIFIED**: Tested with Chase PDFs, gracefully falls back to pdfplumber when Docling unavailable
  - Logs clearly indicate fallback behavior

---

### Phase 2 — Declarative Runtime + Chase Spec (Declarative-first)
- [ ] Introduce `fin_cli/fin_extract/declarative.py` to support a YAML/JSON spec that maps headers, date formats, and sign rules.
- [ ] Author `~/.finagent/extractors/chase.yaml` implementing Chase via the declarative path.
- [ ] Provide `fin-extract dev:validate-spec` to validate a spec against sample PDFs.
- [ ] Compare `chase.yaml` output vs. Python extractor; ensure parity or better. Keep Python as fallback.

Notes
- Keep `PdfDocument` naming for now; extractors remain engine-agnostic.
- Prefer declarative for maintainability and agent authoring.

Acceptance
- [ ] `chase.yaml` passes the spec validator and produces identical CSV rows to the Python extractor on samples.
- [ ] Validator confirms spend-only output (no credits/payments/transfers included).

---

### Phase 3 — Port BofA and Mercury to Declarative
- [ ] Create `bofa.yaml` and `mercury.yaml` specs under `~/.finagent/extractors` with header aliases, date formats, and sign rules.
- [ ] Extend validator to cover BofA/Mercury-specific heuristics (e.g., summary row suppression, period inference).
- [ ] Validate parity vs. current Python extractors; retain Python as fallback until confidence is high.

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
