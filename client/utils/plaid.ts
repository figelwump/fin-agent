export interface PlaidLinkSuccessMetadata {
  institution?: {
    name: string | null;
    institution_id: string | null;
  };
  accounts?: Array<{ id: string; name: string }>
}

export interface PlaidLinkHandler {
  open: () => void;
  exit: () => void;
  destroy: () => void;
}

export interface PlaidLinkError {
  error_code?: string;
  error_message?: string;
  display_message?: string | null;
}

export interface PlaidCreateConfig {
  token: string;
  onSuccess: (publicToken: string, metadata: PlaidLinkSuccessMetadata) => void;
  onExit?: (error: PlaidLinkError | null, metadata?: PlaidLinkSuccessMetadata) => void;
  onEvent?: (eventName: string, metadata: Record<string, unknown>) => void;
}

declare global {
  interface Window {
    Plaid?: {
      create: (config: PlaidCreateConfig) => PlaidLinkHandler;
    };
  }
}

const PLAID_LINK_SCRIPT = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";

let plaidScriptPromise: Promise<void> | null = null;

export function loadPlaidScript(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Plaid Link is only available in the browser"));
  }

  if (window.Plaid) {
    return Promise.resolve();
  }

  if (plaidScriptPromise) {
    return plaidScriptPromise;
  }

  plaidScriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src=\"${PLAID_LINK_SCRIPT}\"]`);
    if (existing && existing.dataset.loaded === "true") {
      resolve();
      return;
    }

    const script = existing ?? document.createElement("script");
    script.src = PLAID_LINK_SCRIPT;
    script.async = true;
    script.dataset.loaded = "false";

    script.onload = () => {
      script.dataset.loaded = "true";
      resolve();
    };
    script.onerror = () => {
      script.remove();
      plaidScriptPromise = null;
      reject(new Error("Failed to load Plaid Link"));
    };

    if (!existing) {
      document.body.appendChild(script);
    }
  });

  return plaidScriptPromise;
}
