import React, { useState } from "react";
import { ChatInterface } from "./components/ChatInterface";
import { useWebSocket } from "./hooks/useWebSocket";
import { ScreenshotModeProvider } from "./context/ScreenshotModeContext";
import { Message } from "./components/message/types";
import { DashboardPane } from "./components/dashboard/DashboardPane";

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Single WebSocket connection for all components
  const { isConnected, sendMessage } = useWebSocket({
    url: 'ws://localhost:3000/ws',
    onMessage: (message) => {
      switch (message.type) {
        case 'connected':
          console.log('Connected to server:', message.message);
          break;
        case 'session':
        case 'session_info':
          setSessionId(message.sessionId);
          break;
        case 'assistant_message':
          const assistantMsg: Message = {
            id: Date.now().toString() + '-assistant',
            type: 'assistant',
            content: [{ type: 'text', text: message.content }],
            timestamp: new Date().toISOString(),
          };
          setMessages(prev => [...prev, assistantMsg]);
          setIsLoading(false);
          break;
        case 'tool_use':
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
        case 'result':
          if (message.success) {
            console.log('Query completed successfully', message);
          } else {
            console.error('Query failed:', message.error);
          }
          setIsLoading(false);
          break;
        case 'error':
          console.error('Server error:', message.error);
          const errorMessage: Message = {
            id: Date.now().toString(),
            type: 'assistant',
            content: [{ type: 'text', text: `Error: ${message.error}` }],
            timestamp: new Date().toISOString(),
          };
          setMessages(prev => [...prev, errorMessage]);
          setIsLoading(false);
          break;
      }
    },
  });

  const sendChat = (content: string) => {
    if (!content.trim()) return;
    // mirror ChatInterface submit behavior: add user message and set loading
    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    sendMessage({ type: 'chat', content, sessionId });
  };

  return (
    <ScreenshotModeProvider>
      <div className="h-screen flex flex-col">
        <div className="flex-none" style={{ height: '45%' }}>
          <DashboardPane isConnected={isConnected} isLoading={isLoading} onSend={sendChat} />
        </div>
        <div className="flex-1 min-h-0">
          <ChatInterface
            isConnected={isConnected}
            sendMessage={sendMessage}
            messages={messages}
            setMessages={setMessages}
            sessionId={sessionId}
            isLoading={isLoading}
            setIsLoading={setIsLoading}
          />
        </div>
      </div>
    </ScreenshotModeProvider>
  );
};

export default App;
