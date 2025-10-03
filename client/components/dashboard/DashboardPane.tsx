import React from 'react';
import { SuggestedQueries } from './SuggestedQueries';

interface DashboardPaneProps {
  isConnected: boolean;
  isLoading: boolean;
  onSend: (prompt: string) => void;
}

export function DashboardPane({ isConnected, isLoading, onSend }: DashboardPaneProps) {
  return (
    <div className="h-full overflow-y-auto p-3 bg-gray-50 border-b border-gray-200">
      <div className="max-w-5xl mx-auto space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold uppercase tracking-wider">Dashboard</h2>
          <div className="text-xs text-gray-500">{isConnected ? 'Connected' : 'Offline'}</div>
        </div>

        <SuggestedQueries
          onSend={(prompt) => onSend(prompt)}
          disabled={!isConnected || isLoading}
        />

        {/* Placeholder for future pinned widgets grid (Phase 4) */}
        <div className="text-xs text-gray-500">Pin your favorite analyses here (coming soon).</div>
      </div>
    </div>
  );
}

