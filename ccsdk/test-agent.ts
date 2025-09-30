import { WebSocket } from "ws";

const query = process.argv[2]; // Get query from command line

if (!query) {
  console.error("Usage: bun run ccsdk/test-agent.ts \"your query here\"");
  process.exit(1);
}

const ws = new WebSocket("ws://localhost:3000/ws");

ws.on("open", () => {
  console.log("Connected to agent\n");

  // Send chat message
  ws.send(JSON.stringify({
    type: "chat",
    content: query
  }));
});

ws.on("message", (data) => {
  const message = JSON.parse(data.toString());

  switch (message.type) {
    case "connected":
      console.log(`✓ ${message.message}`);
      if (message.availableSessions?.length > 0) {
        console.log(`Available sessions: ${message.availableSessions.join(", ")}`);
      }
      console.log();
      break;

    case "session_info":
      console.log(`Session ID: ${message.sessionId}`);
      console.log(`Message count: ${message.messageCount}`);
      console.log();
      break;

    case "user_message":
      console.log(`\n[You]: ${message.content}\n`);
      break;

    case "assistant_message":
      // Stream assistant text as it arrives
      process.stdout.write(message.content);
      break;

    case "tool_use":
      console.log(`\n\n🔧 [Tool: ${message.toolName}]`);
      console.log(`Input: ${JSON.stringify(message.toolInput, null, 2)}`);
      break;

    case "tool_result":
      console.log(`✓ [Tool completed]`);
      if (message.isError) {
        console.error(`Error: ${JSON.stringify(message.content)}`);
      }
      break;

    case "result":
      console.log("\n");
      if (message.success) {
        console.log(`✓ Query completed successfully`);
        console.log(`Cost: $${message.cost?.toFixed(4) || "0.0000"}`);
        console.log(`Duration: ${message.duration}ms`);
      } else {
        console.error(`✗ Query failed: ${message.error}`);
      }

      // Close connection and exit
      ws.close();
      setTimeout(() => process.exit(message.success ? 0 : 1), 100);
      break;

    case "error":
      console.error(`\n✗ Error: ${message.error}`);
      break;

    case "system":
      // Log system messages if needed for debugging
      // console.log(`[System: ${message.subtype}]`);
      break;

    default:
      console.log(`[Unknown message type: ${message.type}]`);
  }
});

ws.on("error", (error) => {
  console.error("WebSocket error:", error);
  process.exit(1);
});

ws.on("close", () => {
  console.log("\nConnection closed");
});