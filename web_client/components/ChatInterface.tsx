import React, { useState, useRef, useEffect, useMemo } from 'react';
import { MessageRenderer } from './message/MessageRenderer';
import { Message, StructuredPrompt } from './message/types';
import { ArrowUp, Zap } from 'lucide-react';
import { SuggestedQueries } from './dashboard/SuggestedQueries';
import { ImportStatementsButton } from './dashboard/ImportStatementsButton';
import { useFileSelection, SelectionMode, SelectedEntry } from '../hooks/useFileSelection';

interface ChatInterfaceProps {
  isConnected: boolean;
  sendMessage: (message: any) => void;
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  sessionId: string | null;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
}

type ResolvedStatementPath = {
  path: string;
  label: string;
  source: 'absolute' | 'staged';
};

export function ChatInterface({ isConnected, sendMessage, messages, setMessages, sessionId, isLoading, setIsLoading }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [showPickerMenu, setShowPickerMenu] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pickerAnchorRef = useRef<HTMLDivElement>(null);
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

  const runSelection = async (mode: SelectionMode) => {
    setShowPickerMenu(false);
    if (isImporting || isSelecting) return;
    setIsImporting(true);
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
    <div className="flex flex-col h-screen relative z-10 overflow-hidden">
      {/* Header */}
      <header className="border-b border-[var(--border-default)] bg-[var(--bg-secondary)]/80 backdrop-blur-xl px-6 py-4 relative z-20">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            {/* Logo / Brand */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] flex items-center justify-center shadow-lg shadow-[var(--accent-primary)]/20">
                <Zap size={20} className="text-[var(--bg-primary)]" />
              </div>
              <div>
                <h1 className="font-mono-display text-xl tracking-tight text-[var(--text-primary)]">
                  FIN<span className="text-[var(--accent-primary)]">_</span>AGENT
                </h1>
                <p className="text-xs text-[var(--text-muted)] font-mono tracking-wide">
                  FINANCIAL INTELLIGENCE TERMINAL
                </p>
              </div>
            </div>
          </div>

          {/* Status indicator */}
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md border ${
              isConnected
                ? 'border-[var(--accent-secondary)]/30 bg-[var(--accent-secondary)]/5'
                : 'border-[var(--accent-danger)]/30 bg-[var(--accent-danger)]/5'
            }`}>
              <div className={`w-2 h-2 rounded-full ${
                isConnected
                  ? 'bg-[var(--accent-secondary)] animate-pulse'
                  : 'bg-[var(--accent-danger)]'
              }`} />
              <span className={`text-xs font-mono ${
                isConnected ? 'text-[var(--accent-secondary)]' : 'text-[var(--accent-danger)]'
              }`}>
                {isConnected ? 'CONNECTED' : 'OFFLINE'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main content area */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-6">
        <div className="max-w-5xl mx-auto w-full">
          {/* Quick actions bar */}
          <div className="mb-6 flex flex-col gap-4">
            <SuggestedQueries onSend={sendSuggestedPrompt} disabled={!isConnected || isLoading} />

            <div className="relative flex justify-end" ref={pickerAnchorRef}>
              <ImportStatementsButton
                onRequestImport={handleRequestImport}
                isLoading={isImporting || isSelecting}
              />
              {showPickerMenu && (
                <div className="absolute right-0 top-full z-10 mt-2 w-52 border border-[var(--border-default)] bg-[var(--bg-secondary)] shadow-xl overflow-hidden animate-fade-in">
                  <button
                    type="button"
                    className="block w-full px-4 py-3 text-left text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--accent-primary)]/10 hover:text-[var(--accent-primary)] transition-colors"
                    onClick={() => runSelection('files')}
                  >
                    Select Files…
                  </button>
                  <button
                    type="button"
                    className="block w-full px-4 py-3 text-left text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--accent-primary)]/10 hover:text-[var(--accent-primary)] transition-colors border-t border-[var(--border-subtle)]"
                    onClick={() => runSelection('directory')}
                  >
                    Select Folder…
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Empty state */}
          {messages.length === 0 ? (
            <div className="text-center py-20 animate-fade-in">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-xl bg-[var(--bg-tertiary)] border border-[var(--border-default)] mb-6">
                <span className="font-mono text-2xl text-[var(--accent-primary)]">$_</span>
              </div>
              <p className="font-mono-display text-lg text-[var(--text-primary)] mb-2">
                Ready for queries
              </p>
              <p className="text-sm text-[var(--text-muted)] max-w-md mx-auto">
                Ask about your spending patterns, search transactions, or import new statements
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-3 text-xs font-mono text-[var(--text-muted)]">
                <span className="px-3 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded">"Show top categories"</span>
                <span className="px-3 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded">"Find Amazon purchases"</span>
                <span className="px-3 py-1.5 bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded">"Monthly summary"</span>
              </div>
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
                    content: [{ type: 'text', text: 'Processing...' }],
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
      <div className="border-t border-[var(--border-default)] bg-[var(--bg-secondary)]/80 backdrop-blur-xl px-6 py-5 relative z-10">
        <form onSubmit={handleSubmit} className="max-w-5xl mx-auto">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={isConnected ? "Enter query..." : "Waiting for connection..."}
                className="w-full px-4 py-3.5 text-sm terminal-input rounded-lg pr-12"
                disabled={isLoading || !isConnected}
              />
              {/* Cursor blink effect when empty */}
              {!inputValue && isConnected && !isLoading && (
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--accent-primary)] animate-blink pointer-events-none">
                  |
                </span>
              )}
            </div>
            <button
              type="submit"
              disabled={isLoading || !inputValue.trim() || !isConnected}
              className="px-5 py-3.5 btn-primary rounded-lg flex items-center gap-2 text-sm font-semibold"
            >
              <ArrowUp size={16} />
              <span className="hidden sm:inline">Execute</span>
            </button>
          </div>

          {/* Keyboard hint */}
          <div className="mt-3 flex items-center justify-between text-xs text-[var(--text-muted)]">
            <span className="font-mono">
              <kbd className="px-1.5 py-0.5 bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded text-[10px]">↵</kbd>
              {' '}to send
            </span>
            {isLoading && (
              <span className="flex items-center gap-2 text-[var(--accent-primary)]">
                <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                Processing query...
              </span>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
