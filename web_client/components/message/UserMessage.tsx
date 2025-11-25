import React from 'react';
import { UserMessage as UserMessageType, UserToolResultMessage } from './types';

interface UserMessageProps {
  message: UserMessageType | UserToolResultMessage;
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString();
}

export function UserMessage({ message }: UserMessageProps) {
  const isToolResult = 'content' in message && Array.isArray(message.content) && 
    message.content.some(c => typeof c === 'object' && 'tool_use_id' in c);

  if (isToolResult) {
    const toolResultMessage = message as UserToolResultMessage;
    return (
      <div className="mb-4 p-4 bg-white border border-gray-200 rounded-2xl shadow-lg">
        <div className="flex justify-between items-start mb-2">
          <div className="flex items-center">
            <span className="text-xs font-semibold text-purple-600 uppercase tracking-wider">Tool Result</span>
          </div>
          <span className="text-xs text-gray-500">
            {formatTimestamp(message.timestamp)}
          </span>
        </div>

        {toolResultMessage.content.map((result, index) => (
          <div key={index} className="mt-2">
            <div className="text-xs text-gray-600 mb-1 font-mono">
              ID: {result.tool_use_id}
            </div>
            <pre className="text-xs bg-gray-50 p-3 border border-gray-200 rounded-lg overflow-x-auto whitespace-pre-wrap font-mono text-gray-900">
              {result.content}
            </pre>
          </div>
        ))}
      </div>
    );
  }

  const userMessage = message as UserMessageType;
  return (
    <div className="mb-4 p-4 bg-white border border-gray-200 rounded-2xl shadow-lg ml-auto max-w-[85%] md:max-w-3xl animate-scale-in">
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center">
          <span className="text-xs font-semibold text-purple-700 uppercase tracking-wider">You</span>
        </div>
        <span className="text-xs text-gray-500">
          {formatTimestamp(message.timestamp)}
        </span>
      </div>

      <div className="text-sm text-gray-900 whitespace-pre-wrap leading-relaxed" style={{ color: '#111827' }}>
        {userMessage.content}
      </div>
    </div>
  );
}