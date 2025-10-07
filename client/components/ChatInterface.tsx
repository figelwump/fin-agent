import React, { useState, useRef, useEffect } from 'react';
import { MessageRenderer } from './message/MessageRenderer';
import { Message, ImportSummaryBlock, ImportProgressBlock, StructuredPrompt } from './message/types';
import { Send, Wifi, WifiOff, RefreshCw, Mail, Clock } from 'lucide-react';
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

export function ChatInterface({ isConnected, sendMessage, messages, setMessages, sessionId, isLoading, setIsLoading }: ChatInterfaceProps) {
  const [inputValue, setInputValue] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [showPickerMenu, setShowPickerMenu] = useState(false);
  const progressMessageIdRef = useRef<string | null>(null);
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

  const updateAssistantText = (id: string, text: string) => {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== id) return msg;
        if (msg.type !== 'assistant') return msg;
        return {
          ...msg,
          content: [{ type: 'text', text }],
          timestamp: new Date().toISOString(),
        };
      })
    );
  };

  const appendImportSummary = (data: ImportSummaryBlock['data']) => {
    const message: Message = {
      id: Date.now().toString(),
      type: 'assistant',
      content: [{ type: 'import_summary', data }],
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, message]);
  };

  const appendProgressMessage = (data: ImportProgressBlock['data']) => {
    const message: Message = {
      id: Date.now().toString(),
      type: 'assistant',
      content: [{ type: 'import_progress', data }],
      timestamp: new Date().toISOString(),
    };
    progressMessageIdRef.current = message.id;
    setMessages((prev) => [...prev, message]);
  };

  const updateProgressMessage = (data: ImportProgressBlock['data']) => {
    const id = progressMessageIdRef.current;
    if (!id) return;
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== id || msg.type !== 'assistant') return msg;
        return {
          ...msg,
          content: [{ type: 'import_progress', data }],
          timestamp: new Date().toISOString(),
        };
      })
    );
  };

  const runImportFlow = async (entries: SelectedEntry[]) => {
    if (!entries.length) return;

    const listed = entries.slice(0, 3).map((entry) => entry.relativePath);
    const remaining = entries.length - listed.length;
    const introLines = [
      `Queued ${entries.length} file${entries.length === 1 ? '' : 's'} for import:`,
      ...listed.map((path) => `• ${path}`),
      remaining > 0 ? `…and ${remaining} more.` : undefined,
    ].filter(Boolean);
    const filePaths = entries.map((entry) => entry.relativePath);
    appendProgressMessage({
      stage: 'uploading',
      message: `${introLines.join('\n')}`,
      files: filePaths,
    });

    const formData = new FormData();
    entries.forEach((entry) => {
      formData.append('files', entry.file, entry.relativePath);
    });
    formData.append('autoApprove', 'false');

    let processingTimer: number | undefined;
    try {
      if (typeof window !== 'undefined') {
        processingTimer = window.setTimeout(() => {
          updateProgressMessage({
            stage: 'processing',
            message: 'Processing statements… this may take a minute.',
            files: filePaths,
          });
        }, 1500);
      }
      const response = await fetch('/api/bulk-import', {
        method: 'POST',
        body: formData,
      });
      const payload = await response.json();

      if (!response.ok) {
        const errorText = typeof payload?.error === 'string'
          ? payload.error
          : 'Bulk import failed. Please check server logs.';
        throw new Error(errorText);
      }

      const { stagingDir, skipped = [], summary } = payload as any;

      const csvCount = Array.isArray(summary?.csvPaths) ? summary.csvPaths.length : 0;
      const reviewPath = summary?.reviewPath ?? null;
      const unsupported = Array.isArray(summary?.unsupported) ? summary.unsupported : [];
      const missing = Array.isArray(summary?.missing) ? summary.missing : [];
      const transactions = Array.isArray(summary?.transactionsPreview) ? summary.transactionsPreview : [];
      const reviewItems = Array.isArray(summary?.reviewItems) ? summary.reviewItems : [];
      const steps = Array.isArray(summary?.steps) ? summary.steps : [];
      const extractionErrors = Array.isArray(summary?.extraction)
        ? summary.extraction
            .filter((entry: any) => entry.status === 'error')
            .map((entry: any) => `${entry.sourcePath}: ${entry.error ?? entry.stderr ?? 'Unknown error'}`)
        : [];

      const summaryData = {
        csvCount,
        stagingDir,
        reviewPath,
        unsupported,
        missing,
        skippedUploads: skipped,
        extractionErrors,
        transactions,
        reviewItems,
        steps,
      };

      appendImportSummary(summaryData);

      if (progressMessageIdRef.current) {
        updateProgressMessage({
          stage: 'completed',
          message: steps.length
            ? steps.map((step: any) => `${step.name}: ${(step.durationMs / 1000).toFixed(1)}s`).join('\n')
            : 'Finished.',
          files: filePaths,
        });
        progressMessageIdRef.current = null;
      }
    } catch (err: any) {
      const detail = err?.message ?? 'Unknown error';
      if (progressMessageIdRef.current) {
        updateProgressMessage({
          stage: 'error',
          message: detail,
          files: filePaths,
        });
        progressMessageIdRef.current = null;
      } else {
        appendAssistantText(`Bulk import failed: ${detail}`);
      }
    } finally {
      if (processingTimer) {
        clearTimeout(processingTimer);
      }
      resetSelection();
    }
  };

  const runSelection = async (mode: SelectionMode) => {
    setShowPickerMenu(false);
    if (isImporting || isSelecting) return;
    setIsImporting(true);
    try {
      const entries = await selectFiles(mode);
      if (!entries.length) {
        setIsImporting(false);
        return;
      }
      await runImportFlow(entries);
    } finally {
      setIsImporting(false);
    }
  };

  const handleRequestImport = async () => {
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
  
  return (
    <div className="flex flex-col h-screen bg-white">
      <div className="flex-1 overflow-y-auto p-3">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-3 pb-3 border-b border-gray-200">
            <h1 className="text-lg font-semibold uppercase tracking-wider">Fin Agent</h1>
          </div>
          <div className="mb-3 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="md:flex-1">
              <SuggestedQueries onSend={sendSuggestedPrompt} disabled={!isConnected || isLoading} />
            </div>
            <div className="relative flex md:items-start" ref={pickerAnchorRef}>
              <ImportStatementsButton
                onRequestImport={handleRequestImport}
                disabled={!isConnected}
                isLoading={isImporting || isSelecting}
              />
              {showPickerMenu && (
                <div className="absolute right-0 top-full z-10 mt-2 w-48 border border-gray-200 bg-white shadow-md">
                  <button
                    type="button"
                    className="block w-full px-3 py-2 text-left text-xs uppercase tracking-wider hover:bg-gray-100"
                    onClick={() => runSelection('files')}
                  >
                    Select Files…
                  </button>
                  <button
                    type="button"
                    className="block w-full px-3 py-2 text-left text-xs uppercase tracking-wider hover:bg-gray-100"
                    onClick={() => runSelection('directory')}
                  >
                    Select Folder…
                  </button>
                </div>
              )}
            </div>
          </div>
          
          {messages.length === 0 ? (
            <div className="text-center text-gray-400 mt-12">
              <p className="text-sm uppercase tracking-wider">Start a conversation</p>
              <p className="mt-2 text-xs">"Show me top spending categories" • "Find all my Amazon purchases" • "What are my subscriptions?"</p>
            </div>
          ) : (
            <div className="space-y-2">
              {messages.map((msg) => (
                <MessageRenderer key={msg.id} message={msg} onSendMessage={sendSuggestedPrompt} />
              ))}
              {isLoading && (
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
      
      <div className="border-t border-gray-200 bg-white p-3">
        <form onSubmit={handleSubmit} className="max-w-5xl mx-auto">
          <div className="flex gap-2">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={isConnected ? "Ask about your finances..." : "Waiting for connection..."}
              className="flex-1 px-3 py-2 text-sm border border-gray-300 focus:border-gray-900 focus:outline-none"
              disabled={isLoading || !isConnected}
            />
            <button
              type="submit"
              disabled={isLoading || !inputValue.trim() || !isConnected}
              className="px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-gray-900 text-white hover:bg-white hover:text-gray-900 border border-gray-900 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
            >
              <Send size={14} />
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
