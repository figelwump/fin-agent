import { describe, expect, it } from "bun:test";
import { computeAccountKey, formatAccountName, normalizeAccountType } from "../plaid/helpers";

describe("plaid helpers", () => {
  it("prefers official account name when present", () => {
    const name = formatAccountName({
      official_name: "Premium Checking",
      name: "Checking",
      mask: "1234",
    });
    expect(name).toBe("Premium Checking");
  });

  it("falls back to name plus mask when official name missing", () => {
    const name = formatAccountName({ name: "Everyday Checking", mask: "9876" });
    expect(name).toBe("Everyday Checking ****9876");
  });

  it("returns generic label when metadata absent", () => {
    expect(formatAccountName(undefined)).toBe("Plaid Account");
  });

  it("normalizes subtype before type", () => {
    expect(normalizeAccountType({ subtype: "credit card", type: "credit" })).toBe("credit card");
    expect(normalizeAccountType({ type: "investment" })).toBe("investment");
  });

  it("computes deterministic account keys", () => {
    const keyA = computeAccountKey("Account One", "Institution", "checking");
    const keyB = computeAccountKey("Account One", "Institution", "checking");
    const keyC = computeAccountKey("Account Two", "Institution", "checking");

    expect(keyA).toBe(keyB);
    expect(keyA).not.toBe(keyC);
  });
});
