import { tool, createSdkMcpServer } from "@anthropic-ai/claude-code";
import { z } from "zod";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Execute a shell command and return the output
 */
async function execCommand(command: string): Promise<string> {
  try {
    const { stdout, stderr } = await execAsync(command);
    if (stderr && stderr.trim()) {
      console.warn("Command stderr:", stderr);
    }
    return stdout.trim();
  } catch (error: any) {
    throw new Error(`Command failed: ${error.message}`);
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
            const result = await execCommand(command);
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
          const finAnalyzeType = {
            "trends": "spending-trends",
            "categories": "category-breakdown",
            "merchants": "merchant-frequency",
            "subscriptions": "subscription-detect"
          }[type];

          // 2. Build time flag based on timeFrame
          let timeFlag = '';
          if ('period' in timeFrame) {
            timeFlag = `--period ${timeFrame.period}`;
          } else {
            timeFlag = `--month ${timeFrame.month}`;
          }

          // 3. Build command: fin-analyze <analyzer> --period <period> OR --month <month> --format json
          // 4. Add --category flag if provided
          let command = `fin-analyze ${finAnalyzeType} ${timeFlag} --format json`;
          if (category) {
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
              text: `Error analyzing spending: ${error.message}`
            }]
          };
        }
      }
    ),

    // -------------------------------------------------------------------------
    // TOOL 4: search_transactions
    // -------------------------------------------------------------------------
    tool(
      "search_transactions",
      "Search and filter transactions from the database",
      {
        month: z.string().optional().describe("Filter by month (YYYY-MM format)"),
        category: z.string().optional().describe("Filter by category name"),
        merchant: z.string().optional().describe("Filter by merchant name"),
        minAmount: z.number().optional().describe("Minimum transaction amount"),
        limit: z.number().default(20).describe("Maximum number of results to return"),
      },
      async (args) => {
        try {
          // TODO: Implement search logic
          // 1. Build SQL WHERE conditions based on provided filters
          // 2. Construct fin-query sql command with filters
          // 3. Execute query with --format json
          // 4. Parse results
          // 5. Format as markdown table

          const month = args.month;
          const category = args.category;
          const merchant = args.merchant;
          const minAmount = args.minAmount;
          const limit = args.limit;
          console.log("== SEARCH TRANSACTIONS TOOL CALLED ==");
          console.log("month:", month);
          console.log("category:", category);
          console.log("merchant:", merchant);
          console.log("minAmount:", minAmount);
          console.log("limit:", limit);
          console.log("================================================");

          // 1. Construct the command
          const conditions = [];
          if (month) conditions.push(`strftime('%Y-%m', date) = '${month.replace(/'/g, "''")}'`);
          if (category) conditions.push(`category LIKE '%${category}%'`);
          if (merchant) conditions.push(`merchant LIKE '%${merchant}%'`);
          if (minAmount) conditions.push(`amount >= ${minAmount}`);
        
          const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
          const sql = `SELECT date, merchant, amount, category FROM transactions ${where} ORDER BY date DESC LIMIT ${limit}`;
          const command = `fin-query sql "${sql}" --format json`;

          // 2. Execute the command
          const fullCommand = `source ${getVenvPath()} && ${command}`; // Wrap command with venv activation
          const result = await execCommand(fullCommand);

          // 3. Write the result to a file
          const logsDir = getLogsDir();
          await ensureDir(logsDir);
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          const logPath = path.join(logsDir, `query-${timestamp}.json`);
          fs.writeFileSync(logPath, result);

          console.log(`Search transactions result: ${result}`);

          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                message: `Search query complete. Results written to ${logPath}`
              }, null, 2)
            }]
          };
        } catch (error: any) {
          return {
            content: [{
              type: "text",
              text: `Error searching transactions: ${error.message}`
            }]
          };
        }
      }
    ),
  ]
});