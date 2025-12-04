import React from 'react';
import { Upload, Loader2 } from 'lucide-react';

interface ImportStatementsButtonProps {
  onRequestImport: () => void;
  disabled?: boolean;
  isLoading?: boolean;
}

export function ImportStatementsButton({
  onRequestImport,
  disabled = false,
  isLoading = false,
}: ImportStatementsButtonProps) {
  return (
    <button
      type="button"
      onClick={onRequestImport}
      disabled={disabled || isLoading}
      className="btn-secondary inline-flex items-center gap-2 px-4 py-2.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {isLoading ? (
        <Loader2 size={16} className="animate-spin" />
      ) : (
        <Upload size={16} />
      )}
      <span>
        {isLoading ? 'Preparing...' : 'Import statements'}
      </span>
    </button>
  );
}
