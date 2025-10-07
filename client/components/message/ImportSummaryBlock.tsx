import React, { useMemo, useState } from 'react';
import type { ImportSummaryBlock } from './types';

const currency = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
});

function formatAmount(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  return currency.format(value);
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return `${minutes}m ${rem.toFixed(0)}s`;
}

interface ReviewDecision {
  id: string;
  status: 'pending' | 'accepted' | 'editing';
  category?: string;
  subcategory?: string;
}

interface ImportSummaryBlockRendererProps {
  block: ImportSummaryBlock;
  onSendMessage?: (message: string) => void;
}

export function ImportSummaryBlockRenderer({ block, onSendMessage }: ImportSummaryBlockRendererProps) {
  const { data } = block;
  const {
    csvCount,
    stagingDir,
    reviewPath,
    unsupported,
    missing,
    skippedUploads,
    extractionErrors,
    transactions,
    reviewItems,
    steps,
  } = data;

  console.log('[ImportSummaryBlock] Received data:', {
    csvCount,
    reviewItemsCount: reviewItems?.length ?? 0,
    reviewItems: reviewItems,
  });

  // Filter out invalid review items (where date is empty/n/a or ID is undefined/empty)
  const validReviewItems = useMemo(() => {
    const filtered = reviewItems
      .map((item) => {
        // Ensure a stable id so deduping/acceptance logic still functions
        const normalizedId = item.id && item.id !== 'undefined'
          ? String(item.id)
          : `${item.merchant ?? 'unknown'}::${item.date ?? 'unknown'}::${Number.isFinite(item.amount) ? item.amount : 'na'}`;

        return { ...item, id: normalizedId };
      })
      .filter(item => item.date && item.date !== 'n/a');

    const dedupedMap = new Map<string, { item: typeof filtered[number]; order: number }>();

    filtered.forEach((item, index) => {
      const key = `${item.id ?? 'unknown'}::${Number.isFinite(item.amount) ? item.amount : 'na'}`;
      const existing = dedupedMap.get(key);

      if (!existing) {
        dedupedMap.set(key, { item, order: index });
        return;
      }

      const currentHasSuggestion = Boolean(item.suggestedCategory || item.suggestedSubcategory);
      const existingHasSuggestion = Boolean(existing.item.suggestedCategory || existing.item.suggestedSubcategory);

      if (currentHasSuggestion && !existingHasSuggestion) {
        dedupedMap.set(key, { item, order: existing.order });
        return;
      }

      if (currentHasSuggestion && existingHasSuggestion) {
        const currentConfidence = item.confidence ?? 0;
        const existingConfidence = existing.item.confidence ?? 0;
        if (currentConfidence > existingConfidence) {
          dedupedMap.set(key, { item, order: existing.order });
        }
      }
    });

    const deduped = Array.from(dedupedMap.values())
      .sort((a, b) => a.order - b.order)
      .map(entry => entry.item);

    const dedupedWithFallback = deduped.length > 0 ? deduped : filtered;

    console.log('[ImportSummaryBlock] Valid review items:', filtered.length);
    console.log('[ImportSummaryBlock] Deduped review items:', dedupedWithFallback.length);
    console.log('[ImportSummaryBlock] Deduped items with suggestedCategory:', dedupedWithFallback.filter(i => i.suggestedCategory).length);
    if (dedupedWithFallback.length > 0) {
      console.log('[ImportSummaryBlock] First deduped review item:', dedupedWithFallback[0]);
    }

    return dedupedWithFallback;
  }, [reviewItems]);

  // State management for review decisions
  const [decisions, setDecisions] = useState<Map<string, ReviewDecision>>(new Map());

  const handleAccept = (item: typeof validReviewItems[0]) => {
    setDecisions(prev => {
      const next = new Map(prev);
      next.set(item.id, {
        id: item.id,
        status: 'accepted',
        category: item.suggestedCategory,
        subcategory: item.suggestedSubcategory,
      });
      return next;
    });
  };

  const handleEdit = (item: typeof validReviewItems[0]) => {
    setDecisions(prev => {
      const next = new Map(prev);
      next.set(item.id, {
        id: item.id,
        status: 'editing',
        category: item.suggestedCategory,
        subcategory: item.suggestedSubcategory,
      });
      return next;
    });
  };

  const handleEditChange = (itemId: string, field: 'category' | 'subcategory', value: string) => {
    setDecisions(prev => {
      const next = new Map(prev);
      const existing = next.get(itemId);
      if (existing) {
        next.set(itemId, { ...existing, [field]: value });
      }
      return next;
    });
  };

  const handleSaveEdit = (itemId: string) => {
    setDecisions(prev => {
      const next = new Map(prev);
      const existing = next.get(itemId);
      if (existing) {
        next.set(itemId, { ...existing, status: 'accepted' });
      }
      return next;
    });
  };

  const handleAcceptAll = () => {
    if (!onSendMessage) return;

    const allDecisions = validReviewItems
      .filter(item => item.suggestedCategory)
      .map(item => ({
        id: item.id,
        merchant: item.merchant,
        category: item.suggestedCategory!,
        subcategory: item.suggestedSubcategory!,
      }));

    const decisionsText = allDecisions.map(d => `- ID: ${d.id}, Merchant: "${d.merchant}", Category: ${d.category} → ${d.subcategory}`).join('\n');

    const reviewContext = reviewPath
      ? `Validate these ${allDecisions.length} categorization decisions from review file ${reviewPath}`
      : `Validate these ${allDecisions.length} categorization decisions`;

    const message = `${reviewContext}. Before applying anything, look up the existing category/subcategory catalog (for example via fin_query_sample(table="categories", limit=200)), suggest close matches when they exist, and ask me to confirm which option to use. Only run fin-enhance --apply-review after that confirmation. Decisions to review:\n${decisionsText}`;

    onSendMessage(message);
  };

  const handleDoneReviewing = () => {
    if (!onSendMessage) return;

    const acceptedDecisions = Array.from(decisions.values())
      .filter(d => d.status === 'accepted' && d.category)
      .map(d => {
        const item = validReviewItems.find(i => i.id === d.id);
        return {
          id: d.id,
          merchant: item?.merchant ?? 'unknown',
          category: d.category!,
          subcategory: d.subcategory ?? '',
        };
      });

    if (acceptedDecisions.length === 0) {
      return; // Nothing to do
    }

    const decisionsText = acceptedDecisions.map(d => `- ID: ${d.id}, Merchant: "${d.merchant}", Category: ${d.category}${d.subcategory ? ' → ' + d.subcategory : ''}`).join('\n');

    const reviewContext = reviewPath
      ? `Validate these ${acceptedDecisions.length} categorization decisions from review file ${reviewPath}`
      : `Validate these ${acceptedDecisions.length} categorization decisions`;

    const message = `${reviewContext}. Before applying anything, look up the existing category/subcategory catalog (for example via fin_query_sample(table="categories", limit=200)), suggest close matches when they exist, and ask me to confirm which option to use. Only run fin-enhance --apply-review after that confirmation. Decisions to review:\n${decisionsText}`;

    onSendMessage(message);
  };

  const getDecisionStatus = (itemId: string): ReviewDecision | undefined => {
    return decisions.get(itemId);
  };

  const hasAnyDecisions = decisions.size > 0;

  return (
    <div className="space-y-4 text-sm text-gray-900">
      <div className="space-y-1">
        <div className="font-semibold uppercase tracking-wider text-gray-700">Bulk Import Summary</div>
        <div>Processed <span className="font-semibold">{csvCount}</span> CSV file{csvCount === 1 ? '' : 's'}.</div>
      </div>

      {transactions.length > 0 && (
        <div>
          <div className="font-semibold text-xs uppercase tracking-wider text-gray-600">Imported Transactions (preview)</div>
          <div className="mt-2 max-h-64 overflow-auto border border-gray-200">
            <table className="min-w-full text-xs">
              <thead className="bg-gray-100 text-gray-600">
                <tr>
                  <th className="px-3 py-2 text-left">Date</th>
                  <th className="px-3 py-2 text-left">Merchant</th>
                  <th className="px-3 py-2 text-right">Amount</th>
                  <th className="px-3 py-2 text-left">Category</th>
                  <th className="px-3 py-2 text-left">Subcategory</th>
                  <th className="px-3 py-2 text-left">Account</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((txn, idx) => (
                  <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                    <td className="px-3 py-2 whitespace-nowrap">{txn.date}</td>
                    <td className="px-3 py-2">{txn.merchant}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatAmount(txn.amount)}</td>
                    <td className="px-3 py-2">{txn.category}</td>
                    <td className="px-3 py-2">{txn.subcategory}</td>
                    <td className="px-3 py-2">{txn.accountName ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {transactions.length >= 200 && (
            <div className="mt-1 text-xs text-gray-500">Showing first 200 transactions.</div>
          )}
        </div>
      )}

      {validReviewItems.length > 0 && (
        <div>
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold text-xs uppercase tracking-wider text-gray-600">
              Needs Review ({validReviewItems.length})
            </div>
            {onSendMessage && (
              <button
                onClick={handleAcceptAll}
                className="px-3 py-1 text-xs font-medium text-white bg-green-600 hover:bg-green-700 rounded transition-colors"
              >
                Accept All
              </button>
            )}
          </div>
          <div className="mt-2 space-y-2">
            {validReviewItems.map((item) => {
              const decision = getDecisionStatus(item.id);
              const isEditing = decision?.status === 'editing';
              const isAccepted = decision?.status === 'accepted';

              return (
                <div key={item.id} className={`border p-3 text-sm ${isAccepted ? 'border-green-300 bg-green-50' : 'border-amber-200 bg-amber-50'}`}>
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="font-semibold text-amber-900">{item.merchant}</div>
                      <div className="mt-1 text-xs text-gray-600">Date: {item.date}</div>

                      {isEditing ? (
                        <div className="mt-2 space-y-2">
                          <div>
                            <label className="block text-xs text-gray-600 mb-1">Category</label>
                            <input
                              type="text"
                              value={decision.category ?? ''}
                              onChange={(e) => handleEditChange(item.id, 'category', e.target.value)}
                              className="w-full px-2 py-1 text-xs border border-gray-300 rounded"
                              placeholder="e.g., Food & Dining"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-600 mb-1">Subcategory</label>
                            <input
                              type="text"
                              value={decision.subcategory ?? ''}
                              onChange={(e) => handleEditChange(item.id, 'subcategory', e.target.value)}
                              className="w-full px-2 py-1 text-xs border border-gray-300 rounded"
                              placeholder="e.g., Restaurants"
                            />
                          </div>
                        </div>
                      ) : (
                        <>
                          {item.suggestedCategory && (
                            <div className="mt-1 text-xs text-gray-700">
                              <span className="text-gray-500">{isAccepted ? 'Accepted:' : 'Suggested:'}</span>{' '}
                              <span className="font-medium">{decision?.category ?? item.suggestedCategory}</span>
                              {(decision?.subcategory ?? item.suggestedSubcategory) && (
                                <span> → {decision?.subcategory ?? item.suggestedSubcategory}</span>
                              )}
                              {!isAccepted && item.confidence !== undefined && (
                                <span className="ml-2 text-gray-500">
                                  ({Math.round(item.confidence * 100)}% confidence)
                                </span>
                              )}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                    <div className="ml-4 font-semibold text-amber-900">{formatAmount(item.amount)}</div>
                  </div>

                  {onSendMessage && !isAccepted && (
                    <div className="mt-2 flex gap-2">
                      {isEditing ? (
                        <>
                          <button
                            onClick={() => handleSaveEdit(item.id)}
                            className="px-3 py-1 text-xs font-medium text-white bg-green-600 hover:bg-green-700 rounded transition-colors"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setDecisions(prev => {
                              const next = new Map(prev);
                              next.delete(item.id);
                              return next;
                            })}
                            className="px-3 py-1 text-xs font-medium text-gray-700 bg-white hover:bg-gray-100 border border-gray-300 rounded transition-colors"
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          {item.suggestedCategory && (
                            <>
                              <button
                                onClick={() => handleAccept(item)}
                                className="px-3 py-1 text-xs font-medium text-white bg-green-600 hover:bg-green-700 rounded transition-colors"
                              >
                                Accept
                              </button>
                              <button
                                onClick={() => handleEdit(item)}
                                className="px-3 py-1 text-xs font-medium text-gray-700 bg-white hover:bg-gray-100 border border-gray-300 rounded transition-colors"
                              >
                                Edit
                              </button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  )}

                  {isAccepted && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-green-700">
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      <span>Ready to apply</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {(unsupported.length > 0 || missing.length > 0 || skippedUploads.length > 0 || extractionErrors.length > 0) && (
        <div className="space-y-1 text-xs">
          {unsupported.length > 0 && (
            <div className="text-gray-600">
              <span className="font-semibold">Unsupported inputs skipped:</span> {unsupported.join(', ')}
            </div>
          )}
          {missing.length > 0 && (
            <div className="text-gray-600">
              <span className="font-semibold">Missing paths:</span> {missing.join(', ')}
            </div>
          )}
          {skippedUploads.length > 0 && (
            <div className="text-gray-600">
              <span className="font-semibold">Skipped uploads:</span> {skippedUploads.join(', ')}
            </div>
          )}
          {extractionErrors.length > 0 && (
            <div className="text-red-700">
              <span className="font-semibold">Extraction issues:</span>
              <ul className="mt-1 list-disc pl-5">
                {extractionErrors.map((err, idx) => (
                  <li key={idx}>{err}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {validReviewItems.length > 0 && hasAnyDecisions && onSendMessage && (
        <div className="rounded-sm bg-blue-50 border border-blue-200 p-3 text-sm">
          <div className="flex justify-between items-center">
            <div className="text-gray-700">
              <span className="font-semibold text-blue-900">{Array.from(decisions.values()).filter(d => d.status === 'accepted').length}</span> of {validReviewItems.length} reviewed
            </div>
            <button
              onClick={handleDoneReviewing}
              disabled={!Array.from(decisions.values()).some(d => d.status === 'accepted')}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed rounded transition-colors"
            >
              Done Reviewing
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
