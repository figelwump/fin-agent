import React, { useState, useRef, useEffect, useMemo } from 'react';
import { MessageRenderer } from './message/MessageRenderer';
import { Message, StructuredPrompt } from './message/types';
import { Send } from 'lucide-react';
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
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-6 md:px-6">
        <div className="max-w-5xl mx-auto w-full">
          <div className="mb-8 pb-6 border-b border-white/20 relative">
            <div className="absolute -left-2 top-0 bottom-0 w-1 bg-gradient-to-b from-transparent via-white/40 to-transparent rounded-full"></div>
            <h1 className="text-4xl font-bold text-white tracking-tight" style={{ fontFamily: "'Lexend', sans-serif" }}>Fin Agent</h1>
            <p className="text-white/80 text-base mt-2">Your intelligent financial assistant</p>
          </div>
          <div className="mb-6 flex flex-col gap-4">
            <div className="w-full">
              <SuggestedQueries onSend={sendSuggestedPrompt} disabled={!isConnected || isLoading} />
            </div>
            <div className="relative flex justify-end" ref={pickerAnchorRef}>
              <ImportStatementsButton
                onRequestImport={handleRequestImport}
                isLoading={isImporting || isSelecting}
              />
              {showPickerMenu && (
                <div className="absolute right-0 top-full z-10 mt-2 w-52 border border-white/30 bg-white/95 backdrop-blur-lg shadow-xl rounded-xl overflow-hidden animate-scale-in">
                  <button
                    type="button"
                    className="block w-full px-4 py-3 text-left text-sm font-medium text-gray-700 hover:bg-purple-50 hover:text-purple-700 transition-colors"
                    onClick={() => runSelection('files')}
                  >
                    Select Files…
                  </button>
                  <button
                    type="button"
                    className="block w-full px-4 py-3 text-left text-sm font-medium text-gray-700 hover:bg-purple-50 hover:text-purple-700 transition-colors border-t border-gray-200"
                    onClick={() => runSelection('directory')}
                  >
                    Select Folder…
                  </button>
                </div>
              )}
            </div>
          </div>


          {messages.length === 0 ? (
            <div className="text-center text-white/60 mt-20">
              <p className="text-lg font-medium mb-3">Start a conversation</p>
              <p className="text-sm text-white/50">Try asking: "Show me top spending categories" • "Find all my Amazon purchases"</p>
            </div>
          ) : (
            <div className="space-y-3">
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

      <div className="border-t border-white/10 backdrop-blur-xl bg-white/10 px-4 py-4 md:px-6 md:py-6 relative z-10">
        <form onSubmit={handleSubmit} className="max-w-5xl mx-auto">
          <div className="flex gap-2 md:gap-3">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={isConnected ? "Ask about your finances..." : "Waiting for connection..."}
              className="flex-1 min-w-0 px-3 py-2.5 md:px-4 md:py-3 text-sm bg-white/90 backdrop-blur-sm border-2 border-white/30 rounded-xl focus:border-white focus:outline-none focus:ring-4 focus:ring-white/30 placeholder:text-gray-400 transition-all shadow-md focus:shadow-xl"
              disabled={isLoading || !isConnected}
            />
            <button
              type="submit"
              disabled={isLoading || !inputValue.trim() || !isConnected}
              className="px-4 py-2.5 md:px-6 md:py-3 text-sm font-semibold bg-white text-purple-600 hover:bg-white hover:scale-105 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 transition-all shadow-lg hover:shadow-2xl hover:shadow-purple-500/20 whitespace-nowrap flex-shrink-0"
            >
              <Send size={16} />
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
