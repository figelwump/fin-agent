# plan_review_flow_polish_100725

## Phase 1 — Review Item Deduplication
- [x] Inspect `bulkImportStatements` output and UI state to confirm where duplicates enter (review JSON vs. client rendering).
- [x] Add deterministic deduplication of review items (keyed by transaction id + amount) before rendering in `ImportSummaryBlock`.
- [ ] Verify acceptance/edit flows still work with deduped collection (state maps, Done Reviewing counts, etc.). *(Note: requires manual UI pass once server is running.)*

## Phase 2 — Reliable fin-enhance Invocation
- [x] Update agent runtime environment so every Bash command has `.venv/bin` on `PATH` and `VIRTUAL_ENV` set (no manual `cd .. && python -m`). *(ccsdk/cc-client.ts)*
- [x] Reinforce prompt guidance to explicitly `source .venv/bin/activate` before running fin-cli commands when using Bash directly. *(ccsdk/fin-agent-prompt.ts)*
- [ ] Manual smoke test: drive a review acceptance flow and confirm agent now runs `fin-enhance --apply-review` via the CLI entrypoint.

## Phase 3 — “Suggest Category” UX
- [x] Add a “Suggest Category” button alongside Accept/Edit in the review list.
- [x] On click, send a structured chat message asking the agent for category suggestions for that specific transaction (include merchant, amount, date, description).
  - Notes: Button renders in `client/components/message/ImportSummaryBlock.tsx` and leverages the structured prompt pipeline introduced in `client/components/ChatInterface.tsx`.

## Phase 4 — User-Friendly Agent Messaging
- [x] Redesign the review handoff text so the user sees clean, human-readable prompts (no filesystem paths, transaction hashes, or raw command instructions).
- [x] Keep the implementation details available to the agent via hidden context/metadata or structured payloads so functionality remains intact.
- [ ] Verify responses stay concise while preserving the validation guidance (existing-category suggestions before applying changes).
  - Notes: Structured prompts now originate in `client/components/message/ImportSummaryBlock.tsx`, carrying metadata for the agent while rendering user-friendly text via the `StructuredPrompt` pipeline.

## Phase 5 — Streaming Assistant Responses
- [x] Enable partial message streaming in `CCClient` (`includePartialMessages: true`) and ensure session resumes keep the flag.
- [x] Tag partial chunks in the WebSocket payload so the frontend can distinguish streaming updates from final messages.
- [x] Update the React client to append partial text to the latest assistant bubble instead of spawning new entries, yielding near real-time updates.
  - Notes: Partial events stream via `assistant_partial` messages emitted in `ccsdk/session.ts`; `App.tsx` and `ChatInterface.tsx` manage the live transcript using the shared `StructuredPrompt` pipeline without duplicate loading placeholders.

## Notes & Considerations
- Deduping should happen before stateful operations to avoid double-counting acceptance progress indicators.
- While tightening environment variables, ensure server-started processes (bulk import, MCP tools) continue to inherit the same virtualenv assumptions.
- “Suggest Category” messaging should reuse taxonomy validation guidance so the agent proposes existing categories when possible.
