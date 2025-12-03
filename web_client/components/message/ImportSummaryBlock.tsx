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

  // Filter out invalid review items
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

    const displayText = `Suggest a category for ${item.merchant} (${item.date}, ${formatAmount(item.amount)}).`;

    const agentInstructions = [
      'You are assisting with a manual categorization review. Suggest one or two category/subcategory pairs for the transaction below.',
      'Prioritize matches from the existing taxonomy whenever possible. If nothing fits, note the closest alternative and call out the gap.',
      'Do not apply any review decisions or run fin-enhance. Respond with concise suggestions and reasoning only.',
      'TRANSACTION JSON:',
      JSON.stringify(transactionPayload, null, 2),
    ].join('\n');

    onSendMessage({
      displayText,
      agentText: agentInstructions,
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

  const buildReviewPrompt = (decisions: ReviewDecisionPayload[], source: 'accept_all' | 'done_reviewing'): StructuredPrompt => {
    const headline = source === 'accept_all'
      ? `Please double-check ${decisions.length} suggested categor${decisions.length === 1 ? 'y' : 'ies'} before we apply them.`
      : `Here are ${decisions.length} categor${decisions.length === 1 ? 'y' : 'ies'} I just reviewed - please validate before applying.`;

    const preview = decisions.slice(0, 3).map(decision => {
      const subLabel = decision.subcategory ? ` -> ${decision.subcategory}` : '';
      return `- ${decision.merchant}: ${decision.category}${subLabel}`;
    });

    const remainingCount = decisions.length - preview.length;
    const remainderLine = remainingCount > 0
      ? `- ...and ${remainingCount} more.`
      : undefined;

    const displayLines = [headline, '', ...preview];
    if (remainderLine) {
      displayLines.push(remainderLine);
    }

    const agentMetadata = {
      action: 'review_decisions' as const,
      source,
      reviewPath,
      decisions,
    };

    const agentInstructions = [
      'Validate the following categorization decisions before applying them.',
      'Steps:',
      '- Query the existing category catalog (for example: fin_query_sample(table="categories", limit=200)).',
      '- Suggest close matches for any new labels and confirm the final choice with the user.',
      '- Once confirmed, create the decisions JSON file and run fin-enhance --apply-review to apply it.',
      'Decisions payload:',
      JSON.stringify(agentMetadata, null, 2),
    ].join('\n');

    return {
      displayText: displayLines.join('\n'),
      agentText: agentInstructions,
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

    if (allDecisions.length === 0) {
      return;
    }

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

    if (acceptedDecisions.length === 0) {
      return;
    }

    onSendMessage(buildReviewPrompt(acceptedDecisions, 'done_reviewing'));
  };

  const getDecisionStatus = (itemId: string): ReviewDecision | undefined => {
    return decisions.get(itemId);
  };

  const hasAnyDecisions = decisions.size > 0;

  return (
    <div className="space-y-4 text-sm">
      {/* Header */}
      <div className="space-y-1">
        <div className="font-mono font-semibold text-xs uppercase tracking-wider text-[var(--accent-primary)]">
          Bulk Import Summary
        </div>
        <div className="text-[var(--text-primary)]">
          Processed <span className="font-semibold text-[var(--accent-primary)]">{csvCount}</span> CSV file{csvCount === 1 ? '' : 's'}.
        </div>
      </div>

      {/* Transactions table */}
      {transactions.length > 0 && (
        <div>
          <div className="font-mono font-semibold text-xs uppercase tracking-wider text-[var(--text-muted)] mb-2">
            Imported Transactions (preview)
          </div>
          <div className="max-h-64 overflow-auto border border-[var(--border-default)]">
            <table className="min-w-full text-xs">
              <thead className="bg-[var(--bg-elevated)] sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left font-mono text-[var(--accent-primary)] uppercase tracking-wider">Date</th>
                  <th className="px-3 py-2 text-left font-mono text-[var(--accent-primary)] uppercase tracking-wider">Merchant</th>
                  <th className="px-3 py-2 text-right font-mono text-[var(--accent-primary)] uppercase tracking-wider">Amount</th>
                  <th className="px-3 py-2 text-left font-mono text-[var(--accent-primary)] uppercase tracking-wider">Category</th>
                  <th className="px-3 py-2 text-left font-mono text-[var(--accent-primary)] uppercase tracking-wider">Sub</th>
                  <th className="px-3 py-2 text-left font-mono text-[var(--accent-primary)] uppercase tracking-wider">Account</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((txn, idx) => (
                  <tr key={idx} className={`border-t border-[var(--border-subtle)] ${idx % 2 === 0 ? 'bg-[var(--bg-tertiary)]' : 'bg-[var(--bg-secondary)]'}`}>
                    <td className="px-3 py-2 whitespace-nowrap text-[var(--text-primary)]">{txn.date}</td>
                    <td className="px-3 py-2 text-[var(--text-primary)]">{txn.merchant}</td>
                    <td className="px-3 py-2 text-right font-mono text-[var(--text-primary)]">{formatAmount(txn.amount)}</td>
                    <td className="px-3 py-2 text-[var(--text-secondary)]">{txn.category}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{txn.subcategory}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{txn.accountName ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {transactions.length >= 200 && (
            <div className="mt-1 text-xs text-[var(--text-muted)] font-mono">Showing first 200 transactions.</div>
          )}
        </div>
      )}

      {/* Review items */}
      {validReviewItems.length > 0 && (
        <div>
          <div className="flex justify-between items-center mb-3">
            <div className="font-mono font-semibold text-xs uppercase tracking-wider text-[var(--accent-warm)]">
              Needs Review ({validReviewItems.length})
            </div>
            {onSendMessage && (
              <button
                onClick={handleAcceptAll}
                className="px-3 py-1.5 text-xs font-mono font-semibold text-[var(--bg-primary)] bg-[var(--accent-secondary)] hover:bg-[var(--accent-secondary)]/90 transition-colors"
              >
                ACCEPT ALL
              </button>
            )}
          </div>
          <div className="space-y-2">
            {validReviewItems.map((item) => {
              const decision = getDecisionStatus(item.id);
              const isEditing = decision?.status === 'editing';
              const isAccepted = decision?.status === 'accepted';

              return (
                <div key={item.id} className={`border p-3 ${
                  isAccepted
                    ? 'border-[var(--accent-secondary)]/30 bg-[var(--accent-secondary)]/5'
                    : 'border-[var(--accent-warm)]/30 bg-[var(--accent-warm)]/5'
                }`}>
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="font-semibold text-[var(--text-primary)]">{item.merchant}</div>
                      <div className="mt-1 text-xs text-[var(--text-muted)] font-mono">
                        DATE: {item.date}
                      </div>

                      {isEditing ? (
                        <div className="mt-2 space-y-2">
                          <div>
                            <label className="block text-xs text-[var(--text-muted)] font-mono mb-1">CATEGORY</label>
                            <input
                              type="text"
                              value={decision.category ?? ''}
                              onChange={(e) => handleEditChange(item.id, 'category', e.target.value)}
                              className="w-full px-2 py-1.5 text-xs terminal-input"
                              placeholder="e.g., Food & Dining"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-[var(--text-muted)] font-mono mb-1">SUBCATEGORY</label>
                            <input
                              type="text"
                              value={decision.subcategory ?? ''}
                              onChange={(e) => handleEditChange(item.id, 'subcategory', e.target.value)}
                              className="w-full px-2 py-1.5 text-xs terminal-input"
                              placeholder="e.g., Restaurants"
                            />
                          </div>
                        </div>
                      ) : (
                        <>
                          {item.suggestedCategory && (
                            <div className="mt-1 text-xs text-[var(--text-secondary)]">
                              <span className="text-[var(--text-muted)]">{isAccepted ? 'ACCEPTED:' : 'SUGGESTED:'}</span>{' '}
                              <span className="font-medium text-[var(--accent-primary)]">{decision?.category ?? item.suggestedCategory}</span>
                              {(decision?.subcategory ?? item.suggestedSubcategory) && (
                                <span className="text-[var(--text-muted)]"> → {decision?.subcategory ?? item.suggestedSubcategory}</span>
                              )}
                              {!isAccepted && item.confidence !== undefined && (
                                <span className="ml-2 text-[var(--text-muted)]">
                                  ({Math.round(item.confidence * 100)}%)
                                </span>
                              )}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                    <div className="ml-4 font-mono font-semibold text-[var(--text-primary)]">{formatAmount(item.amount)}</div>
                  </div>

                  {onSendMessage && !isAccepted && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {isEditing ? (
                        <>
                          <button
                            onClick={() => handleSaveEdit(item.id)}
                            className="px-3 py-1.5 text-xs font-mono text-[var(--bg-primary)] bg-[var(--accent-secondary)] hover:bg-[var(--accent-secondary)]/90 transition-colors flex items-center gap-1"
                          >
                            <CheckCircle size={12} /> SAVE
                          </button>
                          <button
                            onClick={() => setDecisions(prev => {
                              const next = new Map(prev);
                              next.delete(item.id);
                              return next;
                            })}
                            className="btn-secondary px-3 py-1.5 text-xs font-mono"
                          >
                            CANCEL
                          </button>
                          <button
                            onClick={() => handleSuggestCategory(item)}
                            className="px-3 py-1.5 text-xs font-mono text-[var(--bg-primary)] bg-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/90 transition-colors flex items-center gap-1"
                          >
                            <Sparkles size={12} /> SUGGEST
                          </button>
                        </>
                      ) : (
                        <>
                          {item.suggestedCategory && (
                            <>
                              <button
                                onClick={() => handleAccept(item)}
                                className="px-3 py-1.5 text-xs font-mono text-[var(--bg-primary)] bg-[var(--accent-secondary)] hover:bg-[var(--accent-secondary)]/90 transition-colors flex items-center gap-1"
                              >
                                <CheckCircle size={12} /> ACCEPT
                              </button>
                              <button
                                onClick={() => handleEdit(item)}
                                className="btn-secondary px-3 py-1.5 text-xs font-mono flex items-center gap-1"
                              >
                                <Edit3 size={12} /> EDIT
                              </button>
                            </>
                          )}
                          <button
                            onClick={() => handleSuggestCategory(item)}
                            className="px-3 py-1.5 text-xs font-mono text-[var(--bg-primary)] bg-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/90 transition-colors flex items-center gap-1"
                          >
                            <Sparkles size={12} /> SUGGEST
                          </button>
                        </>
                      )}
                    </div>
                  )}

                  {isAccepted && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-[var(--accent-secondary)] font-mono">
                      <CheckCircle size={14} />
                      <span>READY TO APPLY</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Errors and warnings */}
      {(unsupported.length > 0 || missing.length > 0 || skippedUploads.length > 0 || extractionErrors.length > 0) && (
        <div className="space-y-2 text-xs">
          {unsupported.length > 0 && (
            <div className="flex items-start gap-2 text-[var(--text-muted)]">
              <AlertTriangle size={14} className="text-[var(--accent-warm)] flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-mono text-[var(--accent-warm)]">UNSUPPORTED:</span> {unsupported.join(', ')}
              </div>
            </div>
          )}
          {missing.length > 0 && (
            <div className="flex items-start gap-2 text-[var(--text-muted)]">
              <AlertTriangle size={14} className="text-[var(--accent-warm)] flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-mono text-[var(--accent-warm)]">MISSING:</span> {missing.join(', ')}
              </div>
            </div>
          )}
          {skippedUploads.length > 0 && (
            <div className="flex items-start gap-2 text-[var(--text-muted)]">
              <AlertTriangle size={14} className="text-[var(--accent-warm)] flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-mono text-[var(--accent-warm)]">SKIPPED:</span> {skippedUploads.join(', ')}
              </div>
            </div>
          )}
          {extractionErrors.length > 0 && (
            <div className="flex items-start gap-2 text-[var(--accent-danger)]">
              <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-mono">ERRORS:</span>
                <ul className="mt-1 list-none space-y-1">
                  {extractionErrors.map((err, idx) => (
                    <li key={idx} className="text-[var(--text-muted)]">• {err}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Done reviewing button */}
      {validReviewItems.length > 0 && hasAnyDecisions && onSendMessage && (
        <div className="border border-[var(--accent-primary)]/30 bg-[var(--accent-primary)]/5 p-3">
          <div className="flex justify-between items-center">
            <div className="text-[var(--text-secondary)]">
              <span className="font-semibold text-[var(--accent-primary)]">{Array.from(decisions.values()).filter(d => d.status === 'accepted').length}</span> of {validReviewItems.length} reviewed
            </div>
            <button
              onClick={handleDoneReviewing}
              disabled={!Array.from(decisions.values()).some(d => d.status === 'accepted')}
              className="px-4 py-2 text-sm font-mono font-semibold text-[var(--bg-primary)] bg-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/90 disabled:bg-[var(--text-muted)] disabled:cursor-not-allowed transition-colors"
            >
              DONE REVIEWING
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
