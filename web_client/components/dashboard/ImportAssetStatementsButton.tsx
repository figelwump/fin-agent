import React from 'react';
import { TrendingUp, Loader2 } from 'lucide-react';

interface ImportAssetStatementsButtonProps {
  onRequestImport: () => void;
  disabled?: boolean;
  isLoading?: boolean;
}

export function ImportAssetStatementsButton({
  onRequestImport,
  disabled = false,
  isLoading = false,
}: ImportAssetStatementsButtonProps) {
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
        <TrendingUp size={16} />
      )}
      <span>
        {isLoading ? 'Preparing...' : 'Import asset statements'}
      </span>
    </button>
  );
}
