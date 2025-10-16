import { Configuration, PlaidApi, PlaidEnvironments } from 'plaid';

let cachedClient: PlaidApi | null = null;

function resolvePlaidEnvironment(): keyof typeof PlaidEnvironments {
  const raw = (process.env.PLAID_ENV ?? 'sandbox').toLowerCase();
  if (raw === 'sandbox' || raw === 'development' || raw === 'production') {
    return raw;
  }

  console.warn(
    `[plaid] Unsupported PLAID_ENV value "${raw}", falling back to sandbox`
  );
  return 'sandbox';
}

/**
 * Returns a singleton Plaid API client configured from environment variables.
 * The Bun server reuses this instance for all requests.
 */
export function getPlaidClient(): PlaidApi {
  if (cachedClient) {
    return cachedClient;
  }

  const clientId = process.env.PLAID_CLIENT_ID;
  const secret = process.env.PLAID_SECRET;

  if (!clientId || !secret) {
    throw new Error(
      'Plaid client not configured. Set PLAID_CLIENT_ID and PLAID_SECRET.'
    );
  }

  const envName = resolvePlaidEnvironment();
  const configuration = new Configuration({
    basePath: PlaidEnvironments[envName],
    baseOptions: {
      headers: {
        'PLAID-CLIENT-ID': clientId,
        'PLAID-SECRET': secret,
      },
    },
  });

  cachedClient = new PlaidApi(configuration);
  return cachedClient;
}
