import React, { useMemo, useState } from 'react';
import type { ImportSummaryBlock, StructuredPrompt } from './types';
import { CheckCircle, Edit3, Sparkles, AlertTriangle } from 'lucide-react';

const currency = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
});

function formatAmount(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  return currency.format(value);
}

interface ReviewDecision {
  id: string;
  status: 'pending' | 'accepted' | 'editing';
  category?: string;
  subcategory?: string;
}

interface ImportSummaryBlockRendererProps {
  block: ImportSummaryBlock;
  onSendMessage?: (message: StructuredPrompt | string) => void;
}

export function ImportSummaryBlockRenderer({ block, onSendMessage }: ImportSummaryBlockRendererProps) {
  const { data } = block;
  const {
    csvCount,
    reviewPath,
    unsupported,
    missing,
    skippedUploads,
    extractionErrors,
    transactions,
    reviewItems,
  } = data;

  const validReviewItems = useMemo(() => {
    const filtered = reviewItems
      .map((item) => {
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

    return deduped.length > 0 ? deduped : filtered;
  }, [reviewItems]);

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

  const handleSuggestCategory = (item: typeof validReviewItems[0]) => {
    if (!onSendMessage) return;

    const transactionPayload = {
      id: item.id,
      merchant: item.merchant,
      date: item.date,
      amount: item.amount,
      originalDescription: item.originalDescription,
      accountId: item.accountId,
    };

    onSendMessage({
      displayText: `Suggest a category for ${item.merchant} (${item.date}, ${formatAmount(item.amount)}).`,
      agentText: [
        'You are assisting with a manual categorization review. Suggest one or two category/subcategory pairs for the transaction below.',
        'Prioritize matches from the existing taxonomy whenever possible. If nothing fits, note the closest alternative and call out the gap.',
        'Do not apply any review decisions or run fin-enhance. Respond with concise suggestions and reasoning only.',
        'TRANSACTION JSON:',
        JSON.stringify(transactionPayload, null, 2),
      ].join('\n'),
      metadata: {
        action: 'request_category_suggestion',
        transaction: transactionPayload,
      },
    });
  };

  type ReviewDecisionPayload = {
    id: string;
    merchant: string;
    category: string;
    subcategory?: string;
  };

  const buildReviewPrompt = (decisionsList: ReviewDecisionPayload[], source: 'accept_all' | 'done_reviewing'): StructuredPrompt => {
    const headline = source === 'accept_all'
      ? `Please double-check ${decisionsList.length} suggested categor${decisionsList.length === 1 ? 'y' : 'ies'} before we apply them.`
      : `Here are ${decisionsList.length} categor${decisionsList.length === 1 ? 'y' : 'ies'} I just reviewed - please validate before applying.`;

    const preview = decisionsList.slice(0, 3).map(decision => {
      const subLabel = decision.subcategory ? ` → ${decision.subcategory}` : '';
      return `- ${decision.merchant}: ${decision.category}${subLabel}`;
    });

    const remainingCount = decisionsList.length - preview.length;
    const remainderLine = remainingCount > 0 ? `- ...and ${remainingCount} more.` : undefined;

    const displayLines = [headline, '', ...preview];
    if (remainderLine) displayLines.push(remainderLine);

    const agentMetadata = {
      action: 'review_decisions' as const,
      source,
      reviewPath,
      decisions: decisionsList,
    };

    return {
      displayText: displayLines.join('\n'),
      agentText: [
        'Validate the following categorization decisions before applying them.',
        'Steps:',
        '- Query the existing category catalog (for example: fin_query_sample(table="categories", limit=200)).',
        '- Suggest close matches for any new labels and confirm the final choice with the user.',
        '- Once confirmed, create the decisions JSON file and run fin-enhance --apply-review to apply it.',
        'Decisions payload:',
        JSON.stringify(agentMetadata, null, 2),
      ].join('\n'),
      metadata: agentMetadata,
    };
  };

  const handleAcceptAll = () => {
    if (!onSendMessage) return;
    const allDecisions = validReviewItems
      .filter(item => item.suggestedCategory)
      .map(item => ({
        id: item.id,
        merchant: item.merchant,
        category: item.suggestedCategory!,
        subcategory: item.suggestedSubcategory ?? undefined,
      }));
    if (allDecisions.length === 0) return;
    onSendMessage(buildReviewPrompt(allDecisions, 'accept_all'));
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
          subcategory: d.subcategory ?? undefined,
        };
      });
    if (acceptedDecisions.length === 0) return;
    onSendMessage(buildReviewPrompt(acceptedDecisions, 'done_reviewing'));
  };

  const getDecisionStatus = (itemId: string): ReviewDecision | undefined => decisions.get(itemId);
  const hasAnyDecisions = decisions.size > 0;

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="card p-4">
        <h3 className="font-display text-lg text-[var(--text-primary)] mb-1">Import Summary</h3>
        <p className="text-[var(--text-secondary)]">
          Processed <span className="font-semibold text-[var(--accent-primary)]">{csvCount}</span> CSV file{csvCount === 1 ? '' : 's'}.
        </p>
      </div>

      {/* Transactions preview */}
      {transactions.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border-light)] bg-[var(--bg-tertiary)]">
            <h4 className="font-medium text-sm text-[var(--text-primary)]">Imported Transactions</h4>
          </div>
          <div className="max-h-64 overflow-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-[var(--bg-tertiary)] sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide">Date</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide">Merchant</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide">Amount</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide">Category</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((txn, idx) => (
                  <tr key={idx} className="border-t border-[var(--border-light)] hover:bg-[var(--bg-tertiary)]">
                    <td className="px-4 py-2 text-[var(--text-primary)]">{txn.date}</td>
                    <td className="px-4 py-2 text-[var(--text-primary)]">{txn.merchant}</td>
                    <td className="px-4 py-2 text-right text-[var(--text-primary)] tabular-nums">{formatAmount(txn.amount)}</td>
                    <td className="px-4 py-2 text-[var(--text-secondary)]">{txn.category}{txn.subcategory ? ` → ${txn.subcategory}` : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {transactions.length >= 200 && (
            <div className="px-4 py-2 text-xs text-[var(--text-muted)] border-t border-[var(--border-light)]">
              Showing first 200 transactions.
            </div>
          )}
        </div>
      )}

      {/* Review items */}
      {validReviewItems.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border-light)] bg-[var(--accent-warm)]/5 flex justify-between items-center">
            <h4 className="font-medium text-sm text-[var(--accent-warm)]">
              Needs Review ({validReviewItems.length})
            </h4>
            {onSendMessage && (
              <button onClick={handleAcceptAll} className="btn-primary px-3 py-1.5 text-xs">
                Accept all
              </button>
            )}
          </div>
          <div className="divide-y divide-[var(--border-light)]">
            {validReviewItems.map((item) => {
              const decision = getDecisionStatus(item.id);
              const isEditing = decision?.status === 'editing';
              const isAccepted = decision?.status === 'accepted';

              return (
                <div key={item.id} className={`p-4 ${isAccepted ? 'bg-green-50' : ''}`}>
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="font-medium text-[var(--text-primary)]">{item.merchant}</div>
                      <div className="text-sm text-[var(--text-muted)]">{item.date}</div>

                      {isEditing ? (
                        <div className="mt-3 space-y-2">
                          <input
                            type="text"
                            value={decision.category ?? ''}
                            onChange={(e) => handleEditChange(item.id, 'category', e.target.value)}
                            className="w-full px-3 py-2 text-sm input-field"
                            placeholder="Category"
                          />
                          <input
                            type="text"
                            value={decision.subcategory ?? ''}
                            onChange={(e) => handleEditChange(item.id, 'subcategory', e.target.value)}
                            className="w-full px-3 py-2 text-sm input-field"
                            placeholder="Subcategory (optional)"
                          />
                        </div>
                      ) : item.suggestedCategory ? (
                        <div className="mt-1 text-sm">
                          <span className="text-[var(--text-muted)]">{isAccepted ? 'Accepted:' : 'Suggested:'}</span>{' '}
                          <span className="font-medium text-[var(--accent-primary)]">{decision?.category ?? item.suggestedCategory}</span>
                          {(decision?.subcategory ?? item.suggestedSubcategory) && (
                            <span className="text-[var(--text-muted)]"> → {decision?.subcategory ?? item.suggestedSubcategory}</span>
                          )}
                          {!isAccepted && item.confidence !== undefined && (
                            <span className="ml-1 text-[var(--text-muted)]">({Math.round(item.confidence * 100)}%)</span>
                          )}
                        </div>
                      ) : null}
                    </div>
                    <div className="font-medium text-[var(--text-primary)] tabular-nums">{formatAmount(item.amount)}</div>
                  </div>

                  {onSendMessage && !isAccepted && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {isEditing ? (
                        <>
                          <button onClick={() => handleSaveEdit(item.id)} className="btn-primary px-3 py-1.5 text-xs flex items-center gap-1">
                            <CheckCircle size={12} /> Save
                          </button>
                          <button onClick={() => setDecisions(prev => { const next = new Map(prev); next.delete(item.id); return next; })} className="btn-secondary px-3 py-1.5 text-xs">
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          {item.suggestedCategory && (
                            <>
                              <button onClick={() => handleAccept(item)} className="btn-primary px-3 py-1.5 text-xs flex items-center gap-1">
                                <CheckCircle size={12} /> Accept
                              </button>
                              <button onClick={() => handleEdit(item)} className="btn-secondary px-3 py-1.5 text-xs flex items-center gap-1">
                                <Edit3 size={12} /> Edit
                              </button>
                            </>
                          )}
                          <button onClick={() => handleSuggestCategory(item)} className="btn-secondary px-3 py-1.5 text-xs flex items-center gap-1">
                            <Sparkles size={12} /> Suggest
                          </button>
                        </>
                      )}
                    </div>
                  )}

                  {isAccepted && (
                    <div className="mt-2 flex items-center gap-1 text-xs text-[#4a7c59]">
                      <CheckCircle size={14} /> Ready to apply
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Warnings */}
      {(unsupported.length > 0 || missing.length > 0 || skippedUploads.length > 0 || extractionErrors.length > 0) && (
        <div className="card p-4 space-y-2">
          {unsupported.length > 0 && (
            <div className="flex items-start gap-2 text-sm">
              <AlertTriangle size={16} className="text-[var(--accent-warm)] flex-shrink-0 mt-0.5" />
              <span className="text-[var(--text-secondary)]"><strong>Unsupported:</strong> {unsupported.join(', ')}</span>
            </div>
          )}
          {missing.length > 0 && (
            <div className="flex items-start gap-2 text-sm">
              <AlertTriangle size={16} className="text-[var(--accent-warm)] flex-shrink-0 mt-0.5" />
              <span className="text-[var(--text-secondary)]"><strong>Missing:</strong> {missing.join(', ')}</span>
            </div>
          )}
          {skippedUploads.length > 0 && (
            <div className="flex items-start gap-2 text-sm">
              <AlertTriangle size={16} className="text-[var(--accent-warm)] flex-shrink-0 mt-0.5" />
              <span className="text-[var(--text-secondary)]"><strong>Skipped:</strong> {skippedUploads.join(', ')}</span>
            </div>
          )}
          {extractionErrors.length > 0 && (
            <div className="flex items-start gap-2 text-sm text-[var(--accent-danger)]">
              <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
              <div>
                <strong>Errors:</strong>
                <ul className="mt-1 list-disc pl-4 text-[var(--text-secondary)]">
                  {extractionErrors.map((err, idx) => <li key={idx}>{err}</li>)}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Done reviewing */}
      {validReviewItems.length > 0 && hasAnyDecisions && onSendMessage && (
        <div className="card p-4 bg-[var(--accent-primary-light)] flex justify-between items-center">
          <span className="text-sm text-[var(--text-secondary)]">
            <span className="font-semibold text-[var(--accent-primary)]">
              {Array.from(decisions.values()).filter(d => d.status === 'accepted').length}
            </span> of {validReviewItems.length} reviewed
          </span>
          <button
            onClick={handleDoneReviewing}
            disabled={!Array.from(decisions.values()).some(d => d.status === 'accepted')}
            className="btn-primary px-4 py-2 text-sm disabled:opacity-50"
          >
            Done reviewing
          </button>
        </div>
      )}
    </div>
  );
}
