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
    <div className="bg-white/10 backdrop-blur-md border border-white/20 p-4 md:p-5 rounded-2xl shadow-xl animate-fade-in-up w-full overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-semibold text-white/90">Suggested Queries</div>
      </div>
      <div className="flex flex-wrap gap-2 w-full">
        {suggestions.map((s, index) => (
          <button
            key={s.id}
            disabled={disabled}
            onClick={() => onSend(s.prompt)}
            className="px-4 py-2 text-sm bg-white/90 text-purple-700 font-medium rounded-full hover:bg-white hover:shadow-lg hover:scale-105 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 animate-fade-in"
            style={{ animationDelay: `${index * 0.05}s` }}
          >
            {s.title}
          </button>
        ))}
        {suggestions.length === 0 && (
          <span className="text-sm text-white/60">No suggestions configured.</span>
        )}
      </div>
    </div>
  );
}
