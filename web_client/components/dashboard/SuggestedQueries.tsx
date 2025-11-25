import React, { useEffect, useState } from 'react';
import YAML from 'yaml';
import type { StructuredPrompt } from '../message/types';

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
        // fallback to empty (or we could hardcode defaults here if desired)
        if (isMounted) setSuggestions([]);
      }
    })();
    return () => { isMounted = false; };
  }, []);

  return (
    <div className="bg-white border border-gray-200 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold uppercase tracking-wider text-gray-700">Suggested Queries</div>
      </div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <button
            key={s.id}
            disabled={disabled}
            onClick={() => onSend(s.prompt)}
            className="px-3 py-1 text-xs bg-gray-900 text-white border border-gray-900 hover:bg-white hover:text-gray-900 disabled:opacity-40"
          >
            {s.title}
          </button>
        ))}
        {suggestions.length === 0 && (
          <span className="text-xs text-gray-500">No suggestions configured.</span>
        )}
      </div>
    </div>
  );
}
