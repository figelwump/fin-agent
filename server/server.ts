import "dotenv/config";
import { WebSocketHandler } from "../ccsdk/websocket-handler";
import type { WSClient } from "../ccsdk/types";
import { DATABASE_PATH } from "../database/config";
import { bulkImportStatements, getImportsStagingDir, sanitiseRelativePath, writeUploadedFile } from "../ccsdk/bulk-import";
import * as path from "path";
import * as fs from "fs/promises";
import { Buffer } from "buffer";
import { getPlaidClient } from "./plaid/client";
import { getStoredItem as getStoredPlaidItem, loadStoredItems, upsertStoredItem } from "./plaid/token-store";
import { parseCountryCodes, parseProducts } from "./plaid/config";
import { computeAccountKey, formatAccountName, normalizeAccountType } from "./plaid/helpers";
import { fetchPlaidTransactionsAndImport, PlaidFetchError, resolveInstitutionName } from "./plaid/fetch";
import type { LinkTokenCreateRequest } from "plaid";

// Auth config
const PORT = Number(process.env.PORT || 3000);
const AUTH_PASSWORD = process.env.AUTH_PASSWORD || process.env.BASIC_AUTH_PASSWORD;
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || "")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

if (!AUTH_PASSWORD) {
  console.warn("AUTH_PASSWORD not set; WebSocket will allow unauthenticated access");
}

const wsHandler = new WebSocketHandler(DATABASE_PATH);

// Security headers (from claudeboxes)
const securityHeaders: Record<string, string> = {
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self' wss: ws:; script-src 'self' 'unsafe-inline' 'unsafe-eval';",
};

function isOriginAllowed(origin: string | null): boolean {
  if (!origin) return ALLOWED_ORIGINS.length === 0;
  if (ALLOWED_ORIGINS.length === 0) return true;
  return ALLOWED_ORIGINS.includes(origin);
}

function allowedOriginHeader(origin: string | null): string | undefined {
  if (!origin && ALLOWED_ORIGINS.length === 0) return "*";
  if (origin && isOriginAllowed(origin)) return origin;
  return undefined;
}

function createHeaders(contentType?: string, origin?: string | null): Record<string, string> {
  const headers: Record<string, string> = { ...securityHeaders };
  const allowedOrigin = allowedOriginHeader(origin ?? null);
  if (allowedOrigin) {
    headers["Access-Control-Allow-Origin"] = allowedOrigin;
    headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS";
    headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization";
    headers["Vary"] = "Origin";
  }
  if (contentType) headers["Content-Type"] = contentType;
  return headers;
}

function getPasswordFromRequest(req: Request, url: URL): string | null {
  // Check query param token
  const token = url.searchParams.get("token");
  if (token) return token;

  // Check Authorization header (Basic auth)
  const authHeader = req.headers.get("authorization");
  if (authHeader) {
    const [scheme, encoded] = authHeader.split(" ");
    if (encoded && scheme?.toLowerCase() === "basic") {
      try {
        const decoded = Buffer.from(encoded, "base64").toString("utf8");
        const separator = decoded.indexOf(":");
        if (separator !== -1) {
          return decoded.slice(separator + 1);
        }
      } catch {}
    }
  }

  return null;
}

function isAuthorized(password: string | null): boolean {
  if (!AUTH_PASSWORD) return true; // No password configured = open access
  return password === AUTH_PASSWORD;
}

function unauthorizedResponse(origin: string | null): Response {
  const headers = createHeaders("application/json", origin);
  headers["WWW-Authenticate"] = 'Basic realm="fin-agent"';
  return new Response(JSON.stringify({ error: "unauthorized" }), {
    status: 401,
    headers,
  });
}

// Legacy CORS headers (kept for backward compatibility during transition)
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const jsonHeaders = {
  'Content-Type': 'application/json',
  ...corsHeaders,
};

function jsonResponse(data: unknown, status = 200, origin: string | null = null): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: createHeaders("application/json", origin),
  });
}

function errorResponse(message: string, status = 400, detail?: unknown, origin: string | null = null): Response {
  return jsonResponse(
    detail !== undefined ? { error: message, detail } : { error: message },
    status,
    origin
  );
}

async function readJsonBody<T>(req: Request): Promise<T | null> {
  try {
    return (await req.json()) as T;
  } catch (error) {
    console.warn('Failed to parse JSON body:', error);
    return null;
  }
}

const ISO_DATE_REGEX = /^\d{4}-\d{2}-\d{2}$/;

function isIsoDate(value: string): boolean {
  return ISO_DATE_REGEX.test(value);
}

const server = Bun.serve({
  port: PORT,
  idleTimeout: 120,

  websocket: {
    open(ws: WSClient) {
      wsHandler.onOpen(ws);
    },

    message(ws: WSClient, message: string) {
      wsHandler.onMessage(ws, message);
    },

    close(ws: WSClient) {
      wsHandler.onClose(ws);
    }
  },

  async fetch(req: Request, server: any) {
    const url = new URL(req.url);
    const origin = req.headers.get("origin");

    // Check CORS origin if allowlist is configured
    if (ALLOWED_ORIGINS.length > 0 && origin && !isOriginAllowed(origin)) {
      return new Response("Forbidden", { status: 403, headers: createHeaders(undefined, origin) });
    }

    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: createHeaders(undefined, origin) });
    }

    if (url.pathname === '/ws') {
      // Accept all WebSocket connections - auth happens via message
      const upgraded = server.upgrade(req, { data: { sessionId: '', authenticated: false } });
      if (!upgraded) {
        return new Response('WebSocket upgrade failed', { status: 400, headers: createHeaders(undefined, origin) });
      }
      return;
    }

    // Protect API endpoints with auth
    if (AUTH_PASSWORD && url.pathname.startsWith("/api")) {
      const password = getPasswordFromRequest(req, url);
      if (!isAuthorized(password)) {
        return unauthorizedResponse(origin);
      }
    }

    if (url.pathname === '/') {
      const file = Bun.file('./web_client/index.html');
      return new Response(file, {
        headers: createHeaders('text/html', origin),
      });
    }

    if (url.pathname === '/api/plaid/link-token' && req.method === 'POST') {
      try {
        const plaidClient = getPlaidClient();
        const clientUserId = process.env.PLAID_LINK_CLIENT_USER_ID ?? 'fin-agent-local-user';
        const clientName = process.env.PLAID_LINK_CLIENT_NAME ?? 'fin-agent';
        const products = parseProducts(process.env.PLAID_PRODUCTS);
        const countryCodes = parseCountryCodes(process.env.PLAID_COUNTRY_CODES);
        const webhook = process.env.PLAID_WEBHOOK;
        const redirectUri = process.env.PLAID_REDIRECT_URI;

        const request: LinkTokenCreateRequest = {
          client_name: clientName,
          language: 'en',
          country_codes: countryCodes,
          products,
          user: {
            client_user_id: clientUserId,
          },
        };

        if (webhook) {
          request.webhook = webhook;
        }
        if (redirectUri) {
          request.redirect_uri = redirectUri;
        }

        const response = await plaidClient.linkTokenCreate(request);
        return jsonResponse({ link_token: response.data.link_token });
      } catch (error: any) {
        const detail = error?.response?.data ?? error?.message ?? String(error);
        console.error('Plaid link token error', detail);
        return errorResponse('Failed to create Plaid link token.', 500, detail);
      }
    }

    if (url.pathname === '/api/plaid/exchange' && req.method === 'POST') {
      const body = await readJsonBody<{ public_token?: string }>(req);
      const publicToken = body?.public_token;

      if (!publicToken || typeof publicToken !== 'string') {
        return errorResponse('public_token is required.', 400);
      }

      try {
        const plaidClient = getPlaidClient();

        const exchange = await plaidClient.itemPublicTokenExchange({
          public_token: publicToken,
        });

        const accessToken = exchange.data.access_token;
        const itemId = exchange.data.item_id;

        const itemResponse = await plaidClient.itemGet({ access_token: accessToken });
        const institutionId = itemResponse.data.item?.institution_id ?? null;

        const accountsResponse = await plaidClient.accountsGet({
          access_token: accessToken,
        });

        const stored = await upsertStoredItem({
          item_id: itemId,
          access_token: accessToken,
          institution_id: institutionId,
          accounts: accountsResponse.data.accounts.map((account) => ({
            account_id: account.account_id,
            name: account.name ?? null,
            official_name: account.official_name ?? null,
            mask: account.mask ?? null,
            type: account.type ?? null,
            subtype: account.subtype ?? null,
          })),
        });

        return jsonResponse({
          item_id: stored.item_id,
          institution_id: stored.institution_id,
          accounts: stored.accounts,
        });
      } catch (error: any) {
        const detail = error?.response?.data ?? error?.message ?? String(error);
        console.error('Plaid exchange error', {
          error: detail,
        });
        return errorResponse('Failed to exchange Plaid public token.', 500, detail);
      }
    }

    if (url.pathname === '/api/plaid/items' && req.method === 'GET') {
      try {
        const storedItems = await loadStoredItems();
        if (storedItems.length === 0) {
          return jsonResponse({ items: [] });
        }

        const plaidClient = getPlaidClient();
        const countryCodes = parseCountryCodes(process.env.PLAID_COUNTRY_CODES);

        const items = await Promise.all(
          storedItems.map(async (item) => {
            const institutionName = await resolveInstitutionName(plaidClient, item, countryCodes);
            return {
              item_id: item.item_id,
              institution_id: item.institution_id ?? null,
              institution_name: institutionName,
              account_count: item.accounts.length,
              created_at: item.created_at,
              updated_at: item.updated_at,
            };
          })
        );

        return jsonResponse({ items });
      } catch (error: any) {
        console.error('Plaid items error', error);
        return errorResponse('Failed to load Plaid items.', 500, error?.message ?? String(error));
      }
    }

    if (url.pathname === '/api/plaid/accounts' && req.method === 'GET') {
      const itemId = url.searchParams.get('item_id');
      if (!itemId) {
        return errorResponse('item_id query parameter is required.', 400);
      }

      try {
        const storedItem = await getStoredPlaidItem(itemId);
        if (!storedItem) {
          return errorResponse('Plaid item not found.', 404);
        }

        const plaidClient = getPlaidClient();
        const countryCodes = parseCountryCodes(process.env.PLAID_COUNTRY_CODES);
        const institutionName = await resolveInstitutionName(plaidClient, storedItem, countryCodes);
        const institution = institutionName ?? 'Plaid';

        const accounts = storedItem.accounts.map((account) => {
          const displayName = formatAccountName(account);
          const accountType = normalizeAccountType(account);
          return {
            account_id: account.account_id,
            display_name: displayName,
            account_type: accountType,
            name: account.name,
            official_name: account.official_name,
            mask: account.mask,
            type: account.type,
            subtype: account.subtype,
            account_key: computeAccountKey(displayName, institution, accountType),
          };
        });

        return jsonResponse({
          item: {
            item_id: storedItem.item_id,
            institution_id: storedItem.institution_id ?? null,
            institution_name: institutionName,
            updated_at: storedItem.updated_at,
          },
          accounts,
        });
      } catch (error: any) {
        console.error('Plaid accounts error', error);
        return errorResponse('Failed to load Plaid accounts.', 500, error?.message ?? String(error));
      }
    }

    if (url.pathname === '/api/plaid/fetch' && req.method === 'POST') {
      const body = await readJsonBody<{
        item_id?: string;
        start?: string;
        end?: string;
        accountIds?: unknown;
        autoApprove?: unknown;
      }>(req);

      if (!body) {
        return errorResponse('Invalid JSON payload.', 400);
      }

      const itemId = typeof body.item_id === 'string' ? body.item_id.trim() : '';
      const startDate = typeof body.start === 'string' ? body.start.trim() : '';
      const endDate = typeof body.end === 'string' ? body.end.trim() : '';

      if (!itemId) {
        return errorResponse('item_id is required.', 400);
      }
      if (!startDate || !isIsoDate(startDate)) {
        return errorResponse('start must be an ISO date (YYYY-MM-DD).', 400);
      }
      if (!endDate || !isIsoDate(endDate)) {
        return errorResponse('end must be an ISO date (YYYY-MM-DD).', 400);
      }

      const accountIds = Array.isArray(body.accountIds)
        ? body.accountIds.map((value) => String(value))
        : undefined;
      const autoApprove = Boolean(body.autoApprove);

      try {
        const result = await fetchPlaidTransactionsAndImport({
          itemId,
          startDate,
          endDate,
          accountIds,
          autoApprove,
        });

        return jsonResponse({
          item: result.item,
          accounts: result.accounts,
          totalTransactions: result.totalTransactions,
          summary: result.bulkImport,
          transactionsPreview: result.bulkImport.transactionsPreview,
          reviewItems: result.bulkImport.reviewItems,
        });
      } catch (error: any) {
        if (error instanceof PlaidFetchError) {
          return errorResponse(error.message, error.status, error.detail);
        }
        console.error('Plaid fetch error', error);
        return errorResponse('Failed to fetch Plaid transactions.', 500, error?.message ?? String(error));
      }
    }

    if (url.pathname === '/api/bulk-import' && req.method === 'POST') {
      let stagingDir: string | undefined;
      try {
        const formData = await req.formData();
        const autoApproveRaw = formData.get('autoApprove');
        const autoApprove = typeof autoApproveRaw === 'string' ? autoApproveRaw === 'true' : false;
        const fileEntries = formData.getAll('files');

        if (fileEntries.length === 0) {
          return new Response(JSON.stringify({ error: 'No files uploaded.' }), {
            status: 400,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          });
        }

        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        stagingDir = getImportsStagingDir(timestamp);

        const storedPaths: string[] = [];
        const skipped: string[] = [];

        for (let idx = 0; idx < fileEntries.length; idx++) {
          const entry = fileEntries[idx];
          if (!(entry instanceof File)) {
            skipped.push(`non-file-${idx}`);
            continue;
          }

          const providedName = entry.name || `upload-${idx}`;
          const relativePath = sanitiseRelativePath(providedName);
          const destination = path.join(stagingDir, relativePath);

          await writeUploadedFile(destination, entry);
          storedPaths.push(destination);
        }

        if (storedPaths.length === 0) {
          return new Response(JSON.stringify({ error: 'Uploaded files could not be processed.', skipped }), {
            status: 400,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          });
        }

        console.log('Bulk import starting', {
          stagingDir,
          storedCount: storedPaths.length,
          autoApprove,
        });

        const summary = await bulkImportStatements({
          inputPaths: storedPaths,
          autoApprove,
        });

        return new Response(
          JSON.stringify({
            stagingDir,
            storedPaths,
            skipped,
            summary,
          }),
          {
            status: 200,
            headers: {
              'Content-Type': 'application/json',
              ...corsHeaders,
            },
          }
        );
      } catch (error: any) {
        console.error('Bulk import error:', error);
        if (stagingDir) {
          await fs.rm(stagingDir, { recursive: true, force: true }).catch(() => {
            // ignore cleanup failure
          });
        }
        return new Response(JSON.stringify({
          error: 'Bulk import failed.',
          detail: error?.message ?? String(error),
        }), {
          status: 500,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        });
      }
    }

    if (url.pathname === '/api/import/stage' && req.method === 'POST') {
      let stagingDir: string | undefined;
      try {
        const formData = await req.formData();
        const fileEntries = formData.getAll('files');

        if (fileEntries.length === 0) {
          return new Response(JSON.stringify({ error: 'No files uploaded.' }), {
            status: 400,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          });
        }

        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        stagingDir = getImportsStagingDir(`staged-${timestamp}`);

        const storedPaths: string[] = [];
        const skipped: string[] = [];

        for (let idx = 0; idx < fileEntries.length; idx++) {
          const entry = fileEntries[idx];
          if (!(entry instanceof File)) {
            skipped.push(`non-file-${idx}`);
            continue;
          }

          const providedName = entry.name || `upload-${idx}`;
          const relativePath = sanitiseRelativePath(providedName);
          const destination = path.join(stagingDir, relativePath);

          await writeUploadedFile(destination, entry);
          storedPaths.push(destination);
        }

        if (storedPaths.length === 0) {
          return new Response(JSON.stringify({ error: 'Uploaded files could not be processed.', skipped }), {
            status: 400,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          });
        }

        return new Response(JSON.stringify({ stagingDir, storedPaths, skipped }), {
          status: 200,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        });
      } catch (error: any) {
        console.error('Import staging error:', error);
        if (stagingDir) {
          await fs.rm(stagingDir, { recursive: true, force: true }).catch(() => {
            // ignore cleanup failure
          });
        }
        return new Response(JSON.stringify({
          error: 'Failed to stage files.',
          detail: error?.message ?? String(error),
        }), {
          status: 500,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        });
      }
    }

    if (url.pathname.startsWith('/web_client/') && url.pathname.endsWith('.css')) {
      const filePath = `.${url.pathname}`;
      const file = Bun.file(filePath);

      if (await file.exists()) {
        try {
          const cssContent = await file.text();

          const postcss = require('postcss');
          const tailwindcss = require('@tailwindcss/postcss');
          const autoprefixer = require('autoprefixer');

          const result = await postcss([
            tailwindcss(),
            autoprefixer,
          ]).process(cssContent, {
            from: filePath,
            to: undefined
          });

          return new Response(result.css, {
            headers: {
              'Content-Type': 'text/css',
            },
          });
        } catch (error) {
          console.error('CSS processing error:', error);
          return new Response('CSS processing failed', { status: 500 });
        }
      }
    }

    if (url.pathname.startsWith('/web_client/') && (url.pathname.endsWith('.tsx') || url.pathname.endsWith('.ts'))) {
      const filePath = `.${url.pathname}`;
      const file = Bun.file(filePath);

      if (await file.exists()) {
        try {
          const transpiled = await Bun.build({
            entrypoints: [filePath],
            target: 'browser',
            format: 'esm',
          });

          if (transpiled.success) {
            const jsCode = await transpiled.outputs[0].text();
            return new Response(jsCode, {
              headers: {
                'Content-Type': 'application/javascript',
              },
            });
          }
        } catch (error) {
          console.error('Transpilation error:', error);
          return new Response('Transpilation failed', { status: 500 });
        }
      }
    }

    // Serve other static assets under /web_client/ (e.g., .yaml, .json)
    if (url.pathname.startsWith('/web_client/')) {
      const filePath = `.${url.pathname}`;
      const file = Bun.file(filePath);
      if (await file.exists()) {
        let contentType = 'text/plain';
        if (url.pathname.endsWith('.json')) contentType = 'application/json';
        else if (url.pathname.endsWith('.yaml') || url.pathname.endsWith('.yml')) contentType = 'text/yaml';
        else if (url.pathname.endsWith('.svg')) contentType = 'image/svg+xml';
        else if (url.pathname.endsWith('.png')) contentType = 'image/png';
        return new Response(file, { headers: { 'Content-Type': contentType } });
      }
    }

    if (url.pathname === '/api/chat' && req.method === 'POST') {
      return new Response(JSON.stringify({
        error: 'Please use WebSocket connection at /ws for chat'
      }), {
        status: 400,
        headers: {
          'Content-Type': 'application/json',
          ...corsHeaders,
        },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
});

console.log(`Server running at http://localhost:${server.port}`);
console.log('WebSocket endpoint available at ws://localhost:3000/ws');
console.log('Visit http://localhost:3000 to view the fin-agent interface');
