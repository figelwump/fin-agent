# plan_fin_agent_dashboard_100325

## Context & Goals

We want a top-half Dashboard pane and bottom-half Chat UI. The Dashboard shows suggested queries as buttons and renders results with better visuals (pie charts, line charts, tables), while defaulting to markdown for complex outputs. Users can pin an analysis to the dashboard; pinned widgets persist and refresh their data (on page load and manual refresh; background refresh protocol optional in v1).

Key goals:
- One-page split layout: Dashboard (top), Chat (bottom)
- Suggested query buttons that send prompts to the chat/agent
- Rich renderings for common analyses (charts/tables), markdown fallback
- Pin/unpin widgets and persist layout locally (v1 via localStorage)
- Optional: background refresh protocol so refreshes don’t pollute chat

---

## Architecture Notes

- Frontend: React running in Bun-served SPA (`client/`). Tailwind for styles.
- WebSocket: `server/server.ts` + `ccsdk/session.ts` stream assistant/tool events.
- Agent: Claude Code + MCP tools (`ccsdk/custom-tools.ts`). Current tools write analysis JSON to `~/.finagent/logs/*.json` and return a short status text.
- Rendering gap: Assistant text today is all markdown. We’ll add a lightweight “render spec” contract via code-fences in assistant text (language tag: `finviz`) that the UI interprets and renders with charts/tables.
- Library: Use `recharts` for charts (small API, good defaults). Simple HTML table for tabular results.

Trade-offs:
- v1 uses LLM-emitted `finviz` specs embedded in assistant text to trigger visuals. This avoids changing backend streaming now.
- v2 (optional) adds a background dashboard query channel to avoid polluting chat on refresh; requires extending WebSocket protocol.

---

## Rendering Contract (LLM → UI)

Assistant can emit an additional code block in its normal markdown response:

```finviz
{
  "version": "1.0",
  "spec": {
    "type": "pie|bar|line|table|metric",
    "title": "string",
    "data": Array|Object,
    "xKey": "string (bar/line)",
    "yKey": "string (bar/line)",
    "valueKey": "string (pie)",
    "nameKey": "string (pie)",
    "columns": [ {"key": "col", "label": "Col"} ] (table),
    "options": { "currency": true, "accumulate": false }
  }
}
```

Examples:
- Category breakdown → pie: `{ type: "pie", nameKey: "category", valueKey: "amount" }`
- Spending trends → line: `{ type: "line", xKey: "date", yKey: "amount" }`
- Merchant frequency → bar: `{ type: "bar", xKey: "merchant", yKey: "count" }`
- Subscriptions → table: columns + rows

Markdown stays as the natural language explanation; the `finviz` block hints the UI how to render the summary visually.

---

## Suggested Queries (initial set)

- Top categories (last 30d)
- Spending trends (last 6m)
- What did I spend on travel this year?
- What did I eat last week? (Food & Dining → Restaurants last 7d)
- Subscriptions (active)

Each button sends a clear prompt that nudges the agent to use `analyze_spending` (and include a `finviz` spec in the reply).

---

## Phases & Tasks

### Phase 1 — Finviz Contract + Prompting
- [x] Update `ccsdk/fin-agent-prompt.ts` with “Visual Outputs” section describing `finviz` spec and when to emit it.
- [x] Map analyzers → default visuals (categories→pie, trends→line, merchants→bar, subscriptions→table).
- [x] Note fallback to markdown for complex/special cases.

Notes:
- Added a "Visual Outputs (finviz)" section with examples and rules (escaped backticks for template string correctness).
- Default mappings documented as requested.
- Extended guidance to emit a finviz table for any transaction list outputs (e.g., largest/recent transactions), including an explicit example.

### Phase 2 — Viz Renderer Components
- [x] Add `client/components/viz/VizRenderer.tsx` to parse `finviz` blocks and route to chart/table components.
- [x] Add `PieChart`, `BarChart`, `LineChart`, `DataTable`, `MetricCard` components using `recharts` and HTML tables.
- [x] Extend `AssistantMessage.TextComponent` code-block renderer to detect `language-finviz` and render via `VizRenderer`.

Notes:
- Dependency added: `recharts@^2.11` (installed with Bun). The component uses responsive containers and minimal styling.
- AssistantMessage now special-cases `language-finviz` code fences and falls back to raw JSON with an error banner if invalid.

### Phase 3 — Suggested Queries Bar (Chat)
- [x] Create `client/components/dashboard/SuggestedQueries.tsx` with buttons wired to existing `sendMessage`.
- [x] Integrate suggested queries bar at top of chat (no separate dashboard pane).

Notes:
- Removed dashboard split. Kept chat as the main UI; added a fixed Suggested Queries bar above messages.
- Suggested queries now configured in code at `client/config/suggestions.yaml`, loaded at runtime (no in-UI editing). Includes: Top Categories, Subscriptions, Travel YTD, Restaurants Last Week, Spending Trends (6m), Largest Transactions (30d).

### Phase 4 — Pinning & Persistence (v1)
- [ ] REMOVED — Product direction change: dashboard and pinning removed.

### Phase 5 — Background Refresh Channel (v2, optional)
- [ ] Extend WS protocol: new message type `dash_query` with `correlationId` and `prompt`.
- [ ] In `ccsdk/session.ts`, propagate `correlationId` back on all outbound messages from that turn.
- [ ] In `client/App.tsx`, route `dash_query` responses to Dashboard store instead of chat timeline.
- [ ] On page load, replay pinned items via `dash_query` and update visuals silently.

### Phase 6 — Polish & Docs
- [ ] Add short README section: dashboard usage, pinning, refresh semantics.
- [ ] Light themer (dark-friendly neutrals) and empty states.
- [ ] Minimal error messages for failed renders / invalid finviz specs.

---

## Relevant Files
- Frontend: `client/App.tsx`, `client/components/ChatInterface.tsx`, `client/components/message/AssistantMessage.tsx`
- New: `client/components/viz/*`, `client/components/dashboard/*`
- Agent prompt: `ccsdk/fin-agent-prompt.ts`
- WebSocket protocol (optional v2): `server/server.ts`, `ccsdk/session.ts`, `client/hooks/useWebSocket.ts`, `client/App.tsx`

---

## Technical Decisions
- Chosen `recharts` due to simple API and zero config build with Bun.
- Keep v1 backend unchanged; rely on prompt + code-fence contract.
- v1 persistence in `localStorage`; future server persistence optional (SQLite table + endpoints).
- Keep rendering narrowly scoped: only render when a valid `finviz` block is present.

---

## Open Questions
- Should we store dashboard state server-side (multi-device) or keep it local for now?
- Any preferred charting library/theme?
- For background refresh, OK to extend WS protocol now, or land as v2?
- Any default dashboard cards you’d like pinned for new users?

---

## Rollout Plan
- Ship Phases 1–3 only: finviz contract, renderer, suggested queries bar in chat.
- Dashboard and pinning removed per new direction.
