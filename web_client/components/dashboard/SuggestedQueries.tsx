import React, { useEffect, useState } from 'react';
import YAML from 'yaml';
import type { StructuredPrompt } from '../message/types';
import { Sparkles } from 'lucide-react';

type Suggestion = {
  id: string;
  title: string;
  prompt: string;
};

const DEFAULT_SUGGESTIONS: Suggestion[] = [];

export function SuggestedQueries({
  onSend,
  disabled,
}: {
  onSend: (prompt: StructuredPrompt | string) => void;
  disabled?: boolean;
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>(DEFAULT_SUGGESTIONS);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        const res = await fetch('/web_client/config/suggestions.yaml');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const text = await res.text();
        const doc = YAML.parse(text);
        if (isMounted && Array.isArray(doc)) {
          const cleaned = doc.filter((d) => d && d.id && d.title && d.prompt) as Suggestion[];
          setSuggestions(cleaned);
        }
      } catch {
        if (isMounted) setSuggestions([]);
      }
    })();
    return () => { isMounted = false; };
  }, []);

  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border-default)] p-4 md:p-5 relative overflow-hidden animate-fade-in">
      {/* Top accent line */}
      <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[var(--accent-primary)] to-transparent opacity-50" />

      <div className="flex items-center gap-2 mb-4">
        <Sparkles size={14} className="text-[var(--accent-warm)]" />
        <span className="text-xs font-mono font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
          Quick Queries
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {suggestions.map((s, index) => (
          <button
            key={s.id}
            disabled={disabled}
            onClick={() => onSend(s.prompt)}
            className="chip hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/5 disabled:opacity-40 disabled:cursor-not-allowed animate-fade-in"
            style={{ animationDelay: `${index * 0.05}s` }}
          >
            <span className="text-[var(--accent-primary)] font-mono text-xs">▸</span>
            {s.title}
          </button>
        ))}
        {suggestions.length === 0 && (
          <span className="text-sm text-[var(--text-muted)] font-mono">
            No suggestions configured
          </span>
        )}
      </div>
    </div>
  );
}
