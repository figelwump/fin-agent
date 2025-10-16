import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';

const FIN_HOME = path.join(os.homedir(), '.finagent');
const PLAID_DIR = path.join(FIN_HOME, 'plaid');
const TOKENS_PATH = path.join(PLAID_DIR, 'tokens.json');

// Stored account subset keeps only what the UI and imports need.
export interface StoredPlaidAccount {
  account_id: string;
  name?: string | null;
  official_name?: string | null;
  mask?: string | null;
  type?: string | null;
  subtype?: string | null;
}

export interface StoredPlaidItem {
  item_id: string;
  access_token: string;
  institution_id?: string | null;
  accounts: StoredPlaidAccount[];
  created_at: string;
  updated_at: string;
}

async function ensurePlaidDir(): Promise<void> {
  await fs.mkdir(PLAID_DIR, { recursive: true, mode: 0o700 });
  await fs.chmod(PLAID_DIR, 0o700).catch(() => {
    // ignore if chmod fails due to platform
  });
}

async function readTokensFile(): Promise<StoredPlaidItem[]> {
  try {
    const raw = await fs.readFile(TOKENS_PATH, 'utf-8');
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      console.warn('[plaid] tokens.json did not contain an array; resetting file');
      return [];
    }
    return parsed as StoredPlaidItem[];
  } catch (error: any) {
    if (error?.code === 'ENOENT') {
      return [];
    }
    console.warn('[plaid] Failed to read tokens.json; returning empty list:', error);
    return [];
  }
}

async function writeTokensFile(items: StoredPlaidItem[]): Promise<void> {
  await ensurePlaidDir();
  const payload = JSON.stringify(items, null, 2);
  await fs.writeFile(TOKENS_PATH, `${payload}\n`, { mode: 0o600 });
  await fs.chmod(TOKENS_PATH, 0o600).catch(() => {
    // chmod can fail on Windows; swallow to keep flow moving
  });
}

export async function loadStoredItems(): Promise<StoredPlaidItem[]> {
  return readTokensFile();
}

export async function getStoredItem(itemId: string): Promise<StoredPlaidItem | undefined> {
  const items = await readTokensFile();
  return items.find((entry) => entry.item_id === itemId);
}

export async function upsertStoredItem(newItem: Omit<StoredPlaidItem, 'created_at' | 'updated_at'>): Promise<StoredPlaidItem> {
  const items = await readTokensFile();
  const now = new Date().toISOString();
  const existingIndex = items.findIndex((entry) => entry.item_id === newItem.item_id);

  if (existingIndex >= 0) {
    const updatedEntry: StoredPlaidItem = {
      ...items[existingIndex],
      ...newItem,
      created_at: items[existingIndex].created_at,
      updated_at: now,
    };
    items[existingIndex] = updatedEntry;
    await writeTokensFile(items);
    return updatedEntry;
  }

  const stored: StoredPlaidItem = {
    ...newItem,
    created_at: now,
    updated_at: now,
  };
  items.push(stored);
  await writeTokensFile(items);
  return stored;
}

export async function removeStoredItem(itemId: string): Promise<boolean> {
  const items = await readTokensFile();
  const filtered = items.filter((entry) => entry.item_id !== itemId);
  if (filtered.length === items.length) {
    return false;
  }
  await writeTokensFile(filtered);
  return true;
}

export function getTokensPath(): string {
  return TOKENS_PATH;
}
