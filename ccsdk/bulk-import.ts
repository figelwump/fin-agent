import { spawn } from 'child_process';
import * as crypto from 'crypto';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';
import { glob } from 'glob';
import { parse } from 'csv-parse/sync';

export interface BulkImportOptions {
  inputPaths: string[];
  autoApprove?: boolean;
}

export interface ExtractionResult {
  sourcePath: string;
  status: 'success' | 'error';
  csvPath?: string;
  stdout?: string;
  stderr?: string;
  error?: string;
}

export interface BulkImportResult {
  autoApprove: boolean;
  extraction: ExtractionResult[];
  csvPaths: string[];
  reviewPath?: string;
  finEnhanceOutput?: string;
  unsupported: string[];
  missing: string[];
  transactionsPreview: EnhancedTransactionPreview[];
  reviewItems: ReviewItem[];
  steps: Array<{ name: string; durationMs: number }>;
}

export interface EnhancedTransactionPreview {
  date: string;
  merchant: string;
  amount: number;
  category: string;
  subcategory: string;
  accountName?: string;
}

export interface ReviewItem {
  id: string;
  date: string;
  merchant: string;
  amount: number;
  originalDescription: string;
  accountId: number | null;
  suggestedCategory?: string;
  suggestedSubcategory?: string;
  confidence?: number;
}

const FIN_HOME = path.join(os.homedir(), '.finagent');
const OUTPUT_ROOT = path.join(FIN_HOME, 'output', 'bulk');
const LOGS_ROOT = path.join(FIN_HOME, 'logs');
const SUPPORTED_EXTENSIONS = new Set(['.pdf', '.csv']);

async function ensureDir(dirPath: string) {
  await fs.mkdir(dirPath, { recursive: true });
}

function getVenvEnv(): NodeJS.ProcessEnv {
  const env = { ...process.env };
  const projectRoot = process.cwd();
  const venvPath = path.join(projectRoot, '.venv');
  const binDir = path.join(venvPath, 'bin');

  env.PATH = env.PATH ? `${binDir}:${env.PATH}` : binDir;
  env.VIRTUAL_ENV = env.VIRTUAL_ENV || venvPath;

  return env;
}

interface RunCommandResult {
  stdout: string;
  stderr: string;
}

async function runCommand(command: string, args: string[]): Promise<RunCommandResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      env: getVenvEnv(),
    });

    let stdout = '';
    let stderr = '';

    if (child.stdout) {
      child.stdout.on('data', (chunk) => {
        stdout += chunk.toString();
      });
    }

    if (child.stderr) {
      child.stderr.on('data', (chunk) => {
        stderr += chunk.toString();
      });
    }

    child.on('error', (error) => {
      reject(error);
    });

    child.on('close', (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        const error = new Error(`Command failed: ${command} ${args.join(' ')} (exit code ${code})`);
        (error as any).stdout = stdout;
        (error as any).stderr = stderr;
        reject(error);
      }
    });
  });
}

function uniqueCsvPath(pdfPath: string, timestamp: string): string {
  const baseName = path.basename(pdfPath, path.extname(pdfPath));
  const hash = crypto.createHash('sha1').update(pdfPath).digest('hex').slice(0, 8);
  return path.join(OUTPUT_ROOT, `${timestamp}-${baseName}-${hash}.csv`);
}

function isSupportedExt(filePath: string): boolean {
  return SUPPORTED_EXTENSIONS.has(path.extname(filePath).toLowerCase());
}

async function expandDirectory(dirPath: string): Promise<string[]> {
  const matches = await glob('**/*', {
    cwd: dirPath,
    absolute: true,
    nodir: true,
  });
  return matches.filter(isSupportedExt);
}

async function expandGlob(pattern: string): Promise<string[]> {
  const matches = await glob(pattern, {
    nodir: true,
  });
  return matches.filter(isSupportedExt);
}

export interface PathExpansionResult {
  files: string[];
  missing: string[];
  unsupported: string[];
}

export async function expandImportPaths(inputs: string[]): Promise<PathExpansionResult> {
  const files = new Set<string>();
  const missing: string[] = [];
  const unsupported: string[] = [];

  for (const raw of inputs) {
    const hasGlob = /[\*\?]/.test(raw);

    if (hasGlob) {
      const matches = await expandGlob(raw);
      if (matches.length === 0) {
        missing.push(raw);
      } else {
        matches.forEach((match) => files.add(path.resolve(match)));
      }
      continue;
    }

    const resolved = path.resolve(raw);
    try {
      const stats = await fs.stat(resolved);
      if (stats.isDirectory()) {
        const dirMatches = await expandDirectory(resolved);
        if (dirMatches.length === 0) {
          missing.push(resolved);
        } else {
          dirMatches.forEach((match) => files.add(path.resolve(match)));
        }
      } else if (stats.isFile()) {
        if (isSupportedExt(resolved)) {
          files.add(resolved);
        } else {
          unsupported.push(resolved);
        }
      } else {
        unsupported.push(resolved);
      }
    } catch (error: any) {
      if (error?.code === 'ENOENT') {
        missing.push(resolved);
      } else {
        throw error;
      }
    }
  }

  return {
    files: Array.from(files),
    missing,
    unsupported,
  };
}

export async function bulkImportStatements(options: BulkImportOptions): Promise<BulkImportResult> {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const expansion = await expandImportPaths(options.inputPaths);

  if (expansion.files.length === 0) {
    const reason = expansion.missing.length
      ? `No supported files found. Missing inputs: ${expansion.missing.join(', ')}`
      : expansion.unsupported.length
        ? `Inputs did not contain supported .pdf/.csv files: ${expansion.unsupported.join(', ')}`
        : 'No importable files provided. Supported extensions: .pdf, .csv';
    throw new Error(reason);
  }

  const pdfPaths = expansion.files.filter((p) => path.extname(p).toLowerCase() === '.pdf');
  const existingCsvPaths = expansion.files.filter((p) => path.extname(p).toLowerCase() === '.csv');

  await ensureDir(OUTPUT_ROOT);
  await ensureDir(LOGS_ROOT);

  const extraction: ExtractionResult[] = [];
  const generatedCsvPaths: string[] = [];
  const steps: Array<{ name: string; durationMs: number }> = [];

  const extractionStart = Date.now();
  for (const pdfPath of pdfPaths) {
    const csvPath = uniqueCsvPath(pdfPath, timestamp);
    try {
      const { stdout, stderr } = await runCommand('fin-extract', [pdfPath, '--output', csvPath]);
      generatedCsvPaths.push(csvPath);
      extraction.push({
        sourcePath: pdfPath,
        status: 'success',
        csvPath,
        stdout: stdout.trim(),
        stderr: stderr.trim() || undefined,
      });
    } catch (error: any) {
      extraction.push({
        sourcePath: pdfPath,
        status: 'error',
        error: error.message,
        stdout: error.stdout,
        stderr: error.stderr,
      });
    }
  }
  steps.push({ name: 'extract', durationMs: Date.now() - extractionStart });

  const csvPaths = [...existingCsvPaths, ...generatedCsvPaths];

  if (csvPaths.length === 0) {
    const failedPdfs = extraction.filter((entry) => entry.status === 'error').map((entry) => entry.sourcePath);
    const reason = failedPdfs.length
      ? `All PDF extractions failed (${failedPdfs.length} file${failedPdfs.length === 1 ? '' : 's'}).`
      : 'No CSV files were provided or produced.';
    const message = expansion.unsupported.length
      ? `${reason} Unsupported files: ${expansion.unsupported.join(', ')}`
      : reason;
    throw new Error(message);
  }

  const enhanceArgs = [...csvPaths];
  let reviewPath: string | undefined;

  if (options.autoApprove) {
    enhanceArgs.push('--auto');
  } else {
    reviewPath = path.join(LOGS_ROOT, `bulk-review-${timestamp}.json`);
    enhanceArgs.push('--review-output', reviewPath);
  }

  let finEnhanceOutput: string | undefined;
  let enhancedTransactions: EnhancedTransactionPreview[] = [];
  const importStart = Date.now();
  try {
    const enhanceResult = await runCommand('fin-enhance', [...enhanceArgs, '--stdout']);
    finEnhanceOutput = [enhanceResult.stdout.trim(), enhanceResult.stderr.trim()].filter(Boolean).join('\n');

    enhancedTransactions = parseEnhancedCsv(enhanceResult.stdout);
  } catch (error: any) {
    const enhanceError = new Error(`fin-enhance failed: ${error.message}`);
    (enhanceError as any).stdout = error.stdout;
    (enhanceError as any).stderr = error.stderr;
    throw enhanceError;
  }
  steps.push({ name: 'import', durationMs: Date.now() - importStart });

  const reviewItems = await readReviewItems(reviewPath);

  return {
    autoApprove: Boolean(options.autoApprove),
    extraction,
    csvPaths,
    reviewPath,
    finEnhanceOutput,
    unsupported: expansion.unsupported,
    missing: expansion.missing,
    transactionsPreview: enhancedTransactions,
    reviewItems,
    steps,
  };
}

function parseEnhancedCsv(stdout: string): EnhancedTransactionPreview[] {
  const trimmed = stdout.trim();
  if (!trimmed) return [];

  const { csvText, headerLine } = extractCsvSection(trimmed);
  if (!csvText || !headerLine) return [];

  try {
    const records = parse(csvText, {
      columns: headerLine.split(',').map((col) => col.trim()),
      skip_empty_lines: true,
      trim: true,
      relax_column_count: true,
      skip_records_with_error: true,
      on_record: (record: Record<string, string>) => {
        const date = record.date ?? record.Date;
        const amount = record.amount ?? record.Amount;
        return date && amount ? record : null;
      },
    }) as Record<string, string>[];

    const previews: EnhancedTransactionPreview[] = [];
    for (const record of records) {
      if (!record.date && !record.Date) continue;
      const parsedAmount = Number(record.amount ?? record.Amount ?? 0);
      previews.push({
        date: record.date ?? record.Date ?? '',
        merchant: record.merchant ?? record.Merchant ?? '',
        amount: Number.isFinite(parsedAmount) ? parsedAmount : 0,
        category: record.category ?? record.Category ?? '',
        subcategory: record.subcategory ?? record.Subcategory ?? '',
        accountName: record.account_name ?? record.account ?? record.Account ?? undefined,
      });
      if (previews.length >= 200) break;
    }
    return previews;
  } catch (error) {
    console.warn('Failed to parse enhanced CSV preview:', error);
    return [];
  }
}

function extractCsvSection(text: string): { csvText: string | null; headerLine: string | null } {
  const lines = text.split(/\r?\n/);
  let headerIndex = -1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    if (!line.includes(',')) continue;
    const lower = line.toLowerCase();
    if (lower.startsWith('date') && lower.includes('amount')) {
      headerIndex = i;
      break;
    }
  }

  if (headerIndex === -1) return { csvText: null, headerLine: null };

  const csvLines = lines.slice(headerIndex).filter((line) => line.includes(','));
  return {
    csvText: csvLines.join('\n'),
    headerLine: lines[headerIndex],
  };
}

async function readReviewItems(reviewPath?: string): Promise<ReviewItem[]> {
  if (!reviewPath) {
    console.log('[readReviewItems] No review path provided');
    return [];
  }
  try {
    console.log('[readReviewItems] Reading review file:', reviewPath);
    const content = await fs.readFile(reviewPath, 'utf-8');
    const json = JSON.parse(content);

    console.log('[readReviewItems] Review JSON structure:', JSON.stringify(json, null, 2));
    console.log('[readReviewItems] review_needed array length:', json?.review_needed?.length ?? 0);

    if (!Array.isArray(json?.review_needed)) {
      console.warn('[readReviewItems] review_needed is not an array');
      return [];
    }

    // Log first item to see structure
    if (json.review_needed.length > 0) {
      console.log('[readReviewItems] First review item structure:', JSON.stringify(json.review_needed[0], null, 2));
    }

    const items = (json.review_needed as any[]).map((item, idx) => {
      // Extract the first suggestion if available
      const firstSuggestion = Array.isArray(item.suggestions) && item.suggestions.length > 0
        ? item.suggestions[0]
        : null;

      const reviewItem = {
        id: String(item.id),
        date: item.date ?? '',
        merchant: item.merchant ?? '',
        amount: Number(item.amount ?? 0),
        originalDescription: item.original_description ?? '',
        accountId: item.account_id ?? null,
        suggestedCategory: firstSuggestion?.category ?? undefined,
        suggestedSubcategory: firstSuggestion?.subcategory ?? undefined,
        confidence: firstSuggestion?.confidence !== undefined ? Number(firstSuggestion.confidence) : undefined,
      };

      if (idx === 0) {
        console.log('[readReviewItems] First parsed review item:', JSON.stringify(reviewItem, null, 2));
      }

      return reviewItem;
    });

    console.log('[readReviewItems] Total items parsed:', items.length);
    console.log('[readReviewItems] Items with suggested categories:', items.filter(i => i.suggestedCategory).length);

    return items;
  } catch (error) {
    console.warn('[readReviewItems] Failed to read review JSON:', error);
    return [];
  }
}

export async function writeUploadedFile(destination: string, file: File): Promise<void> {
  await ensureDir(path.dirname(destination));
  const buffer = Buffer.from(await file.arrayBuffer());
  await fs.writeFile(destination, buffer);
}

export function sanitiseRelativePath(input: string): string {
  const normalised = path.normalize(input).replace(/^\/+/, '');
  const withoutTraversal = normalised.split(path.sep).filter((segment) => segment !== '..');
  return withoutTraversal.join(path.sep) || path.basename(normalised);
}

export function getImportsStagingDir(timestamp: string): string {
  return path.join(FIN_HOME, 'imports', timestamp);
}

export async function ensureFinagentDirs(): Promise<void> {
  await ensureDir(OUTPUT_ROOT);
  await ensureDir(LOGS_ROOT);
}
