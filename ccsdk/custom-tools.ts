import { tool, createSdkMcpServer } from "@anthropic-ai/claude-code";
import { z } from "zod";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import { exec } from "child_process";
import { promisify } from "util";
import { config as loadEnv } from "dotenv";
import { stripSqlComments, isSingleStatement, validateSelectOnly, ensureLimit } from "./sql-guard";
import { bulkImportStatements } from "./bulk-import";

const execAsync = promisify(exec);

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Execute a shell command and return the output
 */
async function execCommand(command: string): Promise<string> {
  // Ensure child processes inherit the .env configuration so fin-cli sees keys like OPENAI_API_KEY.
  if (!process.env.OPENAI_API_KEY) {
    const envFile = path.join(process.cwd(), ".env");
    if (fs.existsSync(envFile)) {
      loadEnv({ path: envFile, override: false });
    }
  }

  try {
    const { stdout, stderr } = await execAsync(command, {
      env: { ...process.env },
      shell: "/bin/bash",
    });
    if (stderr && stderr.trim()) {
      console.warn("Command stderr:", stderr);
    }
    return stdout.trim();
  } catch (error: any) {
    // Include both stdout and stderr in the error message so Claude can see what went wrong
    const stderr = error.stderr?.trim() || '';
    const stdout = error.stdout?.trim() || '';
    let errorMsg = error.message || 'Unknown error';

    // If we have stderr, it often contains the most useful error info
    if (stderr) {
      errorMsg += `\nError output: ${stderr}`;
    }
    // Sometimes stdout also has useful context
    if (stdout) {
      errorMsg += `\nCommand output: ${stdout}`;
    }

    throw new Error(errorMsg);
  }
}

/**
 * Ensure a directory exists, create it if it doesn't
 */
async function ensureDir(dirPath: string): Promise<void> {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

/**
 * Get the output directory path (expand ~ to home directory)
 */
function getOutputDir(): string {
  const homeDir = os.homedir();
  return path.join(homeDir, ".finagent", "output");
}

/**
 * Get the logs directory path (expand ~ to home directory)
 */
function getLogsDir(): string {
  const homeDir = os.homedir();
  return path.join(homeDir, ".finagent", "logs");
}

/**
 * Get the venv path (relative to the current working directory)
 */
function getVenvPath(): string {
  const cwd = process.cwd();
  return path.join(cwd, ".venv", "bin", "activate");
}

/**
 * Generate a CSV filename from a PDF path
 */
function generateCsvFilename(pdfPath: string): string {
  const outputDir = getOutputDir();
  const basename = path.basename(pdfPath, ".pdf");

  // For now, just use the PDF basename as-is
  const csvFilename = `${basename}.csv`;

  return path.join(outputDir, csvFilename);
}

// =============================================================================
// MCP SERVER DEFINITION
// =============================================================================

export const customMCPServer = createSdkMcpServer({
  name: "finance",
  version: "1.0.0",
  tools: [
    // -------------------------------------------------------------------------
    // TOOL 1: extract_statement
    // -------------------------------------------------------------------------
    tool(
      "extract_statement",
      "Extract transactions from a PDF bank statement to a CSV file. Completely local and private - no data leaves the machine.",
      {
        pdfPath: z.string().describe("Path to the PDF statement file to extract"),
      },
      async (args) => {
        try {
          console.log("== EXTRACT STATEMENT TOOL CALLED ==");
          console.log("pdfPath:", args.pdfPath);
          console.log("================================================");

          // 1. Validate PDF file exists
          const pdfPath = args.pdfPath;
          if (!fs.existsSync(pdfPath)) {
            throw new Error(`PDF file does not exist: ${pdfPath}`);
          }

          // 2. Ensure output directory exists
          const outputDir = getOutputDir();
          await ensureDir(outputDir);

          // 3. Generate output CSV filename
          const csvPath = generateCsvFilename(args.pdfPath);

          // 4. Run: fin-extract <pdfPath> --output <csvPath>
          const command = `fin-extract "${pdfPath}" --output "${csvPath}"`;
          const fullCommand = `source ${getVenvPath()} && ${command}`; // Wrap command with venv activation
          const result = await execCommand(fullCommand);

          console.log(`Statement extracted to: ${csvPath} with result: ${result}`);

          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                csvPath: csvPath,
                message: `Statement extracted successfully to ${csvPath}`
              }, null, 2)
            }]
          };
        } catch (error: any) {
          console.error("Error extracting statement: ", error);
          return {
            content: [{
              type: "text",
              text: `Error extracting statement: ${error.message}`
            }]
          };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL: bulk_import_statements
    // -------------------------------------------------------------------------
    tool(
      "bulk_import_statements",
      "Import multiple PDF statement files (and/or CSVs) in one batch using a single fin-enhance run.",
      {
        pdfPaths: z.union([
          z.array(z.string()),
          z.string(),
        ]).describe("Array of paths, directory/glob string, or single path pointing to PDFs/CSVs."),
        autoApprove: z.boolean().default(false).describe("If true, pass --auto to fin-enhance and skip review file generation."),
      },
      async (args) => {
        try {
          const rawInputs = Array.isArray(args.pdfPaths) ? args.pdfPaths : [args.pdfPaths];

          const result = await bulkImportStatements({
            inputPaths: rawInputs,
            autoApprove: args.autoApprove,
          });

          const payload = {
            autoApprove: result.autoApprove,
            csvPaths: result.csvPaths,
            reviewPath: result.reviewPath ?? null,
            finEnhanceLogPath: result.finEnhanceLogPath ?? null,
            unsupported: result.unsupported,
            missing: result.missing,
            extraction: result.extraction,
            finEnhanceOutput: result.finEnhanceOutput ?? null,
            transactionsPreview: result.transactionsPreview ?? [],
            reviewItems: result.reviewItems ?? [],
          };

          console.log('[bulk_import_statements] Result from bulkImportStatements:');
          console.log('  - reviewPath:', result.reviewPath);
          console.log('  - finEnhanceLogPath:', result.finEnhanceLogPath ?? null);
          console.log('  - reviewItems count:', result.reviewItems?.length ?? 0);
          console.log('  - reviewItems with suggestedCategory:', result.reviewItems?.filter(i => i.suggestedCategory).length ?? 0);

          if (result.reviewItems && result.reviewItems.length > 0) {
            console.log('[bulk_import_statements] First review item being sent to frontend:', JSON.stringify(result.reviewItems[0], null, 2));
          }

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(payload, null, 2),
              },
            ],
          };
        } catch (error: any) {
          return {
            content: [
              {
                type: "text",
                text: `Error during bulk import: ${error.message}`,
              },
            ],
            isError: true,
          };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL: fin_query_list_saved
    // -------------------------------------------------------------------------
    tool(
      "fin_query_list_saved",
      "List saved fin-query definitions with parameter metadata (reads index.yaml).",
      {},
      async () => {
        try {
          // Use Python (PyYAML available in venv) to parse manifest and emit JSON
          const pyCmd = [
            "python",
            "- <<'PY'\n"
              + "import json, yaml\n"
              + "from pathlib import Path\n"
              + "p = Path('fin_cli/fin_query/queries/index.yaml')\n"
              + "data = yaml.safe_load(p.read_text(encoding='utf-8'))\n"
              + "print(json.dumps(data))\n"
              + "PY",
          ].join(" ");
          const full = `source ${getVenvPath()} && ${pyCmd}`;
          const stdout = await execCommand(full);

          const logsDir = getLogsDir();
          await ensureDir(logsDir);
          const ts = new Date().toISOString().replace(/[:.]/g, "-");
          const logPath = path.join(logsDir, `saved-queries-${ts}.json`);
          fs.writeFileSync(logPath, stdout);

          return { content: [{ type: "text", text: stdout }] };
        } catch (error: any) {
          return { content: [{ type: "text", text: `Error listing saved queries: ${error.message}` }], isError: true };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL: fin_query_saved
    // -------------------------------------------------------------------------
    tool(
      "fin_query_saved",
      "Run a saved fin-query by name with optional parameters and JSON output.",
      {
        name: z.string().describe("Saved query name from index.yaml"),
        params: z.record(z.string(), z.string()).optional().describe("KEY:VALUE bindings for saved query parameters"),
        limit: z.number().optional().describe("Optional row limit override; also passed to CLI --limit"),
      },
      async (args) => {
        try {
          const name = args.name;
          const params = args.params || {};
          const limit = args.limit;

          const paramFlags = Object.entries(params).map(([k, v]) => `-p ${k}=${String(v).replaceAll('"', '\\"')}`).join(" ");
          const limitFlag = typeof limit === "number" && isFinite(limit) && limit > 0 ? ` --limit ${Math.min(limit, 1000)}` : "";
          const cmd = `fin-query saved ${name} ${paramFlags} --format json${limitFlag}`.trim();
          const full = `source ${getVenvPath()} && ${cmd}`;
          const out = await execCommand(full);

          const logsDir = getLogsDir();
          await ensureDir(logsDir);
          const ts = new Date().toISOString().replace(/[:.]/g, "-");
          const logPath = path.join(logsDir, `saved-${name}-${ts}.json`);
          fs.writeFileSync(logPath, out);

          return { content: [{ type: "text", text: out }] };
        } catch (error: any) {
          return { content: [{ type: "text", text: `Error running saved query: ${error.message}` }], isError: true };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL: fin_query_schema
    // -------------------------------------------------------------------------
    tool(
      "fin_query_schema",
      "Return database schema metadata (tables, columns, indexes, foreign keys).",
      {
        table: z.string().optional().describe("Optional table name to filter.")
      },
      async (args) => {
        try {
          const table = args.table?.trim();
          const tableFlag = table ? ` --table ${table}` : "";
          const cmd = `fin-query schema${tableFlag} --format json`;
          const full = `source ${getVenvPath()} && ${cmd}`;
          const out = await execCommand(full);

          const logsDir = getLogsDir();
          await ensureDir(logsDir);
          const ts = new Date().toISOString().replace(/[:.]/g, "-");
          const logPath = path.join(logsDir, `schema-${table || 'all'}-${ts}.json`);
          fs.writeFileSync(logPath, out);

          return { content: [{ type: "text", text: out }] };
        } catch (error: any) {
          return { content: [{ type: "text", text: `Error fetching schema: ${error.message}` }], isError: true };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL: fin_query_sql (guarded)
    // -------------------------------------------------------------------------
    tool(
      "fin_query_sql",
      "Execute a single read-only SELECT/WITH SQL with strict guardrails. Adds a LIMIT if missing.",
      {
        query: z.string().describe("SQL SELECT/WITH statement."),
        params: z.record(z.string(), z.string()).optional().describe("Named parameter bindings as KEY:VALUE"),
        limit: z.number().optional().describe("Desired row limit (default 200, hard cap 1000)."),
      },
      async (args) => {
        try {
          const raw = args.query;
          const params = args.params || {};
          const limit = args.limit;

          if (!isSingleStatement(raw)) {
            throw new Error("Provide exactly one SQL statement; multi-statement batches are not allowed.");
          }
          validateSelectOnly(raw);
          const { sql, effectiveLimit } = ensureLimit(raw, limit);

          const paramFlags = Object.entries(params).map(([k, v]) => `-p ${k}=${String(v).replaceAll('"', '\\"')}`).join(" ");
          const cmd = `fin-query sql \"${sql.replaceAll('"', '\\"')}\" ${paramFlags} --format json --limit ${effectiveLimit}`.trim();
          const full = `source ${getVenvPath()} && ${cmd}`;
          const out = await execCommand(full);

          const logsDir = getLogsDir();
          await ensureDir(logsDir);
          const ts = new Date().toISOString().replace(/[:.]/g, "-");
          const logPath = path.join(logsDir, `sql-${ts}.json`);
          fs.writeFileSync(logPath, out);

          return { content: [{ type: "text", text: out }] };
        } catch (error: any) {
          return { content: [{ type: "text", text: `Error executing SQL: ${error.message}` }], isError: true };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL: fin_query_sample
    // -------------------------------------------------------------------------
    tool(
      "fin_query_sample",
      "Return a small, recent sample of rows from an allowlisted table (read-only). Always orders by a recency column per table and applies a strict LIMIT.",
      {
        table: z.enum([
          "transactions",
          "accounts",
          "categories",
          "merchant_patterns",
          "category_suggestions",
          "llm_cache",
        ]).describe("Table name to sample (allowlisted)."),
        limit: z.number().default(20).describe("Maximum rows to return (default 20, max 100)."),
      },
      async (args) => {
        try {
          const table = args.table as string;
          let limit = Number(args.limit ?? 20);
          if (!Number.isFinite(limit) || limit <= 0) limit = 20;
          if (limit > 100) limit = 100; // hard cap for MCP payload size

          // Choose an ORDER BY clause that shows most recent rows for each table.
          // We do not attempt dynamic schema inspection here; we use known columns per schema.
          const orderByByTable: Record<string, string> = {
            transactions: "date DESC, id DESC",
            accounts: "COALESCE(last_import, created_date) DESC, id DESC",
            categories: "COALESCE(last_used, created_date) DESC, id DESC",
            merchant_patterns: "COALESCE(learned_date, usage_count) DESC",
            category_suggestions: "COALESCE(last_seen, created_at) DESC, id DESC",
            llm_cache: "COALESCE(updated_at, created_at) DESC",
          };
          const orderBy = orderByByTable[table] || "rowid DESC";

          // Build SQL safely. Identifier is allowlisted; limit is bound.
          const sql = `SELECT * FROM ${table} ORDER BY ${orderBy} LIMIT :limit`;
          const command = `fin-query sql "${sql}" -p limit=${limit} --format json`;
          const fullCommand = `source ${getVenvPath()} && ${command}`;
          const result = await execCommand(fullCommand);

          const logsDir = getLogsDir();
          await ensureDir(logsDir);
          const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
          const logPath = path.join(logsDir, `sample-${table}-${timestamp}.json`);
          fs.writeFileSync(logPath, result);

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(
                  {
                    table,
                    limit,
                    message: `Sampled recent rows from ${table}. Results written to ${logPath}`,
                    logPath,
                  },
                  null,
                  2
                ),
              },
            ],
          };
        } catch (error: any) {
          return {
            content: [
              {
                type: "text",
                text: `Error sampling table: ${error.message}`,
              },
            ],
            isError: true,
          };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL 2: import_transactions
    // -------------------------------------------------------------------------
    tool(
      "import_transactions",
      "Import and categorize transactions from a CSV file into the database. Uses LLM API for categorization.",
      {
        csvPath: z.string().describe("Path to the CSV file to import"),
        autoApprove: z.boolean().default(false).describe(
          "If true, auto-approve all categorizations. If false, create review file for user approval."
        ),
      },
      async (args) => {
        try {
          const autoApprove = args.autoApprove;
          const csvPath = args.csvPath;
          console.log("== IMPORT TRANSACTIONS TOOL CALLED ==");
          console.log("autoApprove:", autoApprove);
          console.log("csvPath:", csvPath);
          console.log("================================================");

          // 1. Validate CSV file exists
          if (!fs.existsSync(csvPath)) {
            throw new Error(`CSV file does not exist: ${csvPath}`);
          }
          
          // 2. If autoApprove:
          //    - Run: fin-enhance <csvPath> --auto
          //    - Return success message
          // 3. If NOT autoApprove:
          //    - Generate review file path
          //    - Run: fin-enhance <csvPath> --review-output <reviewPath>
          //    - Parse review JSON
          //    - Return formatted review data for user
          if (autoApprove) {
            const command = `fin-enhance "${csvPath}" --auto`;
            const fullCommand = `source ${getVenvPath()} && ${command}`;
            const result = await execCommand(fullCommand);
            console.log(`Imported transactions auto mode into DB , received result: ${result}`);

            return {
              content: [{
                type: "text",
                text: JSON.stringify({
                  message: `Imported transactions auto mode into DB: ${result}`
                }, null, 2)
              }]
            };
          } else {
            const logsDir = getLogsDir();
            await ensureDir(logsDir);
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const reviewPath = path.join(logsDir, `review-${timestamp}.json`);
            const command = `fin-enhance "${csvPath}" --review-output "${reviewPath}"`;
            const fullCommand = `source ${getVenvPath()} && ${command}`; // Wrap command with venv activation
            const result = await execCommand(fullCommand);
            console.log(`Imported transactions with review file: ${reviewPath} with result: ${result}`);

            return {
              content: [{
                type: "text",
                text: JSON.stringify({
                  autoApprove: autoApprove,
                  message: `Imported transactions into DB with pending review file: ${reviewPath}. Ask the user to review the categories in the review file and then collate their responses into a decisions file.`
                }, null, 2)
              }]
            };
          }
        } catch (error: any) {
          return {
            content: [{
              type: "text",
              text: `Error importing transactions: ${error.message}`
            }]
          };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL 3: analyze_spending
    // -------------------------------------------------------------------------
    tool(
      "analyze_spending",
      "Analyze spending patterns for a specific time period using various analyzers",
      {
        timeFrame: z.union([
          z.object({
            period: z.string().describe("Relative period: '7d' for 7 days, '3m' for 3 months, '1w' for 1 week, '12m' for 12 months, etc.")
          }),
          z.object({
            month: z.string().describe("Specific month in YYYY-MM format (e.g., '2024-01')")
          })
        ]).describe("Time frame for analysis - use either period (relative) or month (specific)"),
        type: z.enum([
          "trends",
          "categories",
          "merchants",
          "subscriptions"
        ]).describe("Type of analysis to perform"),
        category: z.string().optional().describe("Filter by specific category (optional)"),
      },
      async (args) => {
        try {
          const timeFrame = args.timeFrame;
          const type = args.type;
          const category = args.category;

          console.log("== ANALYZE TOOL CALLED ==");
          console.log("timeFrame:", timeFrame);
          console.log("type:", type);
          console.log("category:", category);
          console.log("================================================");

          // 1. Map type to fin-analyze analyzer name:
          // Map high-level type to analyzer slug. Adjust when category filter is present.
          let analyzerSlug = {
            "trends": "spending-trends",
            "categories": "category-breakdown",
            "merchants": "merchant-frequency",
            "subscriptions": "subscription-detect"
          }[type];

          // If a category filter is requested, prefer analyzers that support it.
          // - merchant-frequency supports --category
          // - category-timeline supports --category
          // - category-breakdown does NOT support --category
          // For a category-scoped "categories" request, switch to category-timeline.
          if (category && type === 'categories') {
            analyzerSlug = 'category-timeline';
          }

          // 2. Build time flag based on timeFrame with smarter mapping
          let timeFlag = '';
          if ('period' in timeFrame) {
            const p = String((timeFrame as any).period || '').trim();
            if (/^\d{4}$/.test(p)) {
              // Calendar year like 2025
              timeFlag = `--year ${p}`;
            } else if (p.toLowerCase() === 'last-12-months' || p.toLowerCase() === 'last_12_months') {
              // Prefer period syntax for trailing 12 months to match expected usage
              timeFlag = `--period 12m`;
            } else {
              timeFlag = `--period ${p}`; // expects formats like 3m, 6w, 30d, 12m
            }
          } else {
            timeFlag = `--month ${(timeFrame as any).month}`;
          }

          // 3. Build command: fin-analyze <analyzer> --period <period> OR --month <month> --format json
          // 4. Add --category flag if provided
          let command = `fin-analyze ${analyzerSlug} ${timeFlag} --format json`;
          const categorySupported = new Set(["merchant-frequency", "category-timeline"]);
          if (category && categorySupported.has(analyzerSlug)) {
            command += ` --category ${category}`;
          }

          // 4. Execute command
          const fullCommand = `source ${getVenvPath()} && ${command}`; // Wrap command with venv activation
          const result = await execCommand(fullCommand);

          // 5. Write result to file
          const logsDir = getLogsDir();
          await ensureDir(logsDir);
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          const logPath = path.join(logsDir, `analysis-${timestamp}.json`);
          fs.writeFileSync(logPath, result);

          console.log(`Analysis result: ${result}`);

          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                message: `Analysis complete. Full analysis results written to ${logPath}`
              }, null, 2)
            }]
          };
        } catch (error: any) {
          console.error("Error analyzing spending: ", error);

          return {
            content: [{
              type: "text",
              text: error.message
            }],
            isError: true
          };
        }
      }
    ),

    
  ]
});
