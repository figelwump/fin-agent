import * as fs from "fs/promises";
import * as os from "os";
import * as path from "path";
import { AccountBase, Transaction, TransactionsGetRequestOptions } from "plaid";
import { bulkImportStatements, type BulkImportResult } from "../../ccsdk/bulk-import";
import { getPlaidClient } from "./client";
import { parseCountryCodes } from "./config";
import { computeAccountKey, formatAccountName, normalizeAccountType } from "./helpers";
import {
  getStoredItem,
  upsertStoredItem,
  type StoredPlaidAccount,
  type StoredPlaidItem,
} from "./token-store";

const CSV_HEADERS = [
  "date",
  "merchant",
  "amount",
  "original_description",
  "account_name",
  "institution",
  "account_type",
  "account_key",
] as const;

const PAGE_SIZE = 500;

export interface PlaidFetchParams {
  itemId: string;
  startDate: string;
  endDate: string;
  accountIds?: string[];
  autoApprove?: boolean;
}

export interface PlaidFetchResult {
  item: {
    item_id: string;
    institution_id: string | null | undefined;
    institution_name: string | null;
  };
  accounts: Array<{
    account_id: string;
    name: string | null | undefined;
    official_name: string | null | undefined;
    mask: string | null | undefined;
    type: string | null | undefined;
    subtype: string | null | undefined;
    display_name: string;
    account_type: string;
    account_key: string;
  }>;
  totalTransactions: number;
  bulkImport: BulkImportResult;
}

export class PlaidFetchError extends Error {
  status: number;
  detail?: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export async function fetchPlaidTransactionsAndImport(
  params: PlaidFetchParams,
): Promise<PlaidFetchResult> {
  const { itemId, startDate, endDate } = params;

  const storedItem = await getStoredItem(itemId);
  if (!storedItem) {
    throw new PlaidFetchError("Plaid item not found.", 404);
  }

  const plaidClient = getPlaidClient();
  const countryCodes = parseCountryCodes(process.env.PLAID_COUNTRY_CODES);

  const { transactions, accounts } = await fetchAllTransactions({
    plaidClient,
    accessToken: storedItem.access_token,
    startDate,
    endDate,
    accountIds: params.accountIds,
  });

  const institutionName = await resolveInstitutionName(plaidClient, storedItem, countryCodes);

  const csvContent = buildCsvContent({
    transactions,
    accounts,
    institutionName,
  });

  const bulkImport = await runFinEnhance(csvContent, Boolean(params.autoApprove));

  // Refresh stored accounts with the latest name/mask details returned by Plaid.
  await upsertStoredItem({
    item_id: storedItem.item_id,
    access_token: storedItem.access_token,
    institution_id: storedItem.institution_id,
    accounts: accounts.map(minifyAccountForStore),
  });

  const institution = institutionName ?? "Plaid";
  const accountSummaries = accounts.map((account) => {
    const displayName = formatAccountName(account);
    const accountType = normalizeAccountType(account);
    return {
      account_id: account.account_id,
      name: account.name,
      official_name: account.official_name,
      mask: account.mask,
      type: account.type,
      subtype: account.subtype,
      display_name: displayName,
      account_type: accountType,
      account_key: computeAccountKey(displayName, institution, accountType),
    };
  });

  return {
    item: {
      item_id: storedItem.item_id,
      institution_id: storedItem.institution_id,
      institution_name: institutionName,
    },
    accounts: accountSummaries,
    totalTransactions: transactions.length,
    bulkImport,
  };
}

async function fetchAllTransactions(args: {
  plaidClient: ReturnType<typeof getPlaidClient>;
  accessToken: string;
  startDate: string;
  endDate: string;
  accountIds?: string[];
}): Promise<{ transactions: Transaction[]; accounts: AccountBase[] }> {
  const { plaidClient, accessToken, startDate, endDate, accountIds } = args;

  const transactions: Transaction[] = [];
  let accounts: AccountBase[] | null = null;
  let offset = 0;

  const options: TransactionsGetRequestOptions = {
    count: PAGE_SIZE,
    offset,
    include_original_description: true,
  };

  const filteredAccountIds = accountIds?.map((id) => id.trim()).filter(Boolean);
  if (filteredAccountIds && filteredAccountIds.length > 0) {
    options.account_ids = filteredAccountIds;
  }

  // Iterate until we've retrieved all transactions for the selected window.
  while (true) {
    try {
      const response = await plaidClient.transactionsGet({
        access_token: accessToken,
        start_date: startDate,
        end_date: endDate,
        options: {
          ...options,
          offset,
        },
      });

      transactions.push(...response.data.transactions);
      accounts = accounts ?? response.data.accounts;

      const total = response.data.total_transactions ?? response.data.transactions.length;
      if (transactions.length >= total) {
        break;
      }

      if (response.data.transactions.length === 0) {
        // Plaid responded with no transactions but total > fetched; avoid infinite loop.
        break;
      }

      offset += response.data.transactions.length;
    } catch (error: any) {
      throw new PlaidFetchError(
        "Failed to fetch Plaid transactions.",
        502,
        error?.response?.data ?? error?.message ?? String(error),
      );
    }
  }

  accounts = accounts ?? [];

  // Ensure we have account metadata for every transaction; call accounts/get as a fallback.
  const missingAccountIds = new Set(
    transactions.map((txn) => txn.account_id).filter((id) => id && !accounts!.some((acct) => acct.account_id === id)),
  );

  if (missingAccountIds.size > 0) {
    const fallbackAccounts = await fetchAccounts(plaidClient, accessToken);
    const mergedAccounts = mergeAccounts(accounts, fallbackAccounts);
    accounts = mergedAccounts;
  }

  return {
    transactions,
    accounts,
  };
}

async function fetchAccounts(plaidClient: ReturnType<typeof getPlaidClient>, accessToken: string): Promise<AccountBase[]> {
  try {
    const response = await plaidClient.accountsGet({ access_token: accessToken });
    return response.data.accounts;
  } catch (error: any) {
    throw new PlaidFetchError(
      "Failed to fetch Plaid accounts.",
      502,
      error?.response?.data ?? error?.message ?? String(error),
    );
  }
}

function mergeAccounts(primary: AccountBase[], fallback: AccountBase[]): AccountBase[] {
  const byId = new Map<string, AccountBase>();

  for (const account of primary) {
    byId.set(account.account_id, account);
  }

  for (const account of fallback) {
    if (!byId.has(account.account_id)) {
      byId.set(account.account_id, account);
    }
  }

  return Array.from(byId.values());
}

export async function resolveInstitutionName(
  plaidClient: ReturnType<typeof getPlaidClient>,
  storedItem: StoredPlaidItem,
  countryCodes: ReturnType<typeof parseCountryCodes>,
): Promise<string | null> {
  if (!storedItem.institution_id) {
    return null;
  }

  try {
    const response = await plaidClient.institutionsGetById({
      institution_id: storedItem.institution_id,
      country_codes: countryCodes,
    });
    return response.data.institution?.name ?? storedItem.institution_id;
  } catch (error) {
    console.warn("[plaid] Failed to resolve institution name:", error);
    return storedItem.institution_id;
  }
}

function buildCsvContent(args: {
  transactions: Transaction[];
  accounts: AccountBase[];
  institutionName: string | null;
}): string {
  const { transactions, accounts, institutionName } = args;

  const accountMap = new Map<string, AccountBase>();
  for (const account of accounts) {
    accountMap.set(account.account_id, account);
  }

  const sorted = [...transactions].sort((a, b) => a.date.localeCompare(b.date));

  const rows = [CSV_HEADERS.join(",")];

  for (const txn of sorted) {
    const account = accountMap.get(txn.account_id);
    const displayName = formatAccountName(account);
    const accountType = normalizeAccountType(account);
    const institution = institutionName ?? "Plaid";

    const csvRow = [
      csvEscape(txn.date ?? ""),
      csvEscape(resolveMerchant(txn)),
      csvEscape(formatAmount(txn.amount)),
      csvEscape(txn.name ?? ""),
      csvEscape(displayName),
      csvEscape(institution),
      csvEscape(accountType),
      csvEscape(computeAccountKey(displayName, institution, accountType)),
    ];

    rows.push(csvRow.join(","));
  }

  // Ensure trailing newline so fin-enhance reads the last row.
  return `${rows.join("\n")}\n`;
}

function resolveMerchant(txn: Transaction): string {
  const merchant = txn.merchant_name?.trim();
  if (merchant) {
    return merchant;
  }
  const name = txn.name?.trim();
  if (name) {
    return name;
  }
  return "Unknown Merchant";
}

function csvEscape(value: string): string {
  const needsQuotes = /[",\n]/.test(value);
  const escaped = value.replace(/"/g, '""');
  return needsQuotes ? `"${escaped}"` : escaped;
}

function formatAmount(amount: number | null | undefined): string {
  if (typeof amount !== "number" || Number.isNaN(amount)) {
    return "0.00";
  }
  return amount.toFixed(2);
}

async function runFinEnhance(csvContent: string, autoApprove: boolean): Promise<BulkImportResult> {
  const tmpRoot = await fs.mkdtemp(path.join(os.tmpdir(), "finagent-plaid-"));
  const csvPath = path.join(tmpRoot, `plaid-${Date.now()}.csv`);

  try {
    await fs.writeFile(csvPath, csvContent, "utf8");
    return await bulkImportStatements({
      inputPaths: [csvPath],
      autoApprove,
    });
  } finally {
    await fs.rm(tmpRoot, { recursive: true, force: true }).catch(() => {
      // Ignore cleanup errors.
    });
  }
}

function minifyAccountForStore(account: AccountBase): StoredPlaidAccount {
  return {
    account_id: account.account_id,
    name: account.name ?? null,
    official_name: account.official_name ?? null,
    mask: account.mask ?? null,
    type: account.type ?? null,
    subtype: account.subtype ?? null,
  };
}
