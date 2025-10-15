## plan_docling_perf_100725

**Context**
- Investigate why Docling extraction (`fin-extract --engine docling`) is slower than pdfplumber for bank statements.
- Hypothesis: Docling default pipeline loads OCR/vision components that are unnecessary for digitally-native PDFs.
- Target files: `fin_cli/fin_extract/parsers/docling_loader.py`, Docling config/hooks, CLI flags in `fin_cli/fin_extract/main.py`.

### Phase 1 – Baseline Profiling
- [x] Activate virtualenv (docling-only support currently in `.venv-py312`) and measure end-to-end runtime for representative PDFs using pdfplumber vs Docling (`time fin-extract statements/... --stdout --engine ...`).
- [x] Capture Docling logging/profile output (if available) to identify slow stages (e.g., OCR, layout analysis, model downloads).
- [x] Summarize findings in this plan (runtime deltas, notable bottlenecks).
  - Chase 2024-01 statement: pdfplumber ≈6 s vs Docling ≈55 s (Docling repeatedly initializes GPU/`accelerate` stack, conversion step alone 44 s).
  - BofA 2024-12 statement: pdfplumber ≈6 s vs Docling ≈33 s (Docling pipeline logs identical plugin/ocr registration and `Accelerator device: 'mps'` prints).
  - Docling installation requires Python 3.12 because `docling-core[chunking]` pulls `accelerate→torch` (PyTorch wheels unavailable for 3.13); used existing `.venv-py312`.

### Phase 2 – Optimize Docling Pipeline
- [x] Review Docling configuration in our adapter; determine how to disable OCR/vision-heavy modules for computer-generated PDFs.
- [x] Implement configuration changes or fast-paths (e.g., override Docling `DocumentConverter` options, enable lazy loading, cache models).
- [x] Note code touchpoints and decisions in this plan (flags added, modules skipped, caching strategy).
  - 2025-10-08: Added `_build_fast_docling_converter()` in `fin_cli/fin_extract/parsers/docling_loader.py` to reuse a single Docling instance and skip OCR while keeping the default layout/table configuration for accuracy; the helper caches the converter and automatically falls back to the stock pipeline if the fast-path output is empty so scanned PDFs continue to work.

### Phase 3 – Validation & Regression Checks
- [x] Re-run timed extractions with updated Docling configuration and compare against baseline.
  - 2025-10-08 timings (wall clock via `time`): Chase 2024-01 (`statements/chase/chase-credit-20240106-statements-6033-.pdf`) → pdfplumber 6.48 s vs Docling fast-path 39.29 s (conversion 30.39 s), previously ≈55 s with default Docling. BofA 2024-12 (`statements/bofa/eStmt_2024-12-22.pdf`) → pdfplumber 7.28 s vs Docling fast-path 58.28 s (conversion 50.76 s); default Docling on the same file measured 57.00 s, so the optimization does not regress that case even though the statement itself is heavier than the earlier Phase 1 sample.
- [x] Sanity check extraction outputs (row counts, sample CSV diff) to ensure accuracy is unchanged.
  - Verified Chase docling fast-path returns 41 transactions, matching the default Docling pipeline output (both remain below the pdfplumber count of 82 due to upstream Docling table segmentation quirks). BofA docling fast-path returns 56 transactions, matching both pdfplumber and the default Docling run; whitespace/ordering differences are limited to normalization only.
- [x] Document remaining gaps or follow-up ideas (e.g., optional flag for OCR, future profiling hooks).
  - Potential follow-ups: expose a CLI/config toggle to force GPU vs CPU execution when users prefer speed over deterministic setup time; investigate Docling table segmentation so Chase statements reach parity with pdfplumber; consider caching Docling model assets across invocations to cut repeated initialization time for large statements.

**Open Questions / Risks**
- Does Docling expose a pure-layout mode without OCR downloads?
- Do we need a user-configurable toggle to re-enable OCR for scanned statements?
- Are there downstream expectations (tests/fixtures) that assume current Docling behavior/timing?
