import React, { useState } from 'react';
import { SystemMessage as SystemMessageType } from './types';
import { Info, ChevronDown, ChevronRight } from 'lucide-react';

interface SystemMessageProps {
  message: SystemMessageType;
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function SystemMessage({ message }: SystemMessageProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const isInitMessage = message.metadata?.type === 'system' && message.metadata?.subtype === 'init';

  return (
    <div className="mb-4">
      <div className="bg-[var(--bg-tertiary)] border border-[var(--border-default)] max-w-4xl relative overflow-hidden">
        {/* Left accent bar */}
        <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-gradient-to-b from-[var(--accent-warm)] via-[var(--accent-warm)]/50 to-transparent" />

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2 bg-[var(--bg-elevated)] border-b border-[var(--border-subtle)]">
          <div className="flex items-center gap-2">
            <Info size={14} className="text-[var(--accent-warm)]" />
            <span className="text-xs font-mono font-semibold text-[var(--accent-warm)] uppercase tracking-wider">
              System
            </span>
            {isInitMessage && (
              <span className="px-2 py-0.5 text-[10px] bg-[var(--accent-warm)]/10 text-[var(--accent-warm)] font-mono border border-[var(--accent-warm)]/20">
                INIT
              </span>
            )}
          </div>
          <span className="text-xs font-mono text-[var(--text-muted)]">
            {formatTimestamp(message.timestamp)}
          </span>
        </div>

        {/* Content */}
        <div className="p-4 pl-6">
          <div className="text-sm text-[var(--text-primary)] leading-relaxed">
            {message.content}
          </div>
        </div>

        {/* Metadata toggle */}
        {message.metadata && (
          <div className="px-4 py-2 border-t border-[var(--border-subtle)] bg-[var(--bg-elevated)]">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--accent-warm)] flex items-center gap-1 font-mono transition-colors"
            >
              {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              metadata
            </button>

            {isExpanded && (
              <div className="mt-2 p-3 bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-xs">
                <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[var(--text-primary)]">
                  {JSON.stringify(message.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
