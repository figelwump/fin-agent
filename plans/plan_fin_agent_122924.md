# Fin-Agent Implementation Plan

**Branch:** `feature/fin-agent`
**Created:** 2024-12-29
**Goal:** Build an AI agent that provides natural language interface to fin-cli tools

## Overview

Build a Claude Code SDK-based agent that wraps the existing fin-cli commands, allowing users to interact with their financial data through conversational queries. The agent will use a hybrid approach: MCP tools for high-value operations, Bash tool for flexibility.

**Key Principles:**
- YOU write all code (user request)
- Follow patterns from email-agent demo
- Start with backend/agent infrastructure, then UI
- Test each piece before moving to next phase

## Architecture

```
fin-agent/
  agent/
    .claude/
      agents/           # Specialized subagents
    data/              # Agent data storage
  ccsdk/               # Claude Code SDK integration
    ai-client.ts       # SDK wrapper
    custom-tools.ts    # MCP tools for fin-cli
    fin-agent-prompt.ts # System prompt
    session.ts         # Session management
    websocket-handler.ts # WebSocket handling
    message-queue.ts   # Async message queue
    types.ts           # TypeScript types
  server/
    server.ts          # Main server
    endpoints/
      transactions.ts  # Transaction APIs
      analysis.ts      # Analysis APIs
  client/              # React UI (Phase 3)
  database/            # Existing fin-cli database
```

## Implementation Phases

### Phase 1: Project Setup & Dependencies ✅
**Goal:** Set up the fin-agent project structure with proper dependencies

- [x] 1.1: Create branch and initial structure
  - Create branch `feature/fin-agent`
  - Create directories: `agent/`, `agent/.claude/agents/`, `agent/data/`, `ccsdk/`, `server/`, `server/endpoints/`
  - YOU will create these directories manually or via bash

- [x] 1.2: Initialize Node/Bun project
  - Create `package.json` with necessary dependencies
  - Look at email-agent's package.json for reference
  - Key dependencies: `@anthropic-ai/claude-code`, `zod`, `dotenv`
  - Dev dependencies: `@types/node`, `@types/bun`, `typescript`
  - YOU will write the package.json

- [x] 1.3: Create TypeScript configuration
  - Create `tsconfig.json`
  - Reference email-agent's tsconfig for settings
  - YOU will write the tsconfig

- [x] 1.4: Create environment configuration
  - Create `.env.example` with required variables (ANTHROPIC_API_KEY, etc.)
  - Document what each variable is for
  - YOU will write this file

**Completion criteria:** `bun install` runs successfully, directories exist ✅

**Commit:** bf91f41

---

### Phase 2: Core SDK Integration (Backend Focus)
**Goal:** Set up Claude Code SDK integration and basic agent infrastructure

**IMPORTANT:** You are writing all code in this phase. I will point you to patterns and explain concepts, but you implement.

- [ ] 2.1: Create TypeScript types
  - **File:** `ccsdk/types.ts`
  - **What to implement:** Export types for SDK messages, user messages, system messages
  - **Pattern:** Look at email-agent's `ccsdk/types.ts` - it re-exports SDK types and defines custom message types
  - **Key types needed:**
    - `SDKMessage`, `SDKUserMessage` (from SDK)
    - Custom WebSocket message types if needed
  - YOU will write this file

- [ ] 2.2: Create message queue for async communication
  - **File:** `ccsdk/message-queue.ts`
  - **What to implement:** A queue for handling async messages between components
  - **Pattern:** Copy the MessageQueue class from email-agent's message-queue.ts - it's a generic utility
  - **Why:** Allows components to communicate without tight coupling
  - YOU will write this file

- [ ] 2.3: Create system prompt
  - **File:** `ccsdk/fin-agent-prompt.ts`
  - **What to implement:** Export a constant string with the agent's system prompt
  - **Pattern:** Look at email-agent's `email-agent-prompt.ts`
  - **Content guidance:**
    - Describe agent's purpose (financial analysis assistant)
    - List available fin-cli commands (fin-extract, fin-enhance, fin-analyze, etc.)
    - Explain when to use MCP tools vs Bash
    - Database location: ~/.finagent/data.db
    - Always use --format json for parseable output
  - YOU will write this prompt

- [ ] 2.4: Create custom MCP tools for fin-cli
  - **File:** `ccsdk/custom-tools.ts`
  - **What to implement:** MCP server with tools wrapping fin-cli commands
  - **Pattern:** Study email-agent's custom-tools.ts
  - **Key concepts to understand:**
    - `createSdkMcpServer()` creates the MCP server
    - `tool()` defines each tool with name, description, schema, handler
    - Use `zod` for parameter validation
    - Tools return `{ content: [{ type: "text", text: "..." }] }`
  - **Tools to create:**
    1. `analyze_spending` - Wraps fin-analyze with common analyzers
    2. `search_transactions` - Wraps fin-query for transaction search
    3. `import_statement` - Wraps fin-extract + fin-enhance workflow
  - **Implementation tips:**
    - Use dynamic imports for lazy loading: `await import('../path')`
    - Handle errors gracefully
    - Parse JSON output from fin-cli commands
    - Format output for readability
  - YOU will write this file
  - **ASK ME:** If you need help understanding how to call fin-cli commands from Node.js

- [ ] 2.5: Create AI client wrapper
  - **File:** `ccsdk/ai-client.ts`
  - **What to implement:** Wrapper class around SDK's `query()` function
  - **Pattern:** Study email-agent's ai-client.ts
  - **Key concepts:**
    - `AIClient` class with `queryStream()` method
    - Import `query` from `@anthropic-ai/claude-code`
    - Configure options: maxTurns, cwd, model, allowedTools, appendSystemPrompt, mcpServers
    - Yield messages from the SDK's async iterator
  - **Configuration:**
    - Set `cwd` to `agent/` directory
    - Import your custom MCP server from step 2.4
    - Import system prompt from step 2.3
    - Allow standard tools: Bash, Read, Write, Edit, Glob, Grep, etc.
  - YOU will write this file

- [ ] 2.6: Create session management
  - **File:** `ccsdk/session.ts`
  - **What to implement:** Session class that manages a single conversation with Claude
  - **Pattern:** Study email-agent's session.ts carefully
  - **Key concepts:**
    - Each session has a unique ID
    - Sessions maintain `sdkSessionId` for multi-turn conversations
    - `addUserMessage()` processes user input through AI client
    - Messages are broadcast to subscribed WebSocket clients
    - Capture `session_id` from SDK for resume functionality
  - **Important:** This enables conversational context ("show August spending" → "what about subscriptions?")
  - YOU will write this file
  - **ASK ME:** If multi-turn conversation pattern is unclear

- [ ] 2.7: Create WebSocket handler
  - **File:** `ccsdk/websocket-handler.ts`
  - **What to implement:** Manages WebSocket connections and routes to sessions
  - **Pattern:** Study email-agent's websocket-handler.ts
  - **Key responsibilities:**
    - `onOpen()`: Handle new WebSocket connections
    - `onMessage()`: Parse incoming messages and route to sessions
    - `onClose()`: Cleanup when client disconnects
    - Manage session lifecycle
  - **Message types to handle:**
    - `chat` - User sending a message
    - `subscribe` - Client subscribing to a session
    - `unsubscribe` - Client leaving a session
  - YOU will write this file

**Completion criteria:**
- All TypeScript files compile without errors
- Can import and instantiate classes (no runtime needed yet)

---

### Phase 3: Server & API Endpoints
**Goal:** Create HTTP server with WebSocket support and REST endpoints

- [ ] 3.1: Create basic server
  - **File:** `server/server.ts`
  - **What to implement:** Bun server with WebSocket and HTTP endpoints
  - **Pattern:** Study email-agent's server/server.ts
  - **Key features:**
    - WebSocket endpoint at `/ws`
    - Static file serving for future UI
    - CORS headers for API endpoints
    - Initialize WebSocketHandler
  - **Endpoints to create:**
    - `GET /` - Serve HTML (placeholder for now)
    - `/ws` - WebSocket upgrade
    - `POST /api/chat` - Should redirect to WebSocket
  - YOU will write this file

- [ ] 3.2: Create transaction endpoints
  - **File:** `server/endpoints/transactions.ts`
  - **What to implement:** REST API for transaction operations
  - **Endpoints:**
    - `GET /api/transactions/recent` - Get recent transactions
    - `POST /api/transactions/search` - Search transactions
    - `GET /api/transactions/:id` - Get single transaction
  - **Pattern:** Look at email-agent's endpoints/emails.ts
  - **Data source:** Direct SQLite queries to ~/.finagent/data.db
  - YOU will write this file

- [ ] 3.3: Create analysis endpoints
  - **File:** `server/endpoints/analysis.ts`
  - **What to implement:** REST API for analysis operations
  - **Endpoints:**
    - `GET /api/analysis/summary?month=YYYY-MM` - Quick summary
    - `POST /api/analysis/run` - Run specific analyzer
  - **Consider:** These might just be helpers - main analysis happens through agent
  - YOU will write this file

- [ ] 3.4: Test server startup
  - Run `bun run server/server.ts`
  - Verify server starts without errors
  - Test WebSocket connection with a simple client (can use `wscat` or browser console)
  - **Manual test:** You will manually verify this works

**Completion criteria:**
- Server starts without errors
- Can connect to WebSocket endpoint
- REST endpoints return data (even if simple)

---

### Phase 4: Agent Testing & Refinement
**Goal:** Test the agent through command-line before building UI

- [ ] 4.1: Create test script
  - **File:** `agent/test-agent.ts`
  - **What to implement:** Simple script to test agent without UI
  - **Functionality:**
    - Connect to WebSocket
    - Send test queries
    - Print responses
  - **Test queries:**
    - "Show me transactions from last month"
    - "What are my top spending categories?"
    - "Detect my subscriptions"
  - YOU will write this script

- [ ] 4.2: Test MCP tools
  - Test each custom tool works correctly
  - Verify fin-cli commands execute properly
  - Check JSON parsing and formatting
  - **Manual testing:** You will run queries and verify outputs

- [ ] 4.3: Test multi-turn conversations
  - Test context retention across messages
  - Verify session management works
  - Example flow:
    1. "Show August spending"
    2. "What about subscriptions?" (should understand context)
    3. "Show me grocery spending" (should understand still talking about August)
  - **Manual testing:** You will conduct these test conversations

- [ ] 4.4: Refine system prompt
  - Based on testing, improve system prompt
  - Add better examples
  - Clarify tool usage guidance
  - YOU will iterate on the prompt

**Completion criteria:**
- Agent responds to queries correctly
- MCP tools execute fin-cli commands successfully
- Multi-turn conversations maintain context
- Outputs are well-formatted

---

### Phase 5: Basic UI (React Frontend)
**Goal:** Create minimal chat interface for agent interaction

**Note:** This phase can be started once Phase 4 is working. I'll guide you through React patterns.

- [ ] 5.1: Set up React project structure
  - Create `client/` directory structure
  - Create `client/index.html`, `client/index.tsx`, `client/App.tsx`
  - Configure Bun to serve and transpile React
  - **Pattern:** Study email-agent's client setup
  - YOU will create these files

- [ ] 5.2: Create WebSocket hook
  - **File:** `client/hooks/useWebSocket.ts`
  - **What to implement:** React hook for WebSocket connection
  - **Pattern:** Copy email-agent's useWebSocket.ts hook
  - **Features:** Auto-reconnect, message queuing, connection status
  - YOU will write this hook

- [ ] 5.3: Create chat interface component
  - **File:** `client/components/ChatInterface.tsx`
  - **What to implement:** Main chat UI
  - **Features:**
    - Message input
    - Message history display
    - Connection status indicator
    - Loading states
  - **Pattern:** Study email-agent's ChatInterface.tsx
  - YOU will write this component

- [ ] 5.4: Create message renderer
  - **File:** `client/components/MessageRenderer.tsx`
  - **What to implement:** Display different message types
  - **Message types:**
    - User messages
    - Assistant messages
    - Tool use display
    - System messages
  - **Pattern:** Email-agent has great message rendering
  - YOU will write this component

- [ ] 5.5: Add basic styling
  - Create `client/globals.css`
  - Add Tailwind configuration
  - Keep it simple - can beautify later
  - **Pattern:** Email-agent uses Tailwind
  - YOU will add styling

- [ ] 5.6: Test UI interaction
  - Start server
  - Open browser to `http://localhost:3000`
  - Send queries through UI
  - Verify responses appear correctly
  - **Manual testing:** You will test in browser

**Completion criteria:**
- UI loads without errors
- Can send messages through UI
- Receives and displays agent responses
- Basic styling is functional

---

### Phase 6: Enhanced UI Features (Optional Enhancements)
**Goal:** Add visualizations and transaction-specific UI components

- [ ] 6.1: Create transaction list view
  - Display recent transactions
  - Filterable/sortable table
  - YOU will implement this

- [ ] 6.2: Create analysis visualization component
  - Charts for spending trends
  - Category breakdowns
  - Consider using a chart library (recharts, chart.js)
  - YOU will implement this

- [ ] 6.3: Create category management UI
  - View/edit categories
  - Approve suggested categories
  - YOU will implement this

**Completion criteria:**
- Enhanced UI provides better UX for financial data
- Visualizations are clear and useful

---

## Relevant Files

Will be populated as implementation progresses.

## Notes

### Key Patterns to Understand

1. **MCP Tools Pattern:**
   - Tools are functions that Claude can call
   - Defined with `tool(name, description, schema, handler)`
   - Schema uses Zod for type safety
   - Handler is async function that executes the tool

2. **Session Pattern:**
   - Each conversation is a session
   - Sessions maintain context via `sdkSessionId`
   - Use `resume` option to continue conversations
   - Sessions broadcast messages to subscribed clients

3. **WebSocket Pattern:**
   - Bi-directional communication between client and server
   - Server pushes updates as they happen (streaming)
   - Client can have multiple sessions

4. **Hybrid Tool Approach:**
   - MCP tools for high-value, common operations
   - Bash tool for ad-hoc queries and flexibility
   - Agent decides which to use based on context

### Technical Decisions

- **Runtime:** Bun (fast, TypeScript native, used by email-agent)
- **Database:** Existing SQLite at ~/.finagent/data.db
- **UI Framework:** React (matches email-agent pattern)
- **Styling:** Tailwind CSS (simple, matches email-agent)
- **Model:** Claude Opus via SDK (can change in ai-client config)

### Questions to Consider

- Should we support file uploads for PDFs through UI?
- Do we want real-time transaction monitoring?
- Should we add export/download features for reports?
- Multi-user support needed? (probably not initially)

---

## Testing Strategy

### Phase 2-3 Testing (Backend):
- Unit test MCP tools individually
- Test WebSocket connection with `wscat` or simple client
- Verify fin-cli commands execute correctly
- Check session persistence across messages

### Phase 4 Testing (Agent):
- Test with command-line script
- Verify multi-turn conversations
- Test error handling
- Validate output formatting

### Phase 5-6 Testing (UI):
- Manual browser testing
- Test WebSocket reconnection
- Verify message streaming
- Test on different screen sizes

---

## Future Enhancements (Not in initial scope)

- Authentication/authorization
- Multi-user support
- Real-time transaction syncing
- Mobile-responsive design
- Data export features
- Budget tracking
- Financial goals
- Notifications for unusual spending

---

## Getting Started

**First step:** Create the branch and set up the project structure (Phase 1.1)

When you're ready to start, let me know and we'll work through Phase 1 together. Remember: **you write the code**, I guide and explain!
