import React from 'react';
import { UserMessage as UserMessageType, UserToolResultMessage } from './types';

interface UserMessageProps {
  message: UserMessageType | UserToolResultMessage;
}

export function UserMessage({ message }: UserMessageProps) {
  const isToolResult = 'content' in message && Array.isArray(message.content) &&
    message.content.some(c => typeof c === 'object' && 'tool_use_id' in c);

  if (isToolResult) {
    const toolResultMessage = message as UserToolResultMessage;
    return (
      <div className="mb-4">
        <div className="card p-4">
          <div className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide mb-3">
            Tool Result
          </div>
          <div className="space-y-3">
            {toolResultMessage.content.map((result, index) => (
              <div key={index}>
                <div className="text-xs text-[var(--text-muted)] mb-1">
                  ID: <code className="text-[var(--accent-primary)]">{result.tool_use_id}</code>
                </div>
                <pre className="text-xs bg-[var(--bg-tertiary)] p-3 rounded-[var(--radius-sm)] overflow-x-auto whitespace-pre-wrap text-[var(--text-primary)]">
                  {result.content}
                </pre>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const userMessage = message as UserMessageType;
  return (
    <div className="mb-4 flex justify-end">
      <div className="max-w-[85%] md:max-w-xl">
        <div className="bg-[var(--accent-primary)] text-white px-4 py-3 rounded-[var(--radius-lg)] rounded-br-[var(--radius-sm)] shadow-[var(--shadow-sm)]">
          <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
            {userMessage.content}
          </p>
        </div>
      </div>
    </div>
  );
}
