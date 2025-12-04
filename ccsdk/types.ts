import type { ServerWebSocket } from "bun";
import type { SDKUserMessage, SDKMessage } from "@anthropic-ai/claude-code";

// WebSocket client data type
export interface WSData {
  sessionId: string;
  authenticated: boolean;
}

// WebSocket client type
export type WSClient = ServerWebSocket<WSData>;

// Message types for WebSocket communication
export interface AuthMessage {
  type: "auth";
  password: string;
}

export interface ChatMessage {
  type: "chat";
  content: string;
  sessionId?: string;
  newConversation?: boolean;
}

export interface SubscribeMessage {
  type: "subscribe";
  sessionId: string;
}

export interface UnsubscribeMessage {
  type: "unsubscribe";
  sessionId: string;
}

export type IncomingMessage = AuthMessage | ChatMessage | SubscribeMessage | UnsubscribeMessage;

// Re-export SDK types for convenience
export type { SDKUserMessage, SDKMessage };
