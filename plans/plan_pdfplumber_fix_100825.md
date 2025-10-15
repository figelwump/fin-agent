## plan_pdfplumber_fix_100825

**Goal**
- Improve `pdfplumber`-based extraction so multi-page transaction tables (e.g., Chase 2024‑01, BofA 2025‑02) produce complete CSV output without relying on the slower Docling path.

**Key Files / Areas**
- `fin_cli/fin_extract/parsers/pdf_loader.py` – current pdfplumber table normalization.
- `fin_cli/fin_extract/extractors/*` – downstream extractors that expect consistent table headers/rows.
- Potential helper utilities under `fin_cli/fin_extract` if we introduce shared parsing logic.

### Phase 1 – Diagnose pdfplumber Gaps
- [x] Reproduce missing rows for Chase 2024‑01 and BofA 2025‑02 using `fin-extract … --engine pdfplumber` and capture per-page table outputs.
  - 2025-10-08: `fin-extract statements/chase/chase-credit-20240106-statements-6033-.pdf --stdout --engine pdfplumber` yields 82 rows vs Docling’s 41 (page 4 transactions missing in pdfplumber output). `fin-extract statements/bofa/eStmt_2025-02-22.pdf --spec ~/.finagent/extractors/bofa.yaml --stdout --engine pdfplumber` omits the ATT* Bill Payment line present in Docling output.
- [x] Inspect pdfplumber’s raw `extract_tables` / `extract_words` data to confirm why pages with continued tables (e.g., page 4 for Chase) fail normalization.
  - Direct `pdfplumber` inspection shows `page.extract_tables()` returns zero rows for Chase page 3 and only a 2-row summary on page 4, while `extract_text()` clearly includes 01/04 transaction lines; likewise BofA page 3 has the ATT* line in text but no table objects.
- [x] Document root causes in this plan (header detection issues, multi-column splits, etc.).
  - Transactions that flow onto later pages lack ruling lines; the pdfplumber default “stream” table detection fails and our `_normalize_table` logic never sees those rows. We need a fallback that groups words into ledger rows by column guides when `extract_tables` yields nothing, so multi-page continuations and wide descriptions (e.g., ATT* Bill Payment) are preserved.

### Phase 2 – Implement Robust Table Extraction
- [x] Design a fallback strategy when `extract_tables` misses expected ledger rows (e.g., custom word grouping by column guides, explicit table_settings, or per-page regex extraction).
  - 2025-10-08: Opted for a text-driven fallback that scrapes lines matching transaction patterns (primary/secondary dates + trailing amount) and synthesizes a `PdfTable` with canonical headers, avoiding pdfplumber’s brittle lattice detection.
- [x] Implement detection + fallback in `pdf_loader` (or a dedicated helper) ensuring headers remain consistent with existing extractors.
  - Added `_extract_transaction_table_from_text` in `fin_cli/fin_extract/parsers/pdf_loader.py`; when `extract_tables()` fails to yield a ledger-style header, we build synthetic tables per page with headers `Transaction Date`, `Posting Date`, `Description`, `Amount` (posting column dropped if unused). The loader now appends these tables so declarative specs and extractor logic can consume them.
- [ ] Add targeted unit/integration coverage (fixtures or focused tests) that assert the previously missing rows now appear.
- [ ] Add targeted unit/integration coverage (fixtures or focused tests) that assert the previously missing rows now appear.
- [ ] Record implementation notes here (new helpers, config knobs, trade-offs).
  - Fallback only triggers when no transaction headers are seen on a page to avoid duplicating existing tables; summary rows are still emitted but filtered downstream by existing specs/extractors. Consider future enhancements to stitch multi-line descriptions via positional data if statements with heavy wrapping surface.

### Phase 3 – Validation & Regression
- [ ] Re-run `fin-extract` for Chase 2024‑01 and BofA 2025‑02 with pdfplumber; compare outputs against Docling to confirm parity on row counts (+ spot-check sample rows).
- [ ] Smoke-test another representative statement to ensure we did not regress existing behavior.
- [ ] Summarize performance impact (wall-clock before/after) and remaining edge cases or future enhancements.

**Open Questions / Risks**
- Will more aggressive pdfplumber settings introduce duplicate or malformed rows on other issuers?
- Do we need issuer-specific heuristics, or can we keep the solution generic?
- Should we add a CLI/config toggle to opt-in to legacy behavior if new parsing produces surprises?
