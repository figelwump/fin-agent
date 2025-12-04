import React, { useState } from 'react';
import { SystemMessage as SystemMessageType } from './types';
import { Info, ChevronDown, ChevronRight } from 'lucide-react';

interface SystemMessageProps {
  message: SystemMessageType;
}

export function SystemMessage({ message }: SystemMessageProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="mb-4">
      <div className="card p-4 max-w-2xl border-l-4 border-l-[var(--accent-warm)]">
        <div className="flex items-start gap-3">
          <Info size={18} className="text-[var(--accent-warm)] flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="text-sm text-[var(--text-primary)] leading-relaxed">
              {message.content}
            </div>

            {message.metadata && (
              <div className="mt-3">
                <button
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] flex items-center gap-1 transition-colors"
                >
                  {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  Details
                </button>

                {isExpanded && (
                  <div className="mt-2 p-3 bg-[var(--bg-tertiary)] rounded-[var(--radius-sm)] text-xs">
                    <pre className="overflow-x-auto whitespace-pre-wrap text-[var(--text-secondary)]">
                      {JSON.stringify(message.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
