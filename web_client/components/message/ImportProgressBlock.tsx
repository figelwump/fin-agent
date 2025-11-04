import React from 'react';
import type { ImportProgressBlock } from './types';

const stageLabels: Record<ImportProgressBlock['data']['stage'], string> = {
  uploading: 'Uploading statements…',
  processing: 'Processing statements…',
  completed: 'Bulk import complete.',
  error: 'Bulk import failed.',
};

export function ImportProgressBlockRenderer({ block }: { block: ImportProgressBlock }) {
  const { stage, message, files } = block.data;
  const isSpinning = stage === 'uploading' || stage === 'processing';
  const isError = stage === 'error';

  return (
    <div className={`flex items-start gap-3 rounded-sm border px-3 py-2 text-sm ${
      isError ? 'border-red-200 bg-red-50 text-red-800' : 'border-gray-200 bg-gray-50 text-gray-800'
    }`}>
      <div className="mt-1">
        {isSpinning ? (
          <span className="block h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
        ) : stage === 'completed' ? (
          <span className="text-green-600">✓</span>
        ) : (
          <span className="text-red-600">!</span>
        )}
      </div>
      <div className="space-y-1">
        <div className="font-semibold uppercase tracking-wider text-xs text-gray-600">
          {stageLabels[stage]}
        </div>
        <div className="text-sm whitespace-pre-line">{message}</div>
        {files.length > 0 && (
          <div className="text-xs text-gray-600">
            Files: {files.join(', ')}
          </div>
        )}
      </div>
    </div>
  );
}
