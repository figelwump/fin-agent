import React from 'react';
import { Upload } from 'lucide-react';

interface ImportStatementsButtonProps {
  onRequestImport: () => void;
  disabled?: boolean;
  isLoading?: boolean;
}

/**
 * Primary entry point for launching the bulk statement import flow from the UI.
 * Actual file/directory selection is layered on later phases; this component
 * just surfaces the control and keeps styling in one place so future logic
 * stays encapsulated.
 */
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
      className="inline-flex items-center gap-2 rounded-sm border border-blue-600 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-blue-600 transition-colors hover:bg-blue-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
    >
      <Upload size={14} />
      {isLoading ? 'Preparing…' : 'Import Statements'}
    </button>
  );
}
