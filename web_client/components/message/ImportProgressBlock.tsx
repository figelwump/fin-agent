import React from 'react';
import type { ImportProgressBlock } from './types';
import { Loader2, CheckCircle, AlertCircle } from 'lucide-react';

const stageLabels: Record<ImportProgressBlock['data']['stage'], string> = {
  uploading: 'Uploading statements...',
  processing: 'Processing statements...',
  completed: 'Import complete',
  error: 'Import failed',
};

export function ImportProgressBlockRenderer({ block }: { block: ImportProgressBlock }) {
  const { stage, message, files } = block.data;
  const isSpinning = stage === 'uploading' || stage === 'processing';
  const isError = stage === 'error';
  const isComplete = stage === 'completed';

  return (
    <div className={`card flex items-start gap-3 p-4 ${
      isError
        ? 'border-l-4 border-l-[var(--accent-danger)] bg-red-50'
        : isComplete
        ? 'border-l-4 border-l-[#4a7c59] bg-green-50'
        : ''
    }`}>
      <div className="mt-0.5">
        {isSpinning ? (
          <Loader2 size={18} className="text-[var(--accent-primary)] animate-spin" />
        ) : isComplete ? (
          <CheckCircle size={18} className="text-[#4a7c59]" />
        ) : (
          <AlertCircle size={18} className="text-[var(--accent-danger)]" />
        )}
      </div>
      <div className="flex-1">
        <div className={`font-medium text-sm ${
          isError
            ? 'text-[var(--accent-danger)]'
            : isComplete
            ? 'text-[#4a7c59]'
            : 'text-[var(--text-primary)]'
        }`}>
          {stageLabels[stage]}
        </div>
        {message && (
          <div className="text-sm text-[var(--text-secondary)] mt-1 whitespace-pre-line">
            {message}
          </div>
        )}
        {files.length > 0 && (
          <div className="text-xs text-[var(--text-muted)] mt-2">
            Files: {files.join(', ')}
          </div>
        )}
      </div>
    </div>
  );
}
