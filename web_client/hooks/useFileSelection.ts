import { useCallback, useState } from 'react';

export interface SelectedEntry {
  file: File;
  /** Path relative to the selected directory; defaults to file.name for loose files. */
  relativePath: string;
}

interface UseFileSelectionOptions {
  allowedExtensions?: string[];
}

export type SelectionMode = 'auto' | 'files' | 'directory';

interface UseFileSelection {
  selectFiles: (mode?: SelectionMode) => Promise<SelectedEntry[]>;
  isSupported: boolean;
  isSelecting: boolean;
  error: string | null;
  entries: SelectedEntry[];
  reset: () => void;
}

/**
 * Centralises file/directory picking logic. Prefers File System Access API when available,
 * falling back to hidden input elements that support both multi-file and directory uploads.
 */
export function useFileSelection(options: UseFileSelectionOptions = {}): UseFileSelection {
  const { allowedExtensions } = options;
  const [entries, setEntries] = useState<SelectedEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isSelecting, setIsSelecting] = useState(false);

  const normalizeExtension = (ext: string) => (ext.startsWith('.') ? ext.toLowerCase() : `.${ext.toLowerCase()}`);
  const allowed = allowedExtensions?.map(normalizeExtension);

  const validateFile = useCallback((file: File) => {
    if (!allowed?.length) return true;
    const lower = file.name.toLowerCase();
    return allowed.some((ext) => lower.endsWith(ext));
  }, [allowed]);

  const processFiles = useCallback((files: File[]) => {
    const processed: SelectedEntry[] = [];
    for (const file of files) {
      if (!validateFile(file)) continue;
      const relative = (file as any).webkitRelativePath && (file as any).webkitRelativePath.length > 0
        ? (file as any).webkitRelativePath
        : file.name;
      processed.push({ file, relativePath: relative });
    }
    return processed;
  }, [validateFile]);

  const syncState = useCallback((processed: SelectedEntry[], originalCount: number) => {
    setEntries(processed);
    if (originalCount && processed.length === 0) {
      setError('No files matched the allowed extensions.');
    } else if (allowed?.length && processed.length !== originalCount) {
      setError('Some files were skipped because they do not match the allowed extensions.');
    } else {
      setError(null);
    }
    return processed;
  }, [allowed]);

  const selectViaInput = useCallback((mode: Exclude<SelectionMode, 'auto'>) => {
    return new Promise<SelectedEntry[]>((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.multiple = mode === 'files';
      input.accept = allowed?.join(',') ?? '';
      if (mode === 'directory') {
        (input as any).webkitdirectory = true;
      }
      input.style.display = 'none';
      document.body.appendChild(input);

      const handleChange = () => {
        let processed: SelectedEntry[] = [];
        if (input.files) {
          const fileList = Array.from(input.files);
          processed = syncState(processFiles(fileList), fileList.length);
        } else {
          syncState([], 0);
        }
        input.removeEventListener('change', handleChange);
        if (input.parentNode) input.parentNode.removeChild(input);
        resolve(processed);
      };

      input.addEventListener('change', handleChange);
      input.click();
    });
  }, [allowed, processFiles, syncState]);

  const pickWithDirectoryHandle = useCallback(async () => {
    const anyWindow = window as any;
    if (typeof anyWindow.showDirectoryPicker !== 'function') {
      return await selectViaInput('directory');
    }

    try {
      const dirHandle: FileSystemDirectoryHandle = await anyWindow.showDirectoryPicker();
      const collected: SelectedEntry[] = [];

      const traverse = async (handle: FileSystemDirectoryHandle, prefix = '') => {
        const iterator = (handle as any).entries?.call(handle) as AsyncIterable<[string, FileSystemHandle]> | undefined;
        if (!iterator) return;
        for await (const [entryName, entry] of iterator) {
          if (entry.kind === 'file') {
            const fileHandle = entry as FileSystemFileHandle;
            const file = await fileHandle.getFile();
            if (!validateFile(file)) continue;
            collected.push({ file, relativePath: `${prefix}${entryName}` });
          } else if (entry.kind === 'directory') {
            await traverse(entry as FileSystemDirectoryHandle, `${prefix}${entryName}/`);
          }
        }
      };

      await traverse(dirHandle);
      return syncState(collected, collected.length);
    } catch (err) {
      if ((err as DOMException)?.name === 'AbortError') {
        return [];
      }
      console.error('Directory selection error', err);
      setError('Unable to access the selected directory.');
      return [];
    }
  }, [selectViaInput, syncState, validateFile]);

  const pickWithFilePicker = useCallback(async () => {
    const anyWindow = window as any;
    if (typeof anyWindow.showOpenFilePicker !== 'function') {
      return await selectViaInput('files');
    }

    try {
      const accept: Record<string, string[]> = {};
      if (allowed?.includes('.pdf')) accept['application/pdf'] = ['.pdf'];
      if (allowed?.includes('.csv')) accept['text/csv'] = ['.csv'];

      const handles: FileSystemFileHandle[] = await anyWindow.showOpenFilePicker({
        multiple: true,
        types: allowed?.length
          ? [{ description: 'Statements', accept }]
          : undefined,
        excludeAcceptAllOption: !!allowed?.length,
      });

      const files = await Promise.all(handles.map((handle) => handle.getFile()));
      return syncState(processFiles(files), files.length);
    } catch (err) {
      if ((err as DOMException)?.name === 'AbortError') {
        return [];
      }
      console.error('File selection error', err);
      setError('Unable to access selected files. Please try again.');
      return [];
    }
  }, [allowed, processFiles, selectViaInput, syncState]);

  const selectFiles = useCallback(async (mode: SelectionMode = 'auto') => {
    setIsSelecting(true);
    try {
      if (typeof window === 'undefined') return [];

      const anyWindow = window as any;
      const hasFilePicker = typeof anyWindow.showOpenFilePicker === 'function';
      const hasDirectoryPicker = typeof anyWindow.showDirectoryPicker === 'function';

      const resolvedMode: SelectionMode = mode === 'auto'
        ? hasFilePicker
          ? 'files'
          : hasDirectoryPicker
            ? 'directory'
            : 'files'
        : mode;

      if (resolvedMode === 'directory') {
        if (hasDirectoryPicker) {
          return await pickWithDirectoryHandle();
        }
        return await selectViaInput('directory');
      }

      if (hasFilePicker) {
        return await pickWithFilePicker();
      }
      return await selectViaInput('files');
    } finally {
      setIsSelecting(false);
    }
  }, [pickWithDirectoryHandle, pickWithFilePicker, selectViaInput]);

  const reset = useCallback(() => {
    setEntries([]);
    setError(null);
  }, []);

  const supports = typeof window !== 'undefined';

  return {
    selectFiles,
    isSupported: supports,
    isSelecting,
    error,
    entries,
    reset,
  };
}
