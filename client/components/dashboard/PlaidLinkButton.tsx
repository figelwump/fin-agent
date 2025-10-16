import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "lucide-react";
import { loadPlaidScript, type PlaidLinkError, type PlaidLinkHandler } from "../../utils/plaid";

interface PlaidLinkButtonProps {
  disabled?: boolean;
  onConnected?: () => void;
  onError?: (message: string) => void;
}

/**
 * Launches Plaid Link in the browser, exchanges the resulting public token with the Bun server,
 * and notifies the caller once an item is connected.
 */
export function PlaidLinkButton({ disabled = false, onConnected, onError }: PlaidLinkButtonProps) {
  const [isLaunching, setIsLaunching] = useState(false);
  const handlerRef = useRef<PlaidLinkHandler | null>(null);

  const clearHandler = useCallback(() => {
    handlerRef.current?.destroy();
    handlerRef.current = null;
  }, []);

  useEffect(() => clearHandler, [clearHandler]);

  const reportError = useCallback((message: string) => {
    console.error("Plaid Link error", message);
    onError?.(message);
  }, [onError]);

  const exchangePublicToken = useCallback(async (publicToken: string) => {
    const response = await fetch("/api/plaid/exchange", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ public_token: publicToken }),
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || "Plaid token exchange failed");
    }

    await response.json();
  }, []);

  const handleClick = useCallback(async () => {
    if (disabled || isLaunching) return;

    setIsLaunching(true);
    try {
      const linkTokenResponse = await fetch("/api/plaid/link-token", {
        method: "POST",
      });

      if (!linkTokenResponse.ok) {
        const detail = await linkTokenResponse.text();
        throw new Error(detail || "Failed to create Plaid link token");
      }

      const { link_token: linkToken } = await linkTokenResponse.json();
      if (!linkToken) {
        throw new Error("Server did not return a Plaid link token");
      }

      await loadPlaidScript();
      if (!window.Plaid) {
        throw new Error("Plaid Link script failed to load");
      }

      handlerRef.current = window.Plaid.create({
        token: linkToken,
        onSuccess: async (publicToken) => {
          try {
            await exchangePublicToken(publicToken);
            onConnected?.();
          } catch (error: any) {
            reportError(error?.message ?? "Failed to finalize Plaid connection");
          } finally {
            clearHandler();
          }
        },
        onExit: (error: PlaidLinkError | null) => {
          if (error) {
            const message = error.display_message || error.error_message || "Plaid Link closed";
            reportError(message);
          }
          clearHandler();
        },
      });

      handlerRef.current.open();
    } catch (error: any) {
      reportError(error?.message ?? "Unable to launch Plaid Link");
      clearHandler();
    } finally {
      setIsLaunching(false);
    }
  }, [clearHandler, disabled, exchangePublicToken, isLaunching, onConnected, onError, reportError]);

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || isLaunching}
      className="inline-flex items-center gap-2 rounded-sm border border-emerald-600 px-3 py-2 text-xs font-semibold uppercase tracking-wider text-emerald-600 transition-colors hover:bg-emerald-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Link size={14} />
      {isLaunching ? "Connecting…" : "Connect Bank"}
    </button>
  );
}
