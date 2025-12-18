import React, { useState, useRef, useEffect, useMemo } from 'react';
import { MessageRenderer } from './message/MessageRenderer';
import { Message, StructuredPrompt } from './message/types';
import { Send, Wallet } from 'lucide-react';
import { SuggestedQueries } from './dashboard/SuggestedQueries';
import { ImportStatementsButton } from './dashboard/ImportStatementsButton';
import { ImportAssetStatementsButton } from './dashboard/ImportAssetStatementsButton';
import { useFileSelection, SelectionMode, SelectedEntry } from '../hooks/useFileSelection';

interface ChatInterfaceProps {
  isConnected: boolean;
  sendMessage: (message: any) => void;
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  sessionId: string | null;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  onResetAuth?: () => void;
  connectionError?: string | null;
}

type ResolvedStatementPath = {
  path: string;
  label: string;
  source: 'absolute' | 'staged';
};

export function ChatInterface({ isConnected, sendMessage, messages, setMessages, sessionId, isLoading, setIsLoading, onResetAuth, connectionError }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [isImportingAssets, setIsImportingAssets] = useState(false);
  const [showPickerMenu, setShowPickerMenu] = useState(false);
  const [showAssetPickerMenu, setShowAssetPickerMenu] = useState(false);
  const [activeImportMode, setActiveImportMode] = useState<'statements' | 'assets' | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pickerAnchorRef = useRef<HTMLDivElement>(null);
  const assetPickerAnchorRef = useRef<HTMLDivElement>(null);
  const {
    selectFiles,
    error: selectionError,
    isSelecting,
    reset: resetSelection,
  } = useFileSelection({ allowedExtensions: ['.pdf', '.csv'] });

  const canPickDirectories = typeof window !== 'undefined' && (() => {
    if (typeof (window as any).showDirectoryPicker === 'function') return true;
    const input = document.createElement('input');
    return 'webkitdirectory' in input;
  })();

  const canPickFiles = typeof window !== 'undefined';

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const dispatchPrompt = (prompt: StructuredPrompt) => {
    const { displayText, agentText, metadata } = prompt;
    const timestamp = new Date().toISOString();
    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: displayText,
      timestamp,
    };

    const mergedMetadata: Record<string, unknown> = metadata ? { ...metadata } : {};
    if (!('agentText' in mergedMetadata) || mergedMetadata.agentText !== agentText) {
      mergedMetadata.agentText = agentText;
    }

    if (Object.keys(mergedMetadata).length > 0) {
      userMessage.metadata = mergedMetadata;
    }

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);
    sendMessage({ type: 'chat', content: agentText, sessionId });
  };

  const sendSuggestedPrompt = (prompt: StructuredPrompt | string) => {
    if (isLoading || !isConnected) return;

    const structured: StructuredPrompt = typeof prompt === 'string'
      ? { displayText: prompt, agentText: prompt }
      : prompt;

    if (!structured.displayText.trim() || !structured.agentText.trim()) {
      return;
    }

    dispatchPrompt({ ...structured });
  };

  const appendAssistantText = (text: string) => {
    const message: Message = {
      id: Date.now().toString(),
      type: 'assistant',
      content: [{ type: 'text', text }],
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, message]);
  };

  const isAbsolutePathValue = (value: string | undefined): boolean => {
    if (!value) return false;
    return value.startsWith('/') || /^[A-Za-z]:[\\/]/.test(value);
  };

  const collectAbsolutePaths = (entries: SelectedEntry[]): ResolvedStatementPath[] | null => {
    const resolved: ResolvedStatementPath[] = [];
    entries.forEach((entry, index) => {
      const absoluteCandidate = entry.absolutePath && isAbsolutePathValue(entry.absolutePath)
        ? entry.absolutePath.trim()
        : null;
      if (!absoluteCandidate) {
        return;
      }
      const label = entry.relativePath ?? entry.file.name ?? `statement-${index + 1}`;
      resolved.push({ path: absoluteCandidate, label, source: 'absolute' });
    });

    return resolved.length === entries.length && resolved.length > 0 ? resolved : null;
  };

  const stageEntriesRemotely = async (entries: SelectedEntry[]) => {
    const formData = new FormData();
    entries.forEach((entry, index) => {
      const label = entry.relativePath ?? entry.file.name ?? `statement-${index + 1}`;
      formData.append('files', entry.file, label);
    });

    const response = await fetch('/api/import/stage', {
      method: 'POST',
      body: formData,
    });
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Server is missing the /api/import/stage endpoint. Restart `bun run server/server.ts` with the latest code and try again.');
      }

      const message = typeof payload?.error === 'string'
        ? payload.error
        : `Failed to stage selected files (HTTP ${response.status}). Check server logs.`;
      throw new Error(message);
    }

    const storedPaths: string[] = Array.isArray(payload?.storedPaths) ? payload.storedPaths : [];
    if (!storedPaths.length) {
      throw new Error('The server did not return any staged file paths.');
    }

    const resolved = storedPaths.map((path, index) => ({
      path,
      label: entries[index]?.relativePath ?? entries[index]?.file.name ?? path,
      source: 'staged' as const,
    }));

    return {
      resolved,
      stagingDir: typeof payload?.stagingDir === 'string' ? payload.stagingDir : null,
      skipped: Array.isArray(payload?.skipped) ? payload.skipped : [],
    };
  };

  const sendStatementProcessorRequest = (
    paths: ResolvedStatementPath[],
    options?: { staged?: boolean; stagingDir?: string | null }
  ) => {
    if (!paths.length) {
      appendAssistantText('No usable filesystem paths were provided.');
      return;
    }

    const displayLines = paths.map((entry) => {
      const suffix = entry.source === 'staged' ? ' (staged copy)' : '';
      return `• ${entry.path}${suffix}`;
    });
    const displayText = paths.length === 1
      ? `Import statement: ${paths[0].path}${paths[0].source === 'staged' ? ' (staged copy)' : ''}`
      : `Import statements:\n${displayLines.join('\n')}`;

    const numberedLines = paths.map((entry, index) => {
      const suffix = entry.source === 'staged' ? ' (staged copy)' : '';
      return `${index + 1}. ${entry.path}${suffix}`;
    });

    const agentLines = [
      'Please invoke the statement-processor skill to import the following statements.',
      'Use the provided filesystem paths directly; the files already exist on this machine.',
      ...numberedLines,
    ];

    if (options?.staged && options.stagingDir) {
      agentLines.push(`The files above were staged under ${options.stagingDir}.`);
    }

    dispatchPrompt({
      displayText,
      agentText: agentLines.join('\n'),
      metadata: {
        intent: 'statement_import',
        fileCount: paths.length,
        files: paths.map((entry) => entry.path),
        staged: !!options?.staged,
        stagingDir: options?.stagingDir ?? undefined,
      },
    });
  };

  const sendAssetTrackerRequest = (
    paths: ResolvedStatementPath[],
    options?: { staged?: boolean; stagingDir?: string | null }
  ) => {
    if (!paths.length) {
      appendAssistantText('No usable filesystem paths were provided.');
      return;
    }

    const displayLines = paths.map((entry) => {
      const suffix = entry.source === 'staged' ? ' (staged copy)' : '';
      return `• ${entry.path}${suffix}`;
    });
    const displayText = paths.length === 1
      ? `Import asset statement: ${paths[0].path}${paths[0].source === 'staged' ? ' (staged copy)' : ''}`
      : `Import asset statements:\n${displayLines.join('\n')}`;

    const numberedLines = paths.map((entry, index) => {
      const suffix = entry.source === 'staged' ? ' (staged copy)' : '';
      return `${index + 1}. ${entry.path}${suffix}`;
    });

    const agentLines = [
      'Please invoke the asset-tracker skill to import the following investment/brokerage statements.',
      'Use the provided filesystem paths directly; the files already exist on this machine.',
      ...numberedLines,
    ];

    if (options?.staged && options.stagingDir) {
      agentLines.push(`The files above were staged under ${options.stagingDir}.`);
    }

    dispatchPrompt({
      displayText,
      agentText: agentLines.join('\n'),
      metadata: {
        intent: 'asset_import',
        fileCount: paths.length,
        files: paths.map((entry) => entry.path),
        staged: !!options?.staged,
        stagingDir: options?.stagingDir ?? undefined,
      },
    });
  };

  const runSelection = async (mode: SelectionMode) => {
    setShowPickerMenu(false);
    if (isImporting || isSelecting) return;
    setIsImporting(true);
    setActiveImportMode('statements');
    try {
      const entries = await selectFiles(mode);
      if (!entries.length) {
        return;
      }

      const absolutePaths = collectAbsolutePaths(entries);
      if (absolutePaths) {
        sendStatementProcessorRequest(absolutePaths);
        return;
      }

      appendAssistantText('Staging selected files so the statement-processor can access them…');
      const staged = await stageEntriesRemotely(entries);
      if (staged.skipped.length) {
        appendAssistantText(`Some uploads were skipped: ${staged.skipped.join(', ')}`);
      }
      sendStatementProcessorRequest(staged.resolved, { staged: true, stagingDir: staged.stagingDir });
    } catch (error: any) {
      const detail = error?.message ?? 'Failed to prepare selected files.';
      appendAssistantText(detail);
    } finally {
      resetSelection();
      setIsImporting(false);
      setActiveImportMode(null);
    }
  };

  const handleRequestImport = async () => {
    if (!isConnected) {
      appendAssistantText('Connect to the Fin Agent server before importing statements.');
      return;
    }
    if (isImporting || isSelecting) return;
    if (canPickFiles && canPickDirectories) {
      setShowPickerMenu((prev) => !prev);
      return;
    }
    await runSelection(canPickFiles ? 'files' : 'directory');
  };

  const runAssetSelection = async (mode: SelectionMode) => {
    setShowAssetPickerMenu(false);
    if (isImportingAssets || isSelecting) return;
    setIsImportingAssets(true);
    setActiveImportMode('assets');
    try {
      const entries = await selectFiles(mode);
      if (!entries.length) {
        return;
      }

      const absolutePaths = collectAbsolutePaths(entries);
      if (absolutePaths) {
        sendAssetTrackerRequest(absolutePaths);
        return;
      }

      appendAssistantText('Staging selected files so the asset-tracker can access them…');
      const staged = await stageEntriesRemotely(entries);
      if (staged.skipped.length) {
        appendAssistantText(`Some uploads were skipped: ${staged.skipped.join(', ')}`);
      }
      sendAssetTrackerRequest(staged.resolved, { staged: true, stagingDir: staged.stagingDir });
    } catch (error: any) {
      const detail = error?.message ?? 'Failed to prepare selected files.';
      appendAssistantText(detail);
    } finally {
      resetSelection();
      setIsImportingAssets(false);
      setActiveImportMode(null);
    }
  };

  const handleRequestAssetImport = async () => {
    if (!isConnected) {
      appendAssistantText('Connect to the Fin Agent server before importing asset statements.');
      return;
    }
    if (isImportingAssets || isSelecting) return;
    if (canPickFiles && canPickDirectories) {
      setShowAssetPickerMenu((prev) => !prev);
      return;
    }
    await runAssetSelection(canPickFiles ? 'files' : 'directory');
  };

  useEffect(() => {
    if (!showPickerMenu) return;
    const handleClickAway = (event: MouseEvent) => {
      if (pickerAnchorRef.current && !pickerAnchorRef.current.contains(event.target as Node)) {
        setShowPickerMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickAway);
    return () => document.removeEventListener('mousedown', handleClickAway);
  }, [showPickerMenu]);

  useEffect(() => {
    if (!showAssetPickerMenu) return;
    const handleClickAway = (event: MouseEvent) => {
      if (assetPickerAnchorRef.current && !assetPickerAnchorRef.current.contains(event.target as Node)) {
        setShowAssetPickerMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickAway);
    return () => document.removeEventListener('mousedown', handleClickAway);
  }, [showAssetPickerMenu]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (!selectionError) return;
    const message: Message = {
      id: Date.now().toString(),
      type: 'assistant',
      content: [{ type: 'text', text: selectionError }],
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, message]);
  }, [selectionError, setMessages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading || !isConnected) return;

    const trimmed = inputValue.trim();
    if (!trimmed) return;

    setInputValue('');
    dispatchPrompt({ displayText: trimmed, agentText: trimmed });
  };

  const hasStreamingAssistant = useMemo(() => (
    messages.some(msg => msg.type === 'assistant' && msg.metadata?.streaming)
  ), [messages]);

  return (
    <div className="flex flex-col h-screen relative overflow-hidden bg-[var(--bg-primary)]">
      {/* Header */}
      <header className="bg-[var(--bg-secondary)] border-b border-[var(--border-light)] px-6 py-4 shadow-[var(--shadow-xs)]">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-[var(--radius-md)] bg-[var(--accent-primary)] flex items-center justify-center shadow-[var(--shadow-sm)]">
              <Wallet size={20} className="text-white" />
            </div>
            <div>
              <h1 className="font-display text-xl text-[var(--text-primary)]">
                Fin
              </h1>
              <p className="text-xs text-[var(--text-muted)]">
                Your financial assistant
              </p>
            </div>
          </div>

          {/* Connection status */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
            isConnected
              ? 'bg-[#e8f5e9] text-[#4a7c59]'
              : 'bg-[#fce8e8] text-[var(--accent-danger)]'
          }`}>
            <div className={`w-2 h-2 rounded-full ${
              isConnected ? 'bg-[#4a7c59]' : 'bg-[var(--accent-danger)]'
            } ${isConnected ? 'animate-pulse-soft' : ''}`} />
            <span className="font-medium">
              {isConnected ? 'Connected' : 'Offline'}
            </span>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-6">
        <div className="max-w-3xl mx-auto w-full">
          {/* Quick actions */}
          <div className="mb-6 space-y-4">
            <SuggestedQueries onSend={sendSuggestedPrompt} disabled={!isConnected || isLoading} />

            <div className="flex justify-end gap-2">
              <div className="relative" ref={pickerAnchorRef}>
                <ImportStatementsButton
                  onRequestImport={handleRequestImport}
                  isLoading={isImporting || (isSelecting && activeImportMode === 'statements')}
                />
                {showPickerMenu && (
                  <div className="absolute right-0 top-full z-10 mt-2 w-48 card-elevated overflow-hidden animate-fade-in">
                    <button
                      type="button"
                      className="block w-full px-4 py-3 text-left text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
                      onClick={() => runSelection('files')}
                    >
                      Select files
                    </button>
                    <button
                      type="button"
                      className="block w-full px-4 py-3 text-left text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border-t border-[var(--border-light)]"
                      onClick={() => runSelection('directory')}
                    >
                      Select folder
                    </button>
                  </div>
                )}
              </div>
              <div className="relative" ref={assetPickerAnchorRef}>
                <ImportAssetStatementsButton
                  onRequestImport={handleRequestAssetImport}
                  isLoading={isImportingAssets || (isSelecting && activeImportMode === 'assets')}
                />
                {showAssetPickerMenu && (
                  <div className="absolute right-0 top-full z-10 mt-2 w-48 card-elevated overflow-hidden animate-fade-in">
                    <button
                      type="button"
                      className="block w-full px-4 py-3 text-left text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
                      onClick={() => runAssetSelection('files')}
                    >
                      Select files
                    </button>
                    <button
                      type="button"
                      className="block w-full px-4 py-3 text-left text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors border-t border-[var(--border-light)]"
                      onClick={() => runAssetSelection('directory')}
                    >
                      Select folder
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Empty state */}
          {messages.length === 0 ? (
            <div className="text-center py-16">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-[var(--accent-primary-light)] mb-5">
                <Wallet size={28} className="text-[var(--accent-primary)]" />
              </div>
              <h2 className="font-display text-xl text-[var(--text-primary)] mb-2">
                How can I help you today?
              </h2>
              <p className="text-[var(--text-secondary)] max-w-sm mx-auto leading-relaxed">
                Ask about your spending, search transactions, or import new statements to get started.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg) => (
                <MessageRenderer key={msg.id} message={msg} onSendMessage={sendSuggestedPrompt} />
              ))}
              {isLoading && !hasStreamingAssistant && (
                <MessageRenderer
                  message={{
                    id: 'loading',
                    type: 'assistant',
                    content: [{ type: 'text', text: 'Thinking...' }],
                    timestamp: new Date().toISOString(),
                  }}
                />
              )}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <div className="bg-[var(--bg-secondary)] border-t border-[var(--border-light)] px-4 py-4 md:px-6 shadow-[0_-2px_10px_rgba(0,0,0,0.03)]">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="flex gap-3">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={isConnected ? "Ask about your finances..." : "Waiting for connection..."}
              className="flex-1 px-4 py-3 text-[15px] input-field"
              disabled={isLoading || !isConnected}
            />
            <button
              type="submit"
              disabled={isLoading || !inputValue.trim() || !isConnected}
              className="px-5 py-3 btn-primary flex items-center gap-2"
            >
              <Send size={18} />
              <span className="hidden sm:inline">Send</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
