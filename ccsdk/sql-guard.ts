// Simple SQL guardrails used by the MCP fin_query_sql tool.
// These helpers are intentionally conservative and string-based so they work
// without adding a full SQL parser dependency. They aim to prevent writes and
// complex multi-statement batches while keeping SELECT/WITH ad‑hoc queries easy.

export function stripSqlComments(sql: string): string {
  // Remove -- line comments and /* */ block comments
  return sql
    .replace(/--[^\n]*\n/g, "\n")
    .replace(/\/\*[\s\S]*?\*\//g, "");
}

export function isSingleStatement(sql: string): boolean {
  // Forbid semicolons except a single trailing one.
  const trimmed = sql.trim();
  const count = (trimmed.match(/;/g) || []).length;
  if (count === 0) return true;
  if (count === 1) return trimmed.endsWith(";");
  return false;
}

export function validateSelectOnly(sql: string): void {
  const s = stripSqlComments(sql).trim().toUpperCase();
  const firstToken = s.split(/\s+/)[0] || "";
  if (!(firstToken === "SELECT" || firstToken === "WITH")) {
    throw new Error("Only SELECT or WITH statements are allowed in fin_query_sql.");
  }
  const forbidden = [
    "PRAGMA",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "ANALYZE",
    "CREATE",
    "ALTER",
    "DROP",
    "INSERT",
    "UPDATE",
    "DELETE",
    "REPLACE",
    "TRIGGER",
    "INDEX",
    "LOAD_EXTENSION",
  ];
  for (const kw of forbidden) {
    const re = new RegExp(`\\b${kw}\\b`, "i");
    if (re.test(s)) {
      throw new Error(`Statement contains forbidden keyword: ${kw}`);
    }
  }
}

export function ensureLimit(sql: string, requestedLimit?: number): { sql: string; effectiveLimit: number } {
  const defaultLimit = 200;
  const hardCap = 1000;
  let limit = typeof requestedLimit === "number" && isFinite(requestedLimit) && requestedLimit > 0 ? requestedLimit : defaultLimit;
  if (limit > hardCap) limit = hardCap;
  const hasLimit = /\blimit\b/i.test(sql);
  let patched = sql.trim();
  if (!hasLimit) {
    patched = patched.replace(/;\s*$/, "");
    patched += ` LIMIT ${limit}`;
  }
  return { sql: patched, effectiveLimit: limit };
}

