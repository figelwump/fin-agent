import React, { useState, useRef, useEffect } from 'react';
import { MessageRenderer } from './message/MessageRenderer';
import { Message } from './message/types';
import { Send, Wifi, WifiOff, RefreshCw, Mail, Clock } from 'lucide-react';

interface ChatInterfaceProps {
  isConnected: boolean;
  sendMessage: (message: any) => void;
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  sessionId: string | null;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
}

export function ChatInterface({ isConnected, sendMessage, messages, setMessages, sessionId, isLoading, setIsLoading }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading || !isConnected) return;
    
    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date().toISOString(),
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    
    // Send message through WebSocket
    sendMessage({
      type: 'chat',
      content: inputValue,
      sessionId,
    });
  };
  
  return (
    <div className="flex flex-col h-full bg-white">
      <div className="flex-1 overflow-y-auto p-3">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-3 pb-3 border-b border-gray-200">
            <h1 className="text-lg font-semibold uppercase tracking-wider">Fin Agent</h1>
          </div>
          
          {messages.length === 0 ? (
            <div className="text-center text-gray-400 mt-12">
              <p className="text-sm uppercase tracking-wider">Start a conversation</p>
              <p className="mt-2 text-xs">"Show me top spending categories" • "Find all my Amazon purchases" • "What are my subscriptions?"</p>
            </div>
          ) : (
            <div className="space-y-2">
              {messages.map((msg) => (
                <MessageRenderer key={msg.id} message={msg} />
              ))}
              {isLoading && (
                <MessageRenderer 
                  message={{
                    id: 'loading',
                    type: 'assistant',
                    content: [{ type: 'text', text: 'Processing...' }],
                    timestamp: new Date().toISOString(),
                  }}
                />
              )}
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
      </div>
      
      <div className="border-t border-gray-200 bg-white p-3">
        <form onSubmit={handleSubmit} className="max-w-5xl mx-auto">
          <div className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={isConnected ? "Ask about your finances..." : "Waiting for connection..."}
              className="flex-1 px-3 py-2 text-sm border border-gray-300 focus:border-gray-900 focus:outline-none"
              disabled={isLoading || !isConnected}
            />
            <button
              type="submit"
              disabled={isLoading || !inputValue.trim() || !isConnected}
              className="px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-gray-900 text-white hover:bg-white hover:text-gray-900 border border-gray-900 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
            >
              <Send size={14} />
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
