import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AssistantMessage as AssistantMessageType, ToolUseBlock, TextBlock, ImportSummaryBlock, ImportProgressBlock, StructuredPrompt } from './types';
import { VizRenderer, isValidFinviz, parseFinviz } from '../viz/VizRenderer';
import { ImportSummaryBlockRenderer } from './ImportSummaryBlock';
import { ImportProgressBlockRenderer } from './ImportProgressBlock';
import { ChevronDown, ChevronRight, Wrench } from 'lucide-react';

interface AssistantMessageProps {
  message: AssistantMessageType;
  onSendMessage?: (message: StructuredPrompt | string) => void;
}

function ToolUseComponent({ toolUse }: { toolUse: ToolUseBlock }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const formatToolDisplay = () => {
    const input = toolUse.input;

    switch(toolUse.name) {
      case 'Read':
        return (
          <div className="space-y-1 text-sm">
            <div className="text-[var(--text-secondary)]">
              Reading <code className="text-[var(--accent-primary)]">{input.file_path}</code>
            </div>
          </div>
        );

      case 'Write':
        return (
          <div className="space-y-2 text-sm">
            <div className="text-[var(--text-secondary)]">
              Writing to <code className="text-[var(--accent-primary)]">{input.file_path}</code>
            </div>
            <pre className="text-xs bg-[var(--bg-tertiary)] p-3 rounded-[var(--radius-sm)] overflow-x-auto max-h-32 overflow-y-auto">
              {input.content.length > 500 ? input.content.substring(0, 500) + '...' : input.content}
            </pre>
          </div>
        );

      case 'Edit':
      case 'MultiEdit':
        return (
          <div className="space-y-2 text-sm">
            <div className="text-[var(--text-secondary)]">
              Editing <code className="text-[var(--accent-primary)]">{input.file_path}</code>
            </div>
            {toolUse.name === 'Edit' && (
              <div className="space-y-2">
                <div className="bg-red-50 border border-red-100 rounded-[var(--radius-sm)] p-2">
                  <div className="text-xs text-red-600 mb-1">Removing:</div>
                  <pre className="text-xs overflow-x-auto max-h-20 overflow-y-auto text-red-800">{input.old_string}</pre>
                </div>
                <div className="bg-green-50 border border-green-100 rounded-[var(--radius-sm)] p-2">
                  <div className="text-xs text-green-600 mb-1">Adding:</div>
                  <pre className="text-xs overflow-x-auto max-h-20 overflow-y-auto text-green-800">{input.new_string}</pre>
                </div>
              </div>
            )}
          </div>
        );

      case 'Bash':
        return (
          <div className="space-y-2 text-sm">
            {input.description && (
              <div className="text-[var(--text-secondary)]">{input.description}</div>
            )}
            <pre className="text-xs bg-[#2c2c2c] text-[#e8e8e8] p-3 rounded-[var(--radius-sm)] overflow-x-auto">
              $ {input.command}
            </pre>
          </div>
        );

      case 'Skill':
        return (
          <div className="text-sm text-[var(--text-secondary)]">
            Running skill: <span className="badge">{input.skill}</span>
          </div>
        );

      default:
        return (
          <pre className="text-xs bg-[var(--bg-tertiary)] p-3 rounded-[var(--radius-sm)] overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(input, null, 2)}
          </pre>
        );
    }
  };

  return (
    <div className="mt-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-[var(--bg-tertiary)] rounded-[var(--radius-sm)] hover:bg-[var(--border-light)] transition-colors text-left"
      >
        <Wrench size={14} className="text-[var(--text-muted)]" />
        <span className="text-sm font-medium text-[var(--text-secondary)] flex-1">
          {toolUse.name}
        </span>
        {isExpanded ? (
          <ChevronDown size={14} className="text-[var(--text-muted)]" />
        ) : (
          <ChevronRight size={14} className="text-[var(--text-muted)]" />
        )}
      </button>

      {isExpanded && (
        <div className="mt-2 pl-4 border-l-2 border-[var(--border-light)]">
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
      <div key={0} className="prose prose-sm max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ node, ...props }) => (
              <h1 {...props} className="font-display text-xl mb-4 mt-6 text-[var(--text-primary)]" />
            ),
            h2: ({ node, ...props }) => (
              <h2 {...props} className="font-display text-lg mb-3 mt-5 text-[var(--text-primary)]" />
            ),
            h3: ({ node, ...props }) => (
              <h3 {...props} className="font-semibold text-base mb-2 mt-4 text-[var(--text-primary)]" />
            ),
            strong: ({ node, ...props }) => (
              <strong {...props} className="font-semibold text-[var(--text-primary)]" />
            ),
            a: ({ node, ...props }) => (
              <a {...props} className="text-[var(--accent-primary)] hover:underline font-medium" />
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
                return <code className="bg-[var(--bg-tertiary)] text-[var(--accent-primary)] px-1.5 py-0.5 rounded text-sm" {...props}>{children}</code>;
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
                  <pre className="text-sm bg-red-50 p-3 rounded-[var(--radius-md)] border border-red-100">
                    Invalid finviz spec:\n{raw}
                  </pre>
                );
              }
              return (
                <code className="block bg-[#2c2c2c] text-[#e8e8e8] p-4 rounded-[var(--radius-md)] text-sm overflow-x-auto" {...props}>
                  {children}
                </code>
              );
            },
            ul: ({ node, ...props }) => (
              <ul className="list-disc pl-5 space-y-1.5 marker:text-[var(--accent-primary)]" {...props} />
            ),
            ol: ({ node, ...props }) => (
              <ol className="list-decimal pl-5 space-y-1.5 marker:text-[var(--accent-primary)]" {...props} />
            ),
            li: ({ node, ...props }) => (
              <li className="text-[var(--text-primary)]" {...props} />
            ),
            p: ({ node, ...props }) => (
              <p className="mb-3 text-[var(--text-primary)] leading-relaxed" {...props} />
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
    <div className="text-[15px] text-[var(--text-primary)]">
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
  const merchant = findIdx('merchant', 'description', 'payee');
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
      <div className="max-w-2xl">
        {/* Content */}
        <div className="space-y-2">
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

        {/* Metadata toggle */}
        {message.metadata && (
          <div className="mt-3">
            <button
              onClick={() => setShowMetadata(!showMetadata)}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] flex items-center gap-1 transition-colors"
            >
              {showMetadata ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Details
              {message.metadata.usage && (
                <span className="ml-1 text-[var(--text-muted)]">
                  ({message.metadata.usage.input_tokens + message.metadata.usage.output_tokens} tokens)
                </span>
              )}
            </button>

            {showMetadata && (
              <div className="mt-2 p-3 bg-[var(--bg-tertiary)] rounded-[var(--radius-sm)] text-xs">
                <pre className="overflow-x-auto whitespace-pre-wrap text-[var(--text-secondary)]">
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
