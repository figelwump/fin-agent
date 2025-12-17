# Web Agent UI

The `web_client/` directory hosts a lightweight React front end for the local web agent. The UI is powered by the [Claude Agent SDK](https://docs.claude.com/en/docs/agent-sdk/overview), using skills directly from `.claude/skills/` and `~/.claude/skills/`. 

## Features
- Launch the assistant UI with `bun run dev`.
- The agent uses Claude Skills directly (statement-processor, transaction-categorizer, spending-analyzer, ledger-query, asset-tracker).
- Import statements via the local file picker; the workflow routes through the `statement-processor` skill.
- Review recent messages, suggested prompts, and in-progress operations (imports, analysis requests, etc.).

## Local Development
```bash
bun install
bun run dev
```
Open `http://localhost:3000` to interact with the UI. The dev server proxies API calls to the Bun backend.

## Code Layout

```
web_client/
├── client/                  # React frontend
│   ├── src/
│   │   ├── components/     # React components (chat interface, messages, tool displays)
│   │   ├── hooks/          # React hooks for WebSocket and state management
│   │   ├── lib/            # Utilities and helpers
│   │   └── App.tsx         # Main app component
│   └── public/             # Static assets
├── server/                  # Bun backend
│   ├── server.ts           # Main server entry point (WebSocket + HTTP routes)
│   └── routes/             # API route handlers
├── ccsdk/                   # Claude Agent SDK integration
│   ├── cc-client.ts        # SDK initialization and configuration
│   ├── fin-agent-prompt.ts # System prompt for financial domain
│   └── session.ts          # WebSocket session management and streaming
└── package.json            # Dependencies (@anthropic-ai/claude-agent-sdk, etc.)
```

**Key components:**
- **ccsdk/cc-client.ts**: Configures Claude Agent SDK with skills loading (`settingSources: ["project", "user"]`), sets working directory to repo root, and manages tool permissions.
- **ccsdk/session.ts**: Handles WebSocket protocol for streaming assistant messages, tool use events, and skill activations to the frontend.
- **client/src/components**: React UI components for rendering chat messages, tool invocations (including `Skill` tool badges), and statement import workflows.
- **server/server.ts**: Bun server that manages WebSocket connections and proxies requests to the Claude Agent SDK.

## Testing
```bash
bun test
```
