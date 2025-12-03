import React from 'react';
import { UserMessage as UserMessageType, UserToolResultMessage } from './types';
import { User, Terminal } from 'lucide-react';

interface UserMessageProps {
  message: UserMessageType | UserToolResultMessage;
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function UserMessage({ message }: UserMessageProps) {
  const isToolResult = 'content' in message && Array.isArray(message.content) &&
    message.content.some(c => typeof c === 'object' && 'tool_use_id' in c);

  if (isToolResult) {
    const toolResultMessage = message as UserToolResultMessage;
    return (
      <div className="mb-4">
        <div className="bg-[var(--bg-tertiary)] border border-[var(--border-default)] overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2 bg-[var(--bg-elevated)] border-b border-[var(--border-subtle)]">
            <div className="flex items-center gap-2">
              <Terminal size={14} className="text-[var(--accent-warm)]" />
              <span className="text-xs font-mono font-semibold text-[var(--accent-warm)] uppercase tracking-wider">
                Tool Result
              </span>
            </div>
            <span className="text-xs font-mono text-[var(--text-muted)]">
              {formatTimestamp(message.timestamp)}
            </span>
          </div>

          {/* Results */}
          <div className="p-4 space-y-3">
            {toolResultMessage.content.map((result, index) => (
              <div key={index}>
                <div className="text-xs text-[var(--text-muted)] mb-2 font-mono flex items-center gap-2">
                  <span className="text-[var(--accent-primary)]">ID:</span>
                  <code className="text-[var(--text-secondary)]">{result.tool_use_id}</code>
                </div>
                <pre className="text-xs bg-[var(--bg-primary)] p-3 border border-[var(--border-subtle)] overflow-x-auto whitespace-pre-wrap font-mono text-[var(--text-primary)]">
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
      <div className="max-w-[85%] md:max-w-2xl">
        {/* User message bubble */}
        <div className="bg-gradient-to-r from-[var(--accent-primary)]/10 to-[var(--accent-secondary)]/10 border border-[var(--accent-primary)]/20 relative">
          {/* Top accent line */}
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)]" />

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border-subtle)]">
            <div className="flex items-center gap-2">
              <div className="w-5 h-5 rounded bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] flex items-center justify-center">
                <User size={12} className="text-[var(--bg-primary)]" />
              </div>
              <span className="text-xs font-mono font-semibold text-[var(--accent-primary)] uppercase tracking-wider">
                Query
              </span>
            </div>
            <span className="text-xs font-mono text-[var(--text-muted)]">
              {formatTimestamp(message.timestamp)}
            </span>
          </div>

          {/* Content */}
          <div className="px-4 py-3">
            <div className="text-sm text-[var(--text-primary)] whitespace-pre-wrap leading-relaxed">
              {userMessage.content}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
