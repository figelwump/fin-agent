import React, { useState } from 'react';
import { SystemMessage as SystemMessageType } from './types';

interface SystemMessageProps {
  message: SystemMessageType;
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString();
}

export function SystemMessage({ message }: SystemMessageProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const isInitMessage = message.metadata?.type === 'system' && message.metadata?.subtype === 'init';
  
  return (
    <div className="mb-4 p-4 bg-blue-50/80 backdrop-blur-sm border-l-4 border-blue-400 rounded-r-2xl shadow-md animate-scale-in">
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 bg-blue-500 rounded-full"></span>
          <span className="text-sm font-semibold text-blue-900">System</span>
          {isInitMessage && (
            <span className="px-2 py-0.5 text-xs bg-blue-200 text-blue-800 rounded-full font-medium">
              Initialization
            </span>
          )}
        </div>
        <span className="text-xs text-blue-600">
          {formatTimestamp(message.timestamp)}
        </span>
      </div>

      <div className="text-blue-900 text-sm mb-2 leading-relaxed">
        {message.content}
      </div>
      
      {message.metadata && (
        <div className="mt-3 pt-3 border-t border-blue-300">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs text-blue-700 hover:text-blue-900 flex items-center gap-1 font-medium transition-colors"
          >
            {isExpanded ? '▼' : '▶'} View Metadata
          </button>

          {isExpanded && (
            <div className="mt-2 p-3 bg-white/70 rounded-lg border border-blue-200 text-xs">
              <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-blue-900">
                {JSON.stringify(message.metadata, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}