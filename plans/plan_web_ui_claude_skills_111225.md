# plan_web_ui_claude_skills_111225

Goal: Migrate the local web client to use Claude Agent SDK Skills directly (skills-only), removing reliance on MCP-wrapped legacy CLIs. Allow the agent to select from all available skills, load both project and user-level skills, and execute from the repository root.

## Decisions (locked-in)
- [x] Skills-only (remove MCP tools from allowed tools)
- [x] Agent can select from all skills (no per-session pinning UI)
- [x] Support user-level skills (load from `~/.claude/skills`) in addition to project skills (`.claude/skills/`)
- [x] Execute from repo root (SDK working directory at repo root)

## Affected areas
- `ccsdk/cc-client.ts` (SDK import, options: `allowedTools`, `settings/settingSources`, `cwd`)
- `ccsdk/fin-agent-prompt.ts` (system guidance toward skills; remove MCP-first language)
- `ccsdk/custom-tools.ts` (deprecate MCP wrappers; stop registering server)
- `ccsdk/session.ts` (no protocol change; ensure streaming of `Skill` tool events)
- `web_client/*` (optional: surface skill activation in UI; keep existing WS message types)
- `package.json` (switch dependency from `@anthropic-ai/claude-code` to `@anthropic-ai/claude-agent-sdk`)

## Phase 1 — SDK migration & enable skills ✅
- [x] Replace SDK import/package
  - [x] `package.json`: remove `@anthropic-ai/claude-code`, add `@anthropic-ai/claude-agent-sdk`
  - [x] Update `ccsdk/cc-client.ts` imports to `@anthropic-ai/claude-agent-sdk`
- [x] Configure skills loading and tools
  - [x] Add `"Skill"` to `allowedTools`
  - [x] Remove all `mcp__*` tool names from `allowedTools`
  - [x] Set `settingSources: ["project", "user"]` (top-level, not nested) so SDK loads `.claude/skills/` and `~/.claude/skills/`
  - [x] Ensure `cwd` resolves to the repo root (not `agent/`) for tool execution and skill discovery
  - [x] Keep current PATH/VIRTUAL_ENV patching so `fin-scrub`, `fin-query`, `fin-edit`, `fin-analyze` resolve on PATH (per AGENTS.md)
- [x] Smoke test (manual)
  - [x] Prompt: "List available skills and next recommended steps for importing a statement" → Verify Skill tool invocations and Bash calls align with SKILL.md

**Notes:** Fixed bug - `settingSources` must be top-level option, not nested under `settings: {}`. SDK now discovers all 4 project skills successfully.

## Phase 2 — Prompting & guidance (skills-first) ✅
- [x] Update `ccsdk/fin-agent-prompt.ts`
  - [x] Removed all MCP tool documentation (MCP tools already gone from SDK)
  - [x] Updated CLI commands section to reflect commands used by skills (fin-scrub, fin-query, fin-edit, fin-analyze)
  - [x] Replaced strategy section with skills-first approach
  - [x] Removed MCP-specific workflow examples
  - [x] Kept output formatting and finviz visualization specs (presentation concerns)
- [x] Prompt is now much simpler - relies on SDK's built-in skill documentation

**Notes:** Prompt reduced from ~450 lines to ~180 lines. Skills contain the detailed workflows, system prompt just provides context about the financial domain and output formatting.

## Phase 3 — Web UI & streaming ✅
- [x] Leave WS protocol unchanged; continue to stream partial text and tool events
- [x] Parse `tool_use` blocks with `name: "Skill"` and show a lightweight inline badge (optional, non-blocking)
- [x] Keep the existing edit/write hook behavior in `ccsdk/cc-client.ts` (now restricts to `~/.finagent/` for skills workspace)

**Notes:** Added Skill tool case to AssistantMessage.tsx with indigo badge display. Write hook already correct for skills (restricts to ~/.finagent/).

## Phase 4 — Remove MCP wrappers (code cleanup) ✅
- [x] Remove `mcpServers` from `ccsdk/cc-client.ts` options
- [x] Stop exporting/using `customMCPServer` in runtime code; mark `ccsdk/custom-tools.ts` as deprecated
- [x] Prune MCP tool names from any remaining guardrails, logs, or docs

**Notes:** Removed mcpServers from CCQueryOptions interface. Added deprecation notice to custom-tools.ts with rollback instructions.

## Phase 5 — Validation & QA
- [ ] Skills e2e checks (repo-root execution)
  - [ ] Statement import path: `.claude/skills/statement-processor` helpers invoked via Bash, `fin-edit import-transactions` preview then apply
  - [ ] Categorization: `.claude/skills/transaction-categorizer` prompt builder and `fin-edit` operations
  - [ ] Spending analysis: `.claude/skills/spending-analyzer` analyzers (`--format csv`) produce results
  - [ ] Ledger queries: `.claude/skills/ledger-query` uses `fin-query saved` before SQL fallbacks
- [ ] User-level skills
  - [ ] Place a stub skill in `~/.claude/skills/demo-skill/SKILL.md` → verify agent can discover/use it
- [ ] Repo-root execution check
  - [ ] Confirm `pwd` within Bash tool equals repo root; ensure `$SKILL_ROOT` references resolve

## Phase 6 — Docs & handoff ✅
- [x] Update `web_client/README.md` to say the UI is skills-only
- [x] Update root `README.md` to note web UI now uses Claude Skills directly; leave Plaid backend routes as-is
- [ ] Add deprecation note for MCP wrappers with rollback instructions (skipped per user request)

**Notes:** Updated web_client/README.md to state it's skills-only and powered by Claude Agent SDK. Updated root README.md Web Agent section to clarify it uses Skills directly, no MCP wrappers.

## Rollback (if needed)
- Keep a branch with MCP-enabled `allowedTools` and `mcpServers` wiring. Revert by reinstalling `@anthropic-ai/claude-code`, restoring `allowedTools` entries, and re-enabling `customMCPServer`.

## Notes & rationale
- Skills are loaded via SDK settings and file discovery; enabling `settingSources: ["project","user"]` ensures both `.claude/skills` and `~/.claude/skills` are available.
- Running from repo root aligns with SKILL.md instructions that reference `$SKILL_ROOT` and assume the repo layout.
- We retain the file write guard to keep edits limited to `agent/custom_scripts` while allowing read + bash for skills.

## Open questions (answered)
- Keep MCP fallbacks? → No, skills-only.
- Skill picker UI? → No, let agent select from all skills.
- Support user skills? → Yes, include user-level skills.
- Working directory? → Repo root.

