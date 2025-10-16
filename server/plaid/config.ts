import { CountryCode, Products } from "plaid";

const validCountryCodes = new Set<string>(Object.values(CountryCode));

export function parseCountryCodes(raw?: string): CountryCode[] {
  const parsed = (raw ?? "US")
    .split(",")
    .map((code) => code.trim().toUpperCase())
    .filter(Boolean)
    .filter((code) => validCountryCodes.has(code));

  if (parsed.length === 0) {
    return [CountryCode.Us];
  }

  return parsed as CountryCode[];
}

const productsMap = new Map<string, Products>(
  Object.values(Products).map((value) => [value.toLowerCase(), value as Products]),
);

export function parseProducts(raw?: string): Products[] {
  const requested = (raw ?? Products.Transactions)
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);

  const resolved: Products[] = [];

  for (const key of requested) {
    const product = productsMap.get(key);
    if (product && !resolved.includes(product)) {
      resolved.push(product);
    }
  }

  return resolved.length > 0 ? resolved : [Products.Transactions];
}
