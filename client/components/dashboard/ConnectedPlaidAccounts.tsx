import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ChevronDown, ChevronUp, RefreshCcw } from "lucide-react";
import { PlaidLinkButton } from "./PlaidLinkButton";

interface PlaidItemSummary {
  item_id: string;
  institution_id: string | null;
  institution_name: string | null;
  account_count: number;
  created_at: string;
  updated_at: string;
}

interface PlaidAccountSummary {
  account_id: string;
  display_name: string;
  account_type: string;
  name?: string | null;
  official_name?: string | null;
  mask?: string | null;
  type?: string | null;
  subtype?: string | null;
  account_key: string;
}

interface FetchSummary {
  fetchedAt: string;
  totalTransactions: number;
  reviewCount: number;
  preview: Array<{ date: string; merchant: string; amount: number; accountName?: string }>;
}

interface ConnectedPlaidAccountsProps {
  disabled?: boolean;
}

const DEFAULT_LOOKBACK_DAYS = 30;

function isoDateFrom(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function defaultDateRange(): { start: string; end: string } {
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - DEFAULT_LOOKBACK_DAYS);
  return {
    start: isoDateFrom(startDate),
    end: isoDateFrom(endDate),
  };
}

function formatTimestamp(timestamp: string): string {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleString();
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(amount);
}

export function ConnectedPlaidAccounts({ disabled = false }: ConnectedPlaidAccountsProps) {
  const [items, setItems] = useState<PlaidItemSummary[]>([]);
  const [itemsError, setItemsError] = useState<string | null>(null);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [expandedItem, setExpandedItem] = useState<string | null>(null);
  const [accountDetails, setAccountDetails] = useState<Record<string, { loading: boolean; error?: string; accounts?: PlaidAccountSummary[] }>>({});
  const [refreshing, setRefreshing] = useState<Record<string, boolean>>({});
  const [fetchSummaries, setFetchSummaries] = useState<Record<string, FetchSummary>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const reloadItems = useCallback(async () => {
    setItemsLoading(true);
    setItemsError(null);
    try {
      const response = await fetch("/api/plaid/items");
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Failed to load Plaid items");
      }
      const data = await response.json();
      setItems(Array.isArray(data.items) ? data.items : []);
    } catch (error: any) {
      setItemsError(error?.message ?? "Unable to load Plaid connections");
      setItems([]);
    } finally {
      setItemsLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadItems();
  }, [reloadItems]);

  const handleItemConnected = useCallback(async () => {
    await reloadItems();
    setActionError(null);
  }, [reloadItems]);

  const handleLinkError = useCallback((message: string) => {
    setActionError(message || null);
  }, []);

  const toggleAccounts = useCallback(async (itemId: string) => {
    const isExpanding = expandedItem !== itemId;
    setExpandedItem(isExpanding ? itemId : null);
    setActionError(null);

    if (!isExpanding) {
      return;
    }

    setAccountDetails((prev) => {
      if (prev[itemId]?.accounts || prev[itemId]?.loading) {
        return prev;
      }
      return {
        ...prev,
        [itemId]: { loading: true },
      };
    });

    if (accountDetails[itemId]?.accounts || accountDetails[itemId]?.loading) {
      return;
    }

    try {
      const response = await fetch(`/api/plaid/accounts?item_id=${encodeURIComponent(itemId)}`);
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Failed to load Plaid accounts");
      }
      const data = await response.json();
      setAccountDetails((prev) => ({
        ...prev,
        [itemId]: {
          loading: false,
          accounts: Array.isArray(data.accounts) ? data.accounts : [],
        },
      }));
    } catch (error: any) {
      setAccountDetails((prev) => ({
        ...prev,
        [itemId]: {
          loading: false,
          error: error?.message ?? "Unable to load accounts",
        },
      }));
      setActionError(error?.message ?? "Unable to load accounts");
    }
  }, [accountDetails, expandedItem]);

  const handleRefresh = useCallback(async (itemId: string) => {
    const { start, end } = defaultDateRange();
    setRefreshing((prev) => ({ ...prev, [itemId]: true }));
    setActionError(null);

    try {
      const response = await fetch("/api/plaid/fetch", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          item_id: itemId,
          start,
          end,
          autoApprove: true,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Plaid refresh failed");
      }

      const data = await response.json();
      const preview = Array.isArray(data.transactionsPreview) ? data.transactionsPreview.slice(0, 3) : [];
      const reviewCount = Array.isArray(data.reviewItems) ? data.reviewItems.length : 0;

      setFetchSummaries((prev) => ({
        ...prev,
        [itemId]: {
          fetchedAt: new Date().toISOString(),
          totalTransactions: Number(data.totalTransactions) || preview.length,
          reviewCount,
          preview,
        },
      }));

      await reloadItems();
    } catch (error: any) {
      setActionError(error?.message ?? "Plaid refresh failed");
    } finally {
      setRefreshing((prev) => ({ ...prev, [itemId]: false }));
    }
  }, [reloadItems]);

  const emptyState = useMemo(() => !itemsLoading && items.length === 0, [items, itemsLoading]);

  return (
    <div className="rounded-sm border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-semibold uppercase tracking-wider text-gray-600">Connected Accounts</p>
          <p className="text-[11px] text-gray-500">Sync Plaid data directly into fin-enhance</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void reloadItems()}
            disabled={itemsLoading}
            className="inline-flex items-center gap-1 rounded-sm border border-gray-400 px-2 py-1 text-[11px] font-medium uppercase tracking-wider text-gray-600 transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCcw size={12} />
            {itemsLoading ? "Refreshing" : "Reload"}
          </button>
          <PlaidLinkButton disabled={disabled} onConnected={handleItemConnected} onError={handleLinkError} />
        </div>
      </div>

      {itemsError && (
        <div className="mt-2 inline-flex items-center gap-1 rounded-sm border border-red-300 bg-red-50 px-2 py-1 text-[11px] text-red-700">
          <AlertCircle size={12} />
          {itemsError}
        </div>
      )}

      {actionError && !itemsError && (
        <div className="mt-2 inline-flex items-center gap-1 rounded-sm border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] text-amber-700">
          <AlertCircle size={12} />
          {actionError}
        </div>
      )}

      {itemsLoading && (
        <p className="mt-3 text-[11px] text-gray-500">Loading Plaid connections…</p>
      )}

      {emptyState && (
        <p className="mt-3 text-[11px] text-gray-500">No Plaid accounts linked yet. Connect your first account to start importing data.</p>
      )}

      {items.map((item) => {
        const summary = fetchSummaries[item.item_id];
        const accountsState = accountDetails[item.item_id];
        const isExpanded = expandedItem === item.item_id;
        return (
          <div key={item.item_id} className="mt-3 rounded-sm border border-gray-200 bg-white p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-semibold text-gray-800">{item.institution_name || "Plaid Item"}</p>
                <p className="text-[11px] text-gray-500">
                  {item.account_count} {item.account_count === 1 ? "account" : "accounts"} • Last sync {formatTimestamp(item.updated_at)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleRefresh(item.item_id)}
                  disabled={disabled || refreshing[item.item_id] === true}
                  className="inline-flex items-center gap-1 rounded-sm border border-blue-500 px-2 py-1 text-[11px] font-medium uppercase tracking-wider text-blue-600 transition-colors hover:bg-blue-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <RefreshCcw size={12} />
                  {refreshing[item.item_id] ? "Syncing" : "Refresh Data"}
                </button>
                <button
                  type="button"
                  onClick={() => void toggleAccounts(item.item_id)}
                  className="inline-flex items-center gap-1 rounded-sm border border-gray-300 px-2 py-1 text-[11px] font-medium uppercase tracking-wider text-gray-600 transition-colors hover:bg-gray-200"
                >
                  {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  {isExpanded ? "Hide Accounts" : "Show Accounts"}
                </button>
              </div>
            </div>

            {summary && (
              <div className="mt-2 rounded-sm border border-emerald-200 bg-emerald-50 p-2">
                <p className="text-[11px] font-semibold text-emerald-700">Latest sync • {formatTimestamp(summary.fetchedAt)}</p>
                <p className="text-[11px] text-emerald-700">
                  {summary.totalTransactions} transactions fetched
                  {summary.reviewCount > 0 && ` • ${summary.reviewCount} need review`}
                </p>
                {summary.preview.length > 0 && (
                  <ul className="mt-1 space-y-1 text-[11px] text-emerald-800">
                    {summary.preview.map((txn, idx) => (
                      <li key={`${item.item_id}-preview-${idx}`}>
                        {txn.date}: {txn.merchant} ({formatCurrency(Number(txn.amount))})
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {isExpanded && (
              <div className="mt-2 border-t border-gray-200 pt-2">
                {accountsState?.loading && <p className="text-[11px] text-gray-500">Loading accounts…</p>}
                {accountsState?.error && (
                  <p className="text-[11px] text-red-600">{accountsState.error}</p>
                )}
                {accountsState?.accounts && accountsState.accounts.length > 0 && (
                  <ul className="space-y-1 text-[11px] text-gray-700">
                    {accountsState.accounts.map((account) => (
                      <li key={account.account_id} className="flex items-center justify-between gap-2">
                        <span>{account.display_name}</span>
                        <span className="text-[10px] uppercase tracking-wide text-gray-400">{account.account_type}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {accountsState?.accounts && accountsState.accounts.length === 0 && !accountsState.error && (
                  <p className="text-[11px] text-gray-500">No accounts available.</p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
