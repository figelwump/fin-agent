# Web Agent UI

The `client/` directory hosts a lightweight React front end for the local web agent. Key views include the chat interface, statement import helpers, and suggested prompts for the fin-cli skills.

## Features
- Launch the assistant UI against the Bun server (`bun run server/server.ts`).
- Import statements via the local file picker; the workflow still routes through the `statement-processor` skill.
- Review recent messages, suggested prompts, and in-progress operations (imports, analysis requests, etc.).

## Plaid Integration
The open-source build omits the Plaid Link UI. The underlying Plaid server routes remain for future opt-in use, but the front end no longer renders a “Connect Bank” button. If you need Plaid ingestion:
1. Re-enable the components under `client/components/dashboard/` from history (see `ConnectedPlaidAccounts` and `PlaidLinkButton`).
2. Configure credentials via environment variables (`PLAID_CLIENT_ID`, `PLAID_SECRET`, etc.) and restart the Bun server.
3. Make sure the user-facing copy explains that Plaid imports are optional and require explicit consent.

## Local Development
```bash
bun install
bun run dev
```
Open `http://localhost:3000` to interact with the UI. The dev server proxies API calls to the Bun backend.

## Testing
```bash
bun test
```

> Tip: keep the UI aligned with the skills-first workflow documented in the repository root README. Avoid reintroducing Plaid UI affordances unless the user explicitly opts in.
