# plan_ui_bulk_import_button_100325

## Context
- Goal: Provide a first-class bulk statement import entry point from the UI.
- UX: Add an "Import Statements" control adjacent to Suggested Queries and trigger bulk import pipeline once user selects sources.
- Back-end: No existing HTTP endpoint for uploads; need new Bun route that stores uploads and runs the Option A batch import (single fin-enhance invocation) per updated plan.
- Constraints: Always activate project venv before running CLI commands; keep filesystem writes under `~/.finagent` for user data.

## Phase 1 — UI Layout & Controls
- [x] Update `client/components/ChatInterface.tsx` top row to host Suggested Queries + Import button side-by-side on larger screens while stacking on small screens. *(2025-10-03; adds responsive flex layout, keeps header border in place.)*
- [x] Create `client/components/dashboard/ImportStatementsButton.tsx` encapsulating button styling + interaction hooks. *(2025-10-03; initial stub with Upload icon and disabled/loading states.)*
- [x] Ensure visual distinction from Suggested Queries (separate button styling per spec). *(Blue accent button separate from suggestion chip card; will revisit if design feedback arises.)*

## Phase 2 — File/Directory Selection UX
- [x] Implement progressive enhancement: try File System Access API (`showOpenFilePicker` / `showDirectoryPicker`) with fallbacks to hidden `<input type="file">` supporting directories (`webkitdirectory`). *(2025-10-03; see `client/hooks/useFileSelection.ts` for traversal and Bun fallback logic.)*
- [x] Normalize selected entries into a manifest of `{ name, relativePath, file }` covering single files, multiple files, or directory trees. *(Hook returns typed `SelectedEntry` with relative paths preserved.)*
- [x] Validate extensions (accept `.pdf`, `.csv`) and surface gentle error/skip messaging in UI state. *(Hook filters disallowed files and emits assistant message summarizing skips or queued files.)*

## Phase 3 — Server Upload & Bulk Import Orchestration
- [x] Add Bun `POST /api/bulk-import` handler that accepts multipart form uploads, persists them into `~/.finagent/imports/<timestamp>/` preserving relative paths, and returns job id + summary. *(2025-10-03; see `server/server.ts:51`—writes uploads via shared helper and responds with staging dir + summary.)*
- [x] Implement command runner that sequentially executes `fin-extract` for PDFs and collects resulting CSVs; then runs single `fin-enhance` call with all CSVs (Option A) producing optional review file. *(2025-10-03; `ccsdk/bulk-import.ts` exports shared pipeline used by both MCP tool and REST endpoint.)*
- [x] Stream or log progress to console and provide structured response (import counts, review file path, any failures) for UI consumption. *(Server logs `Bulk import starting …`; response includes extraction summaries, csv list, review path.)*
- [x] Add defensive cleanup/error handling (cleanup temp dirs on failure, detailed error payload). *(Failure path removes staging dir and returns JSON detail; extraction errors captured per-file.)*

## Phase 4 — UI Status & Feedback
- [x] Connect button component to call `/api/bulk-import` via `fetch`, handle optimistic loading state, and display completion summary in chat (new system message) or toast. *(2025-10-03; `client/components/ChatInterface.tsx:76` packages selected files into FormData, posts to REST endpoint, and appends assistant messages with progress + results.)*
- [x] Surface review file path (if returned) and highlight next steps for user. *(Success message includes review file path or notes auto-approval; spells out staging directory + counts.)*
- [x] Gracefully handle network/command errors and reset loading state. *(Catch block emits assistant error text and state resets via `resetSelection()`/`isImporting` flags.)*

## Notes & Decisions
- Option A (single `fin-enhance` invocation) is now the only supported bulk import path per plan update; keep hooks extensible for future Option B if resurrected.
- Uploaded statements live under `~/.finagent/imports/` so future CLI runs can reuse them; consider retention policy later.
- Future work: wire into progress logging infrastructure for live updates once available.
