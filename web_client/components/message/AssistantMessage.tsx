import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AssistantMessage as AssistantMessageType, ToolUseBlock, TextBlock, ImportSummaryBlock, ImportProgressBlock, StructuredPrompt } from './types';
import { VizRenderer, isValidFinviz, parseFinviz } from '../viz/VizRenderer';
import { ImportSummaryBlockRenderer } from './ImportSummaryBlock';
import { ImportProgressBlockRenderer } from './ImportProgressBlock';
import { Bot, ChevronDown, ChevronRight, Code2, Cpu } from 'lucide-react';

interface AssistantMessageProps {
  message: AssistantMessageType;
  onSendMessage?: (message: StructuredPrompt | string) => void;
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function ToolUseComponent({ toolUse }: { toolUse: ToolUseBlock }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const formatToolDisplay = () => {
    const input = toolUse.input;

    switch(toolUse.name) {
      case 'Read':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">FILE</span>
              <code className="text-xs text-[var(--accent-primary)] font-mono">{input.file_path}</code>
            </div>
            {input.offset && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)] font-mono">OFFSET</span>
                <span className="text-xs text-[var(--text-primary)] font-mono">{input.offset}</span>
              </div>
            )}
            {input.limit && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)] font-mono">LIMIT</span>
                <span className="text-xs text-[var(--text-primary)] font-mono">{input.limit} lines</span>
              </div>
            )}
          </div>
        );

      case 'Write':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">FILE</span>
              <code className="text-xs text-[var(--accent-primary)] font-mono">{input.file_path}</code>
            </div>
            <div>
              <span className="text-xs text-[var(--text-muted)] font-mono block mb-1">CONTENT</span>
              <pre className="text-xs bg-[var(--bg-primary)] p-2 border border-[var(--border-subtle)] overflow-x-auto font-mono max-h-32 overflow-y-auto text-[var(--text-primary)]">
                {input.content.length > 500 ? input.content.substring(0, 500) + '...' : input.content}
              </pre>
            </div>
          </div>
        );

      case 'Edit':
      case 'MultiEdit':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">FILE</span>
              <code className="text-xs text-[var(--accent-primary)] font-mono">{input.file_path}</code>
            </div>
            {toolUse.name === 'Edit' ? (
              <>
                {input.replace_all && (
                  <div className="text-xs text-[var(--accent-warm)] font-mono">REPLACE ALL</div>
                )}
                <div className="space-y-2">
                  <div>
                    <span className="text-xs text-[var(--accent-danger)] font-mono block mb-1">- REMOVE</span>
                    <pre className="text-xs bg-[var(--accent-danger)]/5 p-2 border border-[var(--accent-danger)]/20 overflow-x-auto font-mono max-h-24 overflow-y-auto text-[var(--text-primary)]">
                      {input.old_string}
                    </pre>
                  </div>
                  <div>
                    <span className="text-xs text-[var(--accent-secondary)] font-mono block mb-1">+ ADD</span>
                    <pre className="text-xs bg-[var(--accent-secondary)]/5 p-2 border border-[var(--accent-secondary)]/20 overflow-x-auto font-mono max-h-24 overflow-y-auto text-[var(--text-primary)]">
                      {input.new_string}
                    </pre>
                  </div>
                </div>
              </>
            ) : (
              <div className="space-y-2">
                <span className="text-xs text-[var(--text-muted)] font-mono">
                  {input.edits?.length || 0} EDITS
                </span>
                {input.edits?.slice(0, 3).map((edit: any, i: number) => (
                  <div key={i} className="pl-3 border-l-2 border-[var(--accent-primary)]/30">
                    <div className="text-xs text-[var(--text-muted)] font-mono">EDIT {i + 1}</div>
                    {edit.replace_all && (
                      <div className="text-xs text-[var(--accent-warm)] font-mono">REPLACE ALL</div>
                    )}
                    <div className="text-xs text-[var(--accent-danger)] font-mono">- {edit.old_string.substring(0, 50)}{edit.old_string.length > 50 ? '...' : ''}</div>
                    <div className="text-xs text-[var(--accent-secondary)] font-mono">+ {edit.new_string.substring(0, 50)}{edit.new_string.length > 50 ? '...' : ''}</div>
                  </div>
                ))}
                {input.edits?.length > 3 && (
                  <div className="text-xs text-[var(--text-muted)] font-mono pl-3">
                    ... and {input.edits.length - 3} more
                  </div>
                )}
              </div>
            )}
          </div>
        );

      case 'Bash':
        return (
          <div className="space-y-2">
            <div>
              <span className="text-xs text-[var(--text-muted)] font-mono block mb-1">COMMAND</span>
              <pre className="text-xs bg-[var(--bg-primary)] text-[var(--accent-secondary)] p-2 border border-[var(--border-subtle)] overflow-x-auto font-mono">
                $ {input.command}
              </pre>
            </div>
            {input.description && (
              <div className="text-xs text-[var(--text-secondary)]">
                {input.description}
              </div>
            )}
            {input.run_in_background && (
              <div className="text-xs text-[var(--accent-warm)] font-mono">BACKGROUND</div>
            )}
            {input.timeout && (
              <div className="text-xs text-[var(--text-muted)] font-mono">
                TIMEOUT: {input.timeout}ms
              </div>
            )}
          </div>
        );

      case 'Grep':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">PATTERN</span>
              <code className="text-xs text-[var(--accent-warm)] font-mono bg-[var(--accent-warm)]/10 px-1">{input.pattern}</code>
            </div>
            {input.path && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)] font-mono">PATH</span>
                <code className="text-xs text-[var(--text-primary)] font-mono">{input.path}</code>
              </div>
            )}
            {input.glob && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)] font-mono">GLOB</span>
                <code className="text-xs text-[var(--text-primary)] font-mono">{input.glob}</code>
              </div>
            )}
            <div className="flex gap-2 text-xs font-mono">
              {input['-i'] && <span className="text-[var(--text-muted)] bg-[var(--bg-elevated)] px-1">-i</span>}
              {input['-n'] && <span className="text-[var(--text-muted)] bg-[var(--bg-elevated)] px-1">-n</span>}
              {input.multiline && <span className="text-[var(--text-muted)] bg-[var(--bg-elevated)] px-1">multiline</span>}
            </div>
          </div>
        );

      case 'Glob':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">PATTERN</span>
              <code className="text-xs text-[var(--accent-primary)] font-mono">{input.pattern}</code>
            </div>
            {input.path && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)] font-mono">PATH</span>
                <code className="text-xs text-[var(--text-primary)] font-mono">{input.path}</code>
              </div>
            )}
          </div>
        );

      case 'WebSearch':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">QUERY</span>
              <span className="text-xs text-[var(--text-primary)]">{input.query}</span>
            </div>
            {input.allowed_domains && input.allowed_domains.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--text-muted)] font-mono">DOMAINS</span>
                <span className="text-xs text-[var(--text-primary)]">{input.allowed_domains.join(', ')}</span>
              </div>
            )}
          </div>
        );

      case 'WebFetch':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">URL</span>
              <code className="text-xs text-[var(--accent-primary)] font-mono break-all">{input.url}</code>
            </div>
            <div>
              <span className="text-xs text-[var(--text-muted)] font-mono block mb-1">PROMPT</span>
              <div className="text-xs text-[var(--text-primary)]">{input.prompt}</div>
            </div>
          </div>
        );

      case 'Task':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">AGENT</span>
              <span className="text-xs text-[var(--accent-primary)]">{input.subagent_type}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-mono">DESC</span>
              <span className="text-xs text-[var(--text-primary)]">{input.description}</span>
            </div>
            <div>
              <span className="text-xs text-[var(--text-muted)] font-mono block mb-1">PROMPT</span>
              <div className="text-xs text-[var(--text-primary)] max-h-24 overflow-y-auto">
                {input.prompt}
              </div>
            </div>
          </div>
        );

      case 'TodoWrite':
        return (
          <div className="space-y-2">
            <div className="text-xs text-[var(--text-muted)] font-mono">
              {input.todos?.length || 0} ITEMS
            </div>
            {input.todos?.map((todo: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={`font-mono ${
                  todo.status === 'completed' ? 'text-[var(--accent-secondary)]' :
                  todo.status === 'in_progress' ? 'text-[var(--accent-primary)]' :
                  'text-[var(--text-muted)]'
                }`}>
                  {todo.status === 'completed' ? '[x]' :
                   todo.status === 'in_progress' ? '[>]' : '[ ]'}
                </span>
                <span className={todo.status === 'completed' ? 'line-through text-[var(--text-muted)]' : 'text-[var(--text-primary)]'}>
                  {todo.status === 'in_progress' ? todo.activeForm : todo.content}
                </span>
              </div>
            ))}
          </div>
        );

      case 'Skill':
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Cpu size={14} className="text-[var(--accent-secondary)]" />
              <span className="text-xs font-mono font-semibold text-[var(--accent-secondary)]">SKILL</span>
              <code className="text-sm font-mono bg-[var(--accent-secondary)]/10 text-[var(--accent-secondary)] px-2 py-0.5 border border-[var(--accent-secondary)]/20">
                {input.skill}
              </code>
            </div>
            <div className="text-xs text-[var(--text-muted)] italic">
              Executing skill workflow...
            </div>
          </div>
        );

      default:
        return (
          <pre className="text-xs bg-[var(--bg-primary)] p-2 border border-[var(--border-subtle)] overflow-x-auto whitespace-pre-wrap font-mono text-[var(--text-primary)]">
            {JSON.stringify(input, null, 2)}
          </pre>
        );
    }
  };

  return (
    <div className="mt-3 bg-[var(--bg-tertiary)] border border-[var(--border-default)] overflow-hidden">
      {/* Tool header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-[var(--bg-elevated)] border-b border-[var(--border-subtle)] hover:bg-[var(--bg-elevated)]/80 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Code2 size={14} className="text-[var(--accent-primary)]" />
          <span className="text-xs font-mono font-semibold text-[var(--accent-primary)] uppercase tracking-wider">
            {toolUse.name}
          </span>
        </div>
        {isExpanded ? (
          <ChevronDown size={14} className="text-[var(--text-muted)]" />
        ) : (
          <ChevronRight size={14} className="text-[var(--text-muted)]" />
        )}
      </button>

      {isExpanded && (
        <div className="p-4">
          {formatToolDisplay()}
        </div>
      )}
    </div>
  );
}

function TextComponent({ text }: { text: TextBlock }) {
  const processContent = (content: string) => {
    const result: React.ReactNode[] = [];

    let skipFirstTable = false;
    if (!content.includes('```finviz')) {
      const fallback = buildFinvizFromMarkdownTable(content);
      if (fallback) {
        skipFirstTable = true;
        result.push(
          <div key="fallback-viz" className="my-3">
            <VizRenderer viz={fallback} />
          </div>
        );
      }
    }

    result.push(
      <div key={0} className="prose prose-sm max-w-none leading-relaxed">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ node, ...props }) => (
              <h1 {...props} className="font-mono-display text-xl mb-4 mt-6 text-[var(--text-primary)]" />
            ),
            h2: ({ node, ...props }) => (
              <h2 {...props} className="font-mono-display text-lg mb-3 mt-5 text-[var(--text-primary)]" />
            ),
            h3: ({ node, ...props }) => (
              <h3 {...props} className="font-semibold text-base mb-2 mt-4 text-[var(--text-primary)]" />
            ),
            strong: ({ node, ...props }) => (
              <strong {...props} className="font-semibold text-[var(--text-primary)]" />
            ),
            a: ({ node, ...props }) => (
              <a {...props} className="text-[var(--accent-primary)] hover:underline" />
            ),
            table: ({ node, ...props }) => {
              if (skipFirstTable) {
                skipFirstTable = false;
                return null;
              }
              return <table className="min-w-full" {...props} />;
            },
            code: (mdProps: any) => {
              const { inline, className, children, ...props } = mdProps || {};
              if (inline) {
                return <code className="bg-[var(--bg-elevated)] text-[var(--accent-primary)] px-1.5 py-0.5 text-xs font-mono border border-[var(--border-subtle)]" {...props}>{children}</code>;
              }
              const lang = (className || '').toString();
              if (lang.includes('language-finviz')) {
                const raw = String(children || '').trim();
                const parsed = parseFinviz(raw);
                if (parsed && isValidFinviz(parsed)) {
                  return (
                    <div className="my-3">
                      <VizRenderer viz={parsed} />
                    </div>
                  );
                }
                return (
                  <pre className="text-xs bg-[var(--accent-danger)]/10 p-3 font-mono border border-[var(--accent-danger)]/20 text-[var(--text-primary)]">
                    Invalid finviz spec:\n{raw}
                  </pre>
                );
              }
              return (
                <code className="block bg-[var(--bg-primary)] p-3 text-xs font-mono overflow-x-auto border border-[var(--border-subtle)] text-[var(--text-primary)]" {...props}>
                  {children}
                </code>
              );
            },
            ul: ({ node, ...props }) => (
              <ul className="list-none pl-4 space-y-1.5" {...props} />
            ),
            ol: ({ node, ...props }) => (
              <ol className="list-decimal pl-5 space-y-1.5 marker:text-[var(--accent-primary)]" {...props} />
            ),
            li: ({ node, ...props }) => (
              <li className="text-[var(--text-primary)] relative before:content-['▸'] before:text-[var(--accent-primary)] before:absolute before:-left-4 before:text-xs" {...props} />
            ),
            p: ({ node, ...props }) => (
              <p className="mb-3 text-[var(--text-primary)]" {...props} />
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    );

    return <>{result}</>;
  };

  return (
    <div className="text-sm text-[var(--text-primary)]">
      {processContent(text.text)}
    </div>
  );
}

function buildFinvizFromMarkdownTable(content: string) {
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length - 2; i++) {
    const header = lines[i];
    const sep = lines[i + 1];
    if (!header.trim().startsWith('|')) continue;
    if (!(sep.trim().startsWith('|') && /[-:]/.test(sep))) continue;

    const dataRows: string[] = [];
    let j = i + 2;
    while (j < lines.length && lines[j].trim().startsWith('|')) {
      dataRows.push(lines[j]);
      j++;
    }
    if (dataRows.length === 0) continue;

    const hdrCells = splitMdRow(header);
    const idx = indexTransactionColumns(hdrCells);
    if (!idx) continue;

    const rows = [] as any[];
    for (const r of dataRows.slice(0, 50)) {
      const cells = splitMdRow(r);
      if (cells.length < hdrCells.length) continue;
      const row: any = {};
      if (idx.date !== -1) row.date = cells[idx.date] || '';
      if (idx.merchant !== -1) row.merchant = cells[idx.merchant] || '';
      if (idx.category !== -1) row.category = cells[idx.category] || '';
      if (idx.amount !== -1) row.amount = parseAmount(cells[idx.amount]);
      rows.push(row);
    }
    if (rows.length === 0) continue;

    const columns = [] as { key: string; label: string }[];
    if (idx.date !== -1) columns.push({ key: 'date', label: 'Date' });
    if (idx.merchant !== -1) columns.push({ key: 'merchant', label: 'Merchant' });
    if (idx.amount !== -1) columns.push({ key: 'amount', label: 'Amount' });
    if (idx.category !== -1) columns.push({ key: 'category', label: 'Category' });

    return {
      version: '1.0',
      spec: {
        type: 'table',
        title: 'Transactions',
        columns,
        options: { currency: idx.amount !== -1 },
        data: rows,
      }
    } as any;
  }
  return null;
}

function splitMdRow(line: string): string[] {
  const inner = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return inner.split('|').map((s) => s.trim());
}

function indexTransactionColumns(headers: string[]) {
  const norm = headers.map((h) => h.toLowerCase());
  const findIdx = (...names: string[]) => norm.findIndex((n) => names.includes(n));
  const date = findIdx('date');
  const merchant = (() => {
    const i = findIdx('merchant', 'description', 'payee');
    return i;
  })();
  const amount = findIdx('amount');
  const category = findIdx('category');
  if (date === -1 || amount === -1) return null;
  return { date, merchant, amount, category };
}

function parseAmount(val: string) {
  const s = val.replace(/[^0-9\-.]/g, '');
  const n = Number(s);
  return isFinite(n) ? n : val;
}

export function AssistantMessage({ message, onSendMessage }: AssistantMessageProps) {
  const [showMetadata, setShowMetadata] = useState(false);

  return (
    <div className="mb-4">
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-default)] max-w-4xl relative overflow-hidden">
        {/* Left accent bar */}
        <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-[var(--accent-primary)]" />

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-[var(--bg-tertiary)] border-b border-[var(--border-subtle)]">
          <div className="flex items-center gap-2">
            <Bot size={14} className="text-[var(--accent-primary)]" />
            <span className="text-xs font-mono font-semibold text-[var(--accent-primary)] uppercase tracking-wider">
              Agent
            </span>
            {message.metadata?.model && (
              <span className="px-2 py-0.5 text-[10px] bg-[var(--bg-elevated)] text-[var(--text-muted)] font-mono border border-[var(--border-subtle)]">
                {message.metadata.model}
              </span>
            )}
            {message.metadata?.streaming && (
              <span className="flex items-center gap-1 text-[10px] text-[var(--accent-secondary)] font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                STREAMING
              </span>
            )}
          </div>
          <span className="text-xs font-mono text-[var(--text-muted)]">
            {formatTimestamp(message.timestamp)}
          </span>
        </div>

        {/* Content */}
        <div className="p-4 pl-6">
          <div className="space-y-3">
            {message.content.map((block, index) => {
              if (block.type === 'text') {
                return <TextComponent key={index} text={block} />;
              } else if (block.type === 'tool_use') {
                return <ToolUseComponent key={index} toolUse={block} />;
              } else if (block.type === 'import_summary') {
                return <ImportSummaryBlockRenderer key={index} block={block as ImportSummaryBlock} onSendMessage={onSendMessage} />;
              } else if (block.type === 'import_progress') {
                return <ImportProgressBlockRenderer key={index} block={block as ImportProgressBlock} />;
              }
              return null;
            })}
          </div>
        </div>

        {/* Metadata toggle */}
        {message.metadata && (
          <div className="px-4 py-2 border-t border-[var(--border-subtle)] bg-[var(--bg-tertiary)]">
            <button
              onClick={() => setShowMetadata(!showMetadata)}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--accent-primary)] flex items-center gap-1 font-mono transition-colors"
            >
              {showMetadata ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              metadata
              {message.metadata.usage && (
                <span className="ml-2 text-[var(--text-muted)]">
                  ({message.metadata.usage.input_tokens}↓ {message.metadata.usage.output_tokens}↑)
                </span>
              )}
            </button>

            {showMetadata && (
              <div className="mt-2 p-3 bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-xs">
                <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[var(--text-primary)]">
                  {JSON.stringify(message.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
