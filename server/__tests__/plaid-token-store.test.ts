import { afterAll, beforeAll, describe, expect, it } from "bun:test";
import * as fs from "fs/promises";
import * as os from "os";
import * as path from "path";

import {
  getStoredItem,
  getTokensPath,
  loadStoredItems,
  removeStoredItem,
  setTokenStoreRoot,
  upsertStoredItem,
} from "../plaid/token-store";

let tempRoot: string;

beforeAll(async () => {
  tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), "plaid-token-store-test-"));
  setTokenStoreRoot(tempRoot);
});

afterAll(async () => {
  setTokenStoreRoot(null);
  await fs.rm(tempRoot, { recursive: true, force: true });
});

describe("plaid token store", () => {
  it("persists and retrieves Plaid items", async () => {
    const stored = await upsertStoredItem({
      item_id: "item-1",
      access_token: "access-abc",
      institution_id: "ins_123",
      accounts: [],
    });

    expect(stored.item_id).toBe("item-1");
    expect(stored.created_at).toBeTruthy();
    expect(await fs.stat(getTokensPath())).toBeTruthy();

    const items = await loadStoredItems();
    expect(items).toHaveLength(1);
    expect(items[0].item_id).toBe("item-1");

    const fetched = await getStoredItem("item-1");
    expect(fetched?.item_id).toBe("item-1");
  });

  it("updates existing item metadata", async () => {
    const updated = await upsertStoredItem({
      item_id: "item-1",
      access_token: "access-xyz",
      institution_id: "ins_123",
      accounts: [
        {
          account_id: "acct-1",
          name: "Checking",
          official_name: null,
          mask: "0000",
          type: "depository",
          subtype: "checking",
        },
      ],
    });

    expect(updated.accounts).toHaveLength(1);
    const items = await loadStoredItems();
    expect(items[0].accounts[0].account_id).toBe("acct-1");
  });

  it("removes items", async () => {
    expect(await removeStoredItem("item-1")).toBe(true);
    const items = await loadStoredItems();
    expect(items).toHaveLength(0);
  });
});
