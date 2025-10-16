import { createHash } from "crypto";

interface AccountNameSource {
  name?: string | null;
  official_name?: string | null;
  mask?: string | null;
}

interface AccountTypeSource {
  type?: string | null;
  subtype?: string | null;
}

/**
 * Prefer official name when available, otherwise fall back to the display name and append mask digits.
 * Mirrors the presentation used when generating CSV rows for fin-enhance.
 */
export function formatAccountName(source?: AccountNameSource): string {
  if (!source) {
    return "Plaid Account";
  }

  const official = source.official_name?.trim();
  if (official) {
    return official;
  }

  const name = source.name?.trim() || "Plaid Account";
  const mask = source.mask?.trim();
  if (mask) {
    return `${name} ****${mask}`;
  }
  return name;
}

/**
 * Use Plaid subtype when present, otherwise fall back to account type and default to "unknown".
 */
export function normalizeAccountType(source?: AccountTypeSource): string {
  const subtype = source?.subtype?.trim();
  if (subtype) {
    return subtype;
  }

  const type = source?.type?.trim();
  if (type) {
    return type;
  }

  return "unknown";
}

/**
 * Deterministic hash for account identity so Plaid imports align with PDF / CSV ingestion.
 */
export function computeAccountKey(name: string, institution: string, accountType: string): string {
  const normalized = [
    name.trim().toLowerCase(),
    institution.trim().toLowerCase(),
    accountType.trim().toLowerCase(),
  ].join("|");

  return createHash("sha256").update(normalized).digest("hex");
}
