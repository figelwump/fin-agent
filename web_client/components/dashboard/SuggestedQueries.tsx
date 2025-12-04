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
        if (isMounted) setSuggestions([]);
      }
    })();
    return () => { isMounted = false; };
  }, []);

  if (suggestions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {suggestions.map((s) => (
        <button
          key={s.id}
          disabled={disabled}
          onClick={() => onSend(s.prompt)}
          className="chip"
        >
          {s.title}
        </button>
      ))}
    </div>
  );
}
