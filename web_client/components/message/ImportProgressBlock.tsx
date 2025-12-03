import React from 'react';
import type { ImportProgressBlock } from './types';
import { Loader2, CheckCircle, AlertCircle } from 'lucide-react';

const stageLabels: Record<ImportProgressBlock['data']['stage'], string> = {
  uploading: 'UPLOADING STATEMENTS',
  processing: 'PROCESSING STATEMENTS',
  completed: 'IMPORT COMPLETE',
  error: 'IMPORT FAILED',
};

export function ImportProgressBlockRenderer({ block }: { block: ImportProgressBlock }) {
  const { stage, message, files } = block.data;
  const isSpinning = stage === 'uploading' || stage === 'processing';
  const isError = stage === 'error';
  const isComplete = stage === 'completed';

  return (
    <div className={`flex items-start gap-3 border px-4 py-3 text-sm ${
      isError
        ? 'border-[var(--accent-danger)]/30 bg-[var(--accent-danger)]/5'
        : isComplete
        ? 'border-[var(--accent-secondary)]/30 bg-[var(--accent-secondary)]/5'
        : 'border-[var(--border-default)] bg-[var(--bg-tertiary)]'
    }`}>
      <div className="mt-0.5">
        {isSpinning ? (
          <Loader2 size={16} className="text-[var(--accent-primary)] animate-spin" />
        ) : isComplete ? (
          <CheckCircle size={16} className="text-[var(--accent-secondary)]" />
        ) : (
          <AlertCircle size={16} className="text-[var(--accent-danger)]" />
        )}
      </div>
      <div className="space-y-1 flex-1">
        <div className={`font-mono font-semibold text-xs uppercase tracking-wider ${
          isError
            ? 'text-[var(--accent-danger)]'
            : isComplete
            ? 'text-[var(--accent-secondary)]'
            : 'text-[var(--accent-primary)]'
        }`}>
          {stageLabels[stage]}
        </div>
        <div className="text-sm text-[var(--text-primary)] whitespace-pre-line">{message}</div>
        {files.length > 0 && (
          <div className="text-xs text-[var(--text-muted)] font-mono">
            FILES: {files.join(', ')}
          </div>
        )}
      </div>
    </div>
  );
}
