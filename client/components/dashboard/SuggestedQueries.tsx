import React, { useEffect, useState } from 'react';

type Suggestion = {
  id: string;
  title: string;
  prompt: string;
};

const DEFAULT_SUGGESTIONS: Suggestion[] = [
  {
    id: 'top-categories-30d',
    title: 'Top Spending Categories',
    prompt: 'Show my top spending categories for the last 30 days and include a finviz pie spec with category and amount data.',
  },
  {
    id: 'subscriptions',
    title: 'Subscriptions',
    prompt: 'Find my active subscriptions and include a finviz table spec with merchant, amount, cadence, and next charge date.',
  },
  {
    id: 'travel-ytd',
    title: 'Travel Year-to-Date',
    prompt: 'How much did I spend on travel this year? Include a finviz line or bar spec if helpful; otherwise a metric plus top merchants table.',
  },
  {
    id: 'restaurants-last-week',
    title: 'Where Did I Eat Last Week',
    prompt: 'Show my Food & Dining → Restaurants for the last 7 days. Include a finviz table with date, merchant, amount; also a pie by merchant if more than 3 merchants.',
  },
  {
    id: 'spending-trends-6m',
    title: 'Spending Trends (6m)',
    prompt: 'Show my monthly spending trends for the last 6 months and include a finviz line spec with date and amount.',
  },
];

function loadSuggestions(): Suggestion[] {
  try {
    const raw = localStorage.getItem('dashboard.suggestions');
    if (raw) return JSON.parse(raw);
  } catch {}
  return DEFAULT_SUGGESTIONS;
}

function saveSuggestions(s: Suggestion[]) {
  localStorage.setItem('dashboard.suggestions', JSON.stringify(s));
}

export function SuggestedQueries({
  onSend,
  disabled,
}: {
  onSend: (prompt: string) => void;
  disabled?: boolean;
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>(loadSuggestions());
  const [editing, setEditing] = useState(false);
  const [jsonText, setJsonText] = useState('');

  useEffect(() => {
    setJsonText(JSON.stringify(suggestions, null, 2));
  }, [editing]);

  const apply = () => {
    try {
      const parsed = JSON.parse(jsonText);
      if (Array.isArray(parsed)) {
        setSuggestions(parsed);
        saveSuggestions(parsed);
        setEditing(false);
      }
    } catch {}
  };

  const reset = () => {
    setSuggestions(DEFAULT_SUGGESTIONS);
    saveSuggestions(DEFAULT_SUGGESTIONS);
  };

  return (
    <div className="bg-white border border-gray-200 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold uppercase tracking-wider text-gray-700">Suggested Queries</div>
        <div className="flex items-center gap-2">
          <button className="text-xs text-gray-600 hover:text-gray-900 underline" onClick={() => setEditing((e) => !e)}>
            {editing ? 'Close' : 'Configure'}
          </button>
          <button className="text-xs text-gray-600 hover:text-gray-900 underline" onClick={reset}>
            Reset
          </button>
        </div>
      </div>
      {!editing ? (
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
        </div>
      ) : (
        <div>
          <p className="text-xs text-gray-600 mb-1">Edit as a JSON array of objects with keys: id, title, prompt.</p>
          <textarea
            className="w-full h-40 border border-gray-300 p-2 text-xs font-mono"
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <button className="px-3 py-1 text-xs bg-gray-900 text-white border border-gray-900 hover:bg-white hover:text-gray-900" onClick={apply}>
              Save
            </button>
            <button className="px-3 py-1 text-xs border border-gray-300" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
