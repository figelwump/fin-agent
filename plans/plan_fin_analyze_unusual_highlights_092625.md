# plan_fin_analyze_unusual_highlights_092625

## Phase 1 – Understand Current Highlight Payload
- [x] Inspect the `unusual-spending` analyzer payload to see how `new_merchants` are populated and confirm they are raw merchant strings.
- [x] Identify available canonical/display fields in the analyzer context that we can leverage for deduping.

## Phase 2 – Implement Canonical Highlight Names
- [x] Update the analyzer to capture canonical + display metadata for merchants, ensuring `new_merchants` contains unique canonical entries with friendly names.
- [x] Adjust highlight rendering (`_unusual_markdown`) if needed to work with the new payload structure and avoid duplicate listings.
- [x] Add clarifying comments for the new canonical handling to aid future maintainers/LLMs.

## Phase 3 – Validate & Regress
- [x] Extend or add tests to verify the JSON payload and Markdown highlights display deduped, friendly merchant names.
- [x] Run targeted pytest coverage (`tests/fin_analyze/test_analyzers.py` and relevant CLI tests) under the virtualenv.
- [x] Smoke-test `fin-analyze unusual-spending` and `fin-export` locally to confirm highlights look correct in Markdown output.

### Notes
- Touchpoints likely include `fin_cli/fin_analyze/analyzers/unusual_spending.py` and `fin_cli/fin_export/exporter.py`.
- Aim to reuse existing canonicalization logic from merchant frequency analyzer to stay consistent project-wide.
