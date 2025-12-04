import React, { useState, useRef } from "react";
import { ChatInterface } from "./components/ChatInterface";
import { useWebSocket } from "./hooks/useWebSocket";
import { ScreenshotModeProvider } from "./context/ScreenshotModeContext";
import { Message } from "./components/message/types";

type Credentials = { password: string };
const CREDENTIALS_STORAGE_KEY = 'finagent:auth';

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [passwordInput, setPasswordInput] = useState('');
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [hasEverConnected, setHasEverConnected] = useState(false);
  const streamingMessageIdRef = useRef<string | null>(null);

  // Build WebSocket URL from current location
  const wsUrl = typeof window !== 'undefined'
    ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`
    : 'ws://localhost:3000/ws';

  // Single WebSocket connection for all components
  const { isConnected, sendMessage } = useWebSocket({
    url: wsUrl,
    enabled: Boolean(credentials),
    maxReconnectAttempts: 5,
    onMessage: (message) => {
      switch (message.type) {
        case 'auth_required': {
          // Server requires authentication - send password
          if (credentials) {
            console.log('Sending auth message');
            sendMessage({ type: 'auth', password: credentials.password });
          }
          break;
        }
        case 'connected': {
          console.log('Connected to server:', message.message);
          setConnectionError(null);
          setHasEverConnected(true);
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
        case 'auth_failed': {
          // Auth failed - clear credentials and show login
          console.error('Authentication failed:', message.error);
          if (typeof window !== 'undefined') {
            window.localStorage.removeItem(CREDENTIALS_STORAGE_KEY);
          }
          setCredentials(null);
          setPasswordInput('');
          setConnectionError(message.error || 'Authentication failed');
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
    onError: (evt) => {
      const msg = 'Connection error. Check your password or try again.';
      console.error(msg, evt);
      setConnectionError(msg);
      if (!hasEverConnected) {
        if (typeof window !== 'undefined') {
          window.localStorage.removeItem(CREDENTIALS_STORAGE_KEY);
        }
        setCredentials(null);
        setPasswordInput('');
      }
    },
    onDisconnect: () => {
      if (!credentials) return;
      setConnectionError('Connection lost. Retrying...');
    }
  });

  // Load saved credentials on mount
  React.useEffect(() => {
    if (typeof window === 'undefined') return;
    const saved = window.localStorage.getItem(CREDENTIALS_STORAGE_KEY);
    if (saved) {
      try {
        const parsed: Credentials = JSON.parse(saved);
        setCredentials(parsed);
        setPasswordInput(parsed.password);
      } catch (err) {
        console.error('Failed to parse saved credentials', err);
        window.localStorage.removeItem(CREDENTIALS_STORAGE_KEY);
      }
    }
  }, []);

  const handleCredentialsSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const password = passwordInput.trim();
    if (!password) return;
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(CREDENTIALS_STORAGE_KEY, JSON.stringify({ password } satisfies Credentials));
    }
    setCredentials({ password });
    setConnectionError(null);
  };

  const handleResetCredentials = () => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(CREDENTIALS_STORAGE_KEY);
    }
    setCredentials(null);
    setPasswordInput('');
    setConnectionError(null);
    setMessages([]);
    setSessionId(null);
  };

  // Show login screen if no credentials
  if (!credentials) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--color-bg-primary)]">
        <div className="max-w-md w-full mx-4 p-6 rounded-lg border border-[var(--color-border-primary)] bg-[var(--color-bg-secondary)]">
          <h1 className="text-xl font-semibold mb-3 text-[var(--color-text-primary)]">
            Access Required
          </h1>
          <p className="text-sm mb-4 text-[var(--color-text-secondary)]">
            Enter the password to connect.
          </p>
          {connectionError && (
            <div className="mb-4 p-3 rounded bg-red-500/10 border border-red-500/30">
              <p className="text-sm text-red-400">
                {connectionError}
              </p>
            </div>
          )}
          <form onSubmit={handleCredentialsSubmit} className="space-y-3">
            <input
              type="password"
              value={passwordInput}
              onChange={(e) => setPasswordInput(e.target.value)}
              placeholder="Password"
              className="w-full px-3 py-2 rounded border border-[var(--color-border-primary)] bg-[var(--color-bg-primary)] text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              autoFocus
            />
            <button
              type="submit"
              className="w-full px-4 py-2 rounded bg-[var(--color-accent)] text-white font-medium hover:opacity-90 transition-opacity"
            >
              Continue
            </button>
          </form>
        </div>
      </div>
    );
  }

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
        onResetAuth={handleResetCredentials}
        connectionError={connectionError}
      />
    </ScreenshotModeProvider>
  );
};

export default App;
