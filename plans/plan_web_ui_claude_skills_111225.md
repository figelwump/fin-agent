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

## Phase 1 — SDK migration & enable skills
- [ ] Replace SDK import/package
  - [ ] `package.json`: remove `@anthropic-ai/claude-code`, add `@anthropic-ai/claude-agent-sdk`
  - [ ] Update `ccsdk/cc-client.ts` imports to `@anthropic-ai/claude-agent-sdk`
- [ ] Configure skills loading and tools
  - [ ] Add `"Skill"` to `allowedTools`
  - [ ] Remove all `mcp__*` tool names from `allowedTools`
  - [ ] Set `settings: { settingSources: ["project", "user"] }` so SDK loads `.claude/skills/` and `~/.claude/skills/`
  - [ ] Ensure `cwd` resolves to the repo root (not `agent/`) for tool execution and skill discovery
  - [ ] Keep current PATH/VIRTUAL_ENV patching so `fin-scrub`, `fin-query`, `fin-edit`, `fin-analyze` resolve on PATH (per AGENTS.md)
- [ ] Smoke test (manual)
  - [ ] Prompt: “List available skills and next recommended steps for importing a statement” → Verify Skill tool invocations and Bash calls align with SKILL.md

## Phase 2 — Prompting & guidance (skills-first)
- [ ] Update `ccsdk/fin-agent-prompt.ts`
  - [ ] Emphasize using Skills for statement processing, categorization, analysis, and ledger queries
  - [ ] Remove MCP references and legacy CLI-first instructions
  - [ ] Keep guardrails and file write hook guidance
- [ ] Verify the agent prefers skills (check early turns for Skill tool invocation)

## Phase 3 — Web UI & streaming
- [ ] Leave WS protocol unchanged; continue to stream partial text and tool events
- [ ] Parse `tool_use` blocks with `name: "Skill"` and show a lightweight inline badge (optional, non-blocking)
- [ ] Keep the existing edit/write hook behavior in `ccsdk/cc-client.ts` (Script writes only under `agent/custom_scripts`)

## Phase 4 — Remove MCP wrappers (code cleanup)
- [ ] Remove `mcpServers` from `ccsdk/cc-client.ts` options
- [ ] Stop exporting/using `customMCPServer` in runtime code; mark `ccsdk/custom-tools.ts` as deprecated
- [ ] Prune MCP tool names from any remaining guardrails, logs, or docs

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

## Phase 6 — Docs & handoff
- [ ] Update `web_client/README.md` to say the UI is skills-only
- [ ] Update root `README.md` to note web UI now uses Claude Skills directly; leave Plaid backend routes as-is
- [ ] Add deprecation note for MCP wrappers with rollback instructions

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

