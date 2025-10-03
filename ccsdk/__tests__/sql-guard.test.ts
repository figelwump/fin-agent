import { describe, it, expect } from "bun:test";
import { stripSqlComments, isSingleStatement, validateSelectOnly, ensureLimit } from "../sql-guard";

describe("sql-guard", () => {
  it("strips SQL comments", () => {
    const sql = "SELECT 1 -- comment\n/* block */\nFROM dual";
    const out = stripSqlComments(sql);
    expect(out).not.toContain("-- comment");
    expect(out).not.toContain("/* block */");
    expect(out).toContain("SELECT 1");
  });

  it("detects single vs multi-statement", () => {
    expect(isSingleStatement("SELECT 1")).toBe(true);
    expect(isSingleStatement("SELECT 1;")).toBe(true);
    expect(isSingleStatement("SELECT 1; SELECT 2;")).toBe(false);
  });

  it("allows SELECT/WITH and rejects forbidden keywords", () => {
    expect(() => validateSelectOnly("SELECT * FROM t")).not.toThrow();
    expect(() => validateSelectOnly("WITH c AS (SELECT 1) SELECT * FROM c")).not.toThrow();
    expect(() => validateSelectOnly("DELETE FROM t")).toThrow();
    expect(() => validateSelectOnly("PRAGMA table_info('t')")).toThrow();
    expect(() => validateSelectOnly("CREATE TABLE x(id INT)")).toThrow();
    // Forbidden keywords in comments should be ignored
    expect(() => validateSelectOnly("/* DROP TABLE x */ SELECT 1")).not.toThrow();
  });

  it("injects LIMIT defaults and caps", () => {
    let r = ensureLimit("SELECT * FROM t", undefined);
    expect(r.sql.toUpperCase()).toContain("LIMIT 200");
    expect(r.effectiveLimit).toBe(200);

    r = ensureLimit("SELECT * FROM t", 5000);
    expect(r.effectiveLimit).toBe(1000);
    expect(r.sql.toUpperCase()).toContain("LIMIT 1000");

    r = ensureLimit("SELECT * FROM t LIMIT 10", undefined);
    expect(r.sql.toUpperCase()).toContain("LIMIT 10");
  });
});
