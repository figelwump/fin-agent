import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AssistantMessage as AssistantMessageType, ToolUseBlock, TextBlock, ImportSummaryBlock, ImportProgressBlock, StructuredPrompt } from './types';
import { VizRenderer, isValidFinviz, parseFinviz } from '../viz/VizRenderer';
import { ImportSummaryBlockRenderer } from './ImportSummaryBlock';
import { ImportProgressBlockRenderer } from './ImportProgressBlock';
// Dashboard pinning removed per product decision; keep visuals only.

interface AssistantMessageProps {
  message: AssistantMessageType;
  onSendMessage?: (message: StructuredPrompt | string) => void;
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString();
}

function ToolUseComponent({ toolUse }: { toolUse: ToolUseBlock }) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Format tool parameters based on tool type
  const formatToolDisplay = () => {
    const input = toolUse.input;
    
    switch(toolUse.name) {
      case 'Read':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">File:</span>
              <span className="text-xs text-gray-900 font-mono">{input.file_path}</span>
            </div>
            {input.offset && (
              <div className="flex">
                <span className="text-xs text-gray-600 font-semibold mr-2">Offset:</span>
                <span className="text-xs text-gray-900 font-mono">{input.offset}</span>
              </div>
            )}
            {input.limit && (
              <div className="flex">
                <span className="text-xs text-gray-600 font-semibold mr-2">Limit:</span>
                <span className="text-xs text-gray-900 font-mono">{input.limit} lines</span>
              </div>
            )}
          </div>
        );
        
      case 'Write':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">File:</span>
              <span className="text-xs text-gray-900 font-mono">{input.file_path}</span>
            </div>
            <div>
              <span className="text-xs text-gray-600 font-semibold">Content:</span>
              <pre className="text-xs bg-white p-1 mt-1 border border-gray-200 overflow-x-auto font-mono max-h-32 overflow-y-auto">
                {input.content.length > 500 ? input.content.substring(0, 500) + '...' : input.content}
              </pre>
            </div>
          </div>
        );
        
      case 'Edit':
      case 'MultiEdit':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">File:</span>
              <span className="text-xs text-gray-900 font-mono">{input.file_path}</span>
            </div>
            {toolUse.name === 'Edit' ? (
              <>
                {input.replace_all && (
                  <div className="text-xs text-amber-600">Replace all occurrences</div>
                )}
                <div className="space-y-1">
                  <div className="text-xs text-gray-600 font-semibold">Replace:</div>
                  <pre className="text-xs bg-red-50 p-1 border border-red-200 overflow-x-auto font-mono max-h-24 overflow-y-auto">
                    {input.old_string}
                  </pre>
                  <div className="text-xs text-gray-600 font-semibold">With:</div>
                  <pre className="text-xs bg-green-50 p-1 border border-green-200 overflow-x-auto font-mono max-h-24 overflow-y-auto">
                    {input.new_string}
                  </pre>
                </div>
              </>
            ) : (
              <div className="space-y-1">
                <span className="text-xs text-gray-600 font-semibold">
                  {input.edits?.length || 0} edits
                </span>
                {input.edits?.slice(0, 3).map((edit: any, i: number) => (
                  <div key={i} className="pl-2 border-l-2 border-gray-300">
                    <div className="text-xs text-gray-500">Edit {i + 1}:</div>
                    {edit.replace_all && (
                      <div className="text-xs text-amber-600">Replace all</div>
                    )}
                    <div className="text-xs text-gray-600">Old: {edit.old_string.substring(0, 50)}{edit.old_string.length > 50 ? '...' : ''}</div>
                    <div className="text-xs text-gray-600">New: {edit.new_string.substring(0, 50)}{edit.new_string.length > 50 ? '...' : ''}</div>
                  </div>
                ))}
                {input.edits?.length > 3 && (
                  <div className="text-xs text-gray-500 pl-2">
                    ... and {input.edits.length - 3} more edits
                  </div>
                )}
              </div>
            )}
          </div>
        );
        
      case 'Bash':
        return (
          <div className="space-y-1">
            <div>
              <span className="text-xs text-gray-600 font-semibold">Command:</span>
              <pre className="text-xs bg-gray-900 text-green-400 p-1 mt-1 border border-gray-700 overflow-x-auto font-mono">
                {input.command}
              </pre>
            </div>
            {input.description && (
              <div className="text-xs text-gray-600">
                <span className="font-semibold">Description:</span> {input.description}
              </div>
            )}
            {input.run_in_background && (
              <div className="text-xs text-amber-600">Running in background</div>
            )}
            {input.timeout && (
              <div className="text-xs text-gray-600">
                <span className="font-semibold">Timeout:</span> {input.timeout}ms
              </div>
            )}
          </div>
        );
        
      case 'Grep':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">Pattern:</span>
              <span className="text-xs text-gray-900 font-mono bg-yellow-50 px-1">{input.pattern}</span>
            </div>
            {input.path && (
              <div className="flex">
                <span className="text-xs text-gray-600 font-semibold mr-2">Path:</span>
                <span className="text-xs text-gray-900 font-mono">{input.path}</span>
              </div>
            )}
            {input.glob && (
              <div className="flex">
                <span className="text-xs text-gray-600 font-semibold mr-2">Glob:</span>
                <span className="text-xs text-gray-900 font-mono">{input.glob}</span>
              </div>
            )}
            {input.output_mode && (
              <div className="flex">
                <span className="text-xs text-gray-600 font-semibold mr-2">Mode:</span>
                <span className="text-xs text-gray-900">{input.output_mode}</span>
              </div>
            )}
            <div className="flex space-x-2 text-xs">
              {input['-i'] && <span className="bg-gray-100 px-1">case-insensitive</span>}
              {input['-n'] && <span className="bg-gray-100 px-1">line-numbers</span>}
              {input.multiline && <span className="bg-gray-100 px-1">multiline</span>}
            </div>
          </div>
        );
        
      case 'Glob':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">Pattern:</span>
              <span className="text-xs text-gray-900 font-mono">{input.pattern}</span>
            </div>
            {input.path && (
              <div className="flex">
                <span className="text-xs text-gray-600 font-semibold mr-2">Path:</span>
                <span className="text-xs text-gray-900 font-mono">{input.path}</span>
              </div>
            )}
          </div>
        );
        
      case 'WebSearch':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">Query:</span>
              <span className="text-xs text-gray-900">{input.query}</span>
            </div>
            {input.allowed_domains && input.allowed_domains.length > 0 && (
              <div className="flex">
                <span className="text-xs text-gray-600 font-semibold mr-2">Domains:</span>
                <span className="text-xs text-gray-900">{input.allowed_domains.join(', ')}</span>
              </div>
            )}
          </div>
        );
        
      case 'WebFetch':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">URL:</span>
              <span className="text-xs text-gray-900 font-mono break-all">{input.url}</span>
            </div>
            <div>
              <span className="text-xs text-gray-600 font-semibold">Prompt:</span>
              <div className="text-xs text-gray-900 mt-1">{input.prompt}</div>
            </div>
          </div>
        );
        
      case 'Task':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">Agent:</span>
              <span className="text-xs text-gray-900">{input.subagent_type}</span>
            </div>
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">Description:</span>
              <span className="text-xs text-gray-900">{input.description}</span>
            </div>
            <div>
              <span className="text-xs text-gray-600 font-semibold">Prompt:</span>
              <div className="text-xs text-gray-900 mt-1 max-h-24 overflow-y-auto">
                {input.prompt}
              </div>
            </div>
          </div>
        );
        
      case 'TodoWrite':
        return (
          <div className="space-y-1">
            <div className="text-xs text-gray-600 font-semibold">
              Todos: {input.todos?.length || 0} items
            </div>
            {input.todos?.map((todo: any, i: number) => (
              <div key={i} className="flex items-center text-xs">
                <span className={`mr-2 ${
                  todo.status === 'completed' ? 'text-green-600' : 
                  todo.status === 'in_progress' ? 'text-blue-600' : 
                  'text-gray-500'
                }`}>
                  {todo.status === 'completed' ? '✓' : 
                   todo.status === 'in_progress' ? '→' : '○'}
                </span>
                <span className={todo.status === 'completed' ? 'line-through text-gray-500' : ''}>
                  {todo.status === 'in_progress' ? todo.activeForm : todo.content}
                </span>
              </div>
            ))}
          </div>
        );
        
      case 'NotebookEdit':
        return (
          <div className="space-y-1">
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">Notebook:</span>
              <span className="text-xs text-gray-900 font-mono">{input.notebook_path}</span>
            </div>
            {input.cell_id && (
              <div className="flex">
                <span className="text-xs text-gray-600 font-semibold mr-2">Cell ID:</span>
                <span className="text-xs text-gray-900 font-mono">{input.cell_id}</span>
              </div>
            )}
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">Type:</span>
              <span className="text-xs text-gray-900">{input.cell_type || 'default'}</span>
            </div>
            <div className="flex">
              <span className="text-xs text-gray-600 font-semibold mr-2">Mode:</span>
              <span className="text-xs text-gray-900">{input.edit_mode || 'replace'}</span>
            </div>
          </div>
        );
        
      case 'ExitPlanMode':
        return (
          <div className="space-y-1">
            <div className="text-xs text-gray-600 font-semibold">Plan:</div>
            <div className="text-xs text-gray-900 bg-blue-50 p-2 border border-blue-200 max-h-32 overflow-y-auto">
              {input.plan}
            </div>
          </div>
        );
        
      default:
        // Fallback to raw JSON for unknown tools
        return (
          <pre className="text-xs bg-white p-2 border border-gray-200 overflow-x-auto whitespace-pre-wrap font-mono">
            {JSON.stringify(input, null, 2)}
          </pre>
        );
    }
  };
  
  return (
    <div className="mt-2 border border-gray-200 bg-gray-50">
      <div className="p-2 border-b border-gray-200 bg-white">
        <div className="flex justify-between items-center">
          <div className="flex items-center">
            <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">
              TOOL: {toolUse.name}
            </span>
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs text-gray-600 hover:text-gray-900 font-mono"
          >
            {isExpanded ? '[-]' : '[+]'}
          </button>
        </div>
      </div>
      
      {isExpanded && (
        <div className="p-2">
          {formatToolDisplay()}
        </div>
      )}
    </div>
  );
}

function TextComponent({ text }: { text: TextBlock }) {
  // Parse the text and add a visualization fallback if we detect a markdown transaction table and no finviz block.
  const processContent = (content: string) => {
    const result: React.ReactNode[] = [];

    // Fallback: detect first markdown table that looks like transactions and render a finviz table above the markdown.
    let skipFirstTable = false;
    if (!content.includes('```finviz')) {
      const fallback = buildFinvizFromMarkdownTable(content);
      if (fallback) {
        skipFirstTable = true;
        result.push(
          <div key="fallback-viz" className="my-2">
            <VizRenderer viz={fallback} />
          </div>
        );
      }
    }

    // Regular text part - render with markdown
    result.push(
    <div key={0} className="prose prose-sm max-w-none">
        <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
            // Customize link rendering
            a: ({ node, ...props }) => (
            <a {...props} className="text-gray-900 hover:text-gray-600 underline" />
            ),
            // Hide the original markdown table when we rendered a fallback viz for it
            table: ({ node, ...props }) => {
              if (skipFirstTable) {
                skipFirstTable = false;
                return null;
              }
              return <table className="min-w-full" {...props} />;
            },
            // Customize code rendering. Special-case `finviz` fences to render charts/tables.
            code: (mdProps: any) => {
              const { inline, className, children, ...props } = mdProps || {};
              if (inline) {
                return <code className="bg-gray-100 px-1 py-0.5 text-xs font-mono" {...props}>{children}</code>;
              }
              const lang = (className || '').toString();
              if (lang.includes('language-finviz')) {
                const raw = String(children || '').trim();
                const parsed = parseFinviz(raw);
                if (parsed && isValidFinviz(parsed)) {
                  return (
                    <div className="my-2">
                      <VizRenderer viz={parsed} />
                    </div>
                  );
                }
                // Fall back to raw if invalid
                return (
                  <pre className="text-xs bg-red-50 p-2 font-mono border border-red-200">
                    Invalid finviz spec. Showing raw:\n{raw}
                  </pre>
                );
              }
              return (
                <code className="block bg-gray-100 p-2 text-xs font-mono overflow-x-auto border border-gray-200" {...props}>
                  {children}
                </code>
              );
            },
            // Customize list rendering
            ul: ({ node, ...props }) => (
            <ul className="list-disc pl-5 space-y-1" {...props} />
            ),
            ol: ({ node, ...props }) => (
            <ol className="list-decimal pl-5 space-y-1" {...props} />
            ),
            // Customize paragraph spacing
            p: ({ node, ...props }) => (
            <p className="mb-2" {...props} />
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
    <div className="text-sm text-gray-900">
      {processContent(text.text)}
    </div>
  );
}

// Heuristic parser to build a finviz table from a markdown table with columns like Date, Merchant/Description/Payee, Amount, Category
function buildFinvizFromMarkdownTable(content: string) {
  const lines = content.split(/\r?\n/);
  for (let i = 0; i < lines.length - 2; i++) {
    const header = lines[i];
    const sep = lines[i + 1];
    if (!header.trim().startsWith('|')) continue;
    if (!(sep.trim().startsWith('|') && /[-:]/.test(sep))) continue;

    // Collect rows until a non-table line
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
    for (const r of dataRows.slice(0, 50)) { // cap rows for performance
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
  // Remove leading/trailing pipes and split
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
  // Require at minimum date and amount to qualify as transactions
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
    <div className="mb-3 p-3 bg-gray-50 border border-gray-200">
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center">
          <span className="text-xs font-semibold text-gray-600 uppercase tracking-wider">ASSISTANT</span>
          {message.metadata?.model && (
            <span className="ml-2 px-1 py-0.5 text-xs bg-gray-200 text-gray-600 font-mono">
              {message.metadata.model}
            </span>
          )}
        </div>
        <span className="text-xs text-gray-400">
          {formatTimestamp(message.timestamp)}
        </span>
      </div>
      
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
      
      {message.metadata && (
        <div className="mt-3">
          <button
            onClick={() => setShowMetadata(!showMetadata)}
            className="text-xs text-gray-600 hover:text-gray-900 flex items-center font-mono"
          >
            {showMetadata ? '[-]' : '[+]'} 
            <span className="ml-1">
              metadata
              {message.metadata.usage && (
                <span className="ml-1 text-gray-400">
                  ({message.metadata.usage.input_tokens}↓ / {message.metadata.usage.output_tokens}↑)
                </span>
              )}
            </span>
          </button>
          
          {showMetadata && (
            <div className="mt-2 p-2 bg-white border border-gray-200 text-xs">
              <pre className="overflow-x-auto whitespace-pre-wrap font-mono">
                {JSON.stringify(message.metadata, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
