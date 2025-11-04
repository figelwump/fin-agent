import React, { useState, useRef } from "react";
import { ChatInterface } from "./components/ChatInterface";
import { useWebSocket } from "./hooks/useWebSocket";
import { ScreenshotModeProvider } from "./context/ScreenshotModeContext";
import { Message } from "./components/message/types";

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const streamingMessageIdRef = useRef<string | null>(null);

  // Single WebSocket connection for all components
  const { isConnected, sendMessage } = useWebSocket({
    url: 'ws://localhost:3000/ws',
    onMessage: (message) => {
      switch (message.type) {
        case 'connected': {
          console.log('Connected to server:', message.message);
          break;
        }
        case 'session':
        case 'session_info': {
          setSessionId(message.sessionId);
          break;
        }
        case 'assistant_partial': {
          const partialText = typeof message.content === 'string' ? message.content : '';
          const timestamp = new Date().toISOString();
          const existingId = streamingMessageIdRef.current;
          const streamingId = existingId ?? `${Date.now()}-assistant-partial`;

          if (!existingId) {
            streamingMessageIdRef.current = streamingId;
          }

          setMessages(prev => {
            let found = false;
            const next = prev.map(msg => {
              if (msg.id !== streamingId || msg.type !== 'assistant') {
                return msg;
              }
              found = true;
              return {
                ...msg,
                content: [{ type: 'text', text: partialText }],
                timestamp,
                metadata: { ...(msg.metadata ?? {}), streaming: true },
              };
            });

            if (found) {
              return next;
            }

            const partialMessage: Message = {
              id: streamingId,
              type: 'assistant',
              content: [{ type: 'text', text: partialText }],
              timestamp,
              metadata: { streaming: true },
            };

            return [...prev, partialMessage];
          });

          setIsLoading(true);
          break;
        }
        case 'assistant_message': {
          const text = typeof message.content === 'string' ? message.content : '';
          const timestamp = new Date().toISOString();
          const streamingId = streamingMessageIdRef.current;

          setMessages(prev => {
            if (streamingId) {
              let updated = false;
              const next = prev.map(msg => {
                if (msg.id !== streamingId || msg.type !== 'assistant') {
                  return msg;
                }
                updated = true;
                const baseMetadata = { ...(msg.metadata ?? {}) };
                delete baseMetadata.streaming;
                const metadata = Object.keys(baseMetadata).length > 0 ? baseMetadata : undefined;
                return {
                  ...msg,
                  content: [{ type: 'text', text }],
                  timestamp,
                  metadata,
                };
              });

              if (updated) {
                streamingMessageIdRef.current = null;
                return next;
              }
            }

            const assistantMsg: Message = {
              id: Date.now().toString() + '-assistant',
              type: 'assistant',
              content: [{ type: 'text', text }],
              timestamp,
            };

            streamingMessageIdRef.current = null;
            return [...prev, assistantMsg];
          });

          setIsLoading(false);
          break;
        }
        case 'tool_use': {
          const toolMsg: Message = {
            id: Date.now().toString() + '-tool',
            type: 'assistant',
            content: [{
              type: 'tool_use',
              id: message.toolId || Date.now().toString(),
              name: message.toolName,
              input: message.toolInput || {}
            }],
            timestamp: new Date().toISOString(),
          };
          setMessages(prev => [...prev, toolMsg]);
          break;
        }
        case 'result': {
          if (message.success) {
            console.log('Query completed successfully', message);
          } else {
            console.error('Query failed:', message.error);
          }
          streamingMessageIdRef.current = null;
          setIsLoading(false);
          break;
        }
        case 'error': {
          console.error('Server error:', message.error);
          const errorMessage: Message = {
            id: Date.now().toString(),
            type: 'assistant',
            content: [{ type: 'text', text: `Error: ${message.error}` }],
            timestamp: new Date().toISOString(),
          };
          setMessages(prev => [...prev, errorMessage]);
          streamingMessageIdRef.current = null;
          setIsLoading(false);
          break;
        }
      }
    },
  });

  return (
    <ScreenshotModeProvider>
      <ChatInterface
        isConnected={isConnected}
        sendMessage={sendMessage}
        messages={messages}
        setMessages={setMessages}
        sessionId={sessionId}
        isLoading={isLoading}
        setIsLoading={setIsLoading}
      />
    </ScreenshotModeProvider>
  );
};

export default App;
