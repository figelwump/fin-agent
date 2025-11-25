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
      className="inline-flex items-center gap-2 rounded-full border-2 border-white/80 px-5 py-2.5 text-sm font-semibold text-white transition-all hover:bg-white hover:text-purple-600 hover:shadow-lg hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40"
    >
      <Upload size={16} />
      {isLoading ? 'Preparing…' : 'Import Statements'}
    </button>
  );
}
