# plan_bulk_import_review_flow_100425

## Context
- Current bulk-import UX shows raw success text and filesystem paths, offering no progress feedback.
- After imports complete, users must manually inspect review JSON files and run `fin-enhance --apply-review` themselves.
- Goal: deliver an end-to-end UI workflow that (a) communicates progress, (b) summarizes imported transactions + pending reviews, and (c) helps users submit categorization decisions that the backend applies.

## Phase 1 — Progress Feedback
- [x] Add optimistic “Import in progress” assistant message with file count as soon as upload begins. *(2025-10-04; progress bubble now appears immediately with queued file summary.)*
- [x] Surface server-side stages (upload saved, extraction, import) via lightweight status updates when steps finish. *(Progress message updates to show completion + stage durations returned by API.)*
- [x] Ensure loading state clears even on failure; show human-friendly error text. *(Errors replace progress text with readable failure details.)*

## Phase 2 — Backend Summary Payloads
- [ ] Extend `/api/bulk-import` response to bundle enhanced CSV output (via `--stdout`) and parsed transactions.
- [ ] Read review JSON before returning; include unresolved review items directly in JSON payload.
- [ ] Guard response size by limiting transaction preview to a reasonable number (e.g., first 200 rows) and note truncation.
- [ ] Capture progress milestones in logs for future streaming.

## Phase 3 — UI Summary Views
- [ ] Render a table of imported transactions (date, merchant, amount, category/subcategory) from the response payload.
- [ ] Display review_needed entries in a dedicated review panel with key details (merchant, amount, suggested category, etc.).
- [ ] Replace raw path dump with concise messaging (friendly text + optional “open on disk” hint).

## Phase 4 — Review Decision Workflow
- [ ] Provide per-item controls (inputs for category, subcategory, learn toggle, notes) to collect user review decisions.
- [ ] Generate a decisions JSON artifact client-side (or as an MCP instruction) and hand it to the agent to run `fin-enhance --apply-review`.
- [ ] After decisions apply, refresh UI summary + review list (clearing resolved items) and report results in chat.
- [ ] Handle partial failures—show which decisions failed and why.

## Notes & Decisions
- Keep Option A batch import; review flow operates on its single review JSON output.
- CSV parsing likely uses `csv-parse` or similar; monitor payload size to avoid overloading the frontend.
- Subsequent iteration could add streaming progress (SSE/WebSocket); present scope stops at stepwise updates.
