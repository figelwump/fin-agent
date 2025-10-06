# Bulk Import Tool Implementation Plan

This document follows the repo plan conventions (prefix `plan_`, date suffix `MMDDYY`). It has been renamed to `plans/plan_bulk_import_statements_100325.md` on 2025-10-03.

## Overview

Add a new MCP tool `bulk_import_statements` to handle importing multiple bank statement PDFs in a single operation, with optional parallelization for improved performance.

## Problem Statement

Currently, when users want to import multiple bank statements:
1. The agent tries to write bash scripts to loop through files
2. This takes multiple back-and-forth iterations to get right
3. Each file is processed sequentially, which is slow
4. No built-in way to aggregate review files from multiple imports

## Proposed Solution

Add a new MCP tool that:
- Accepts multiple PDF paths (array or glob pattern)
- Extracts and imports them with configurable parallelism
- Aggregates review files into a single consolidated output
- Provides clear progress reporting

Clarification: In the recommended batch mode (single `fin-enhance` invocation with all CSVs), one unified in-memory review queue is produced and written once to a single review JSON. Aggregation is only needed if we choose per-file imports (Option B).

## Architecture

### Tool Signature

```typescript
tool(
  "bulk_import_statements",
  "Import multiple bank statement PDFs with parallel processing",
  {
    pdfPaths: z.union([
      z.array(z.string()),
      z.string()
    ]).describe("Array of PDF paths OR a directory path with glob pattern (e.g., '/path/to/statements/*.pdf')"),

    autoApprove: z.boolean()
      .default(false)
      .describe("Auto-approve all categorizations. If false, creates consolidated review file."),

    parallelism: z.number()
      .default(3)
      .min(1)
      .max(10)
      .describe("Number of files to process in parallel")
  }
)
```

### Processing Phases

#### Phase 1: Discovery
- Expand glob patterns to file lists
- Validate all PDFs exist
- Return error early if any files are missing

#### Phase 2: Extraction (Parallel)
- Extract all PDFs to CSVs using `fin-extract`
- Use TypeScript `Promise.allSettled()` with concurrency limiting
- Collect extraction results (success/failure per file)

#### Phase 3: Import (Batched)
- **Option A: Batch Import (SELECTED 2025-10-03)**
  - Call `fin-enhance` once with all CSV files as arguments
  - Single CLI invocation/connection (not a single monolithic SQLite transaction)
  - More efficient LLM usage (can batch similar merchants)
  - Simpler error handling

- ~~**Option B: Parallel Import**~~ *(deferred; revisit only if batch mode fails to meet requirements)*
  - ~~Call `fin-enhance` for each CSV in parallel~~
  - ~~SQLite will serialize writes automatically~~
  - ~~More granular progress reporting~~
  - ~~More complex error handling~~

#### Phase 4: Review Aggregation
Not required for Option A (single `fin-enhance` invocation produces one review file). Keep design notes here for future exploration if we ever revive per-file imports.

- If `autoApprove = false`, aggregate all per-file review JSON files *(only if Option B is restored)*
- Deduplicate `transaction_review` entries by `id` (transaction fingerprint)
- Deduplicate `new_category_approval` proposals by `(category, subcategory)`; sum `support_count` and `total_amount`, and merge `transaction_examples` (bounded length)
- Write consolidated review file and return its path + summary stats

### Error Handling

- Use `Promise.allSettled()` to continue even if some files fail
- Return detailed results: succeeded files, failed files with error messages
- Don't abort entire batch on single file failure

### Progress Reporting

Since MCP tools run synchronously from Claude's perspective:
- Write progress to console.log (visible in MCP server logs)
- Return comprehensive summary at the end with per-file status

## Implementation Details

### Concurrency Control

Use a library like `p-limit` or implement simple semaphore:

```typescript
import pLimit from 'p-limit';

async function extractPDFsInParallel(
  pdfPaths: string[],
  parallelism: number
): Promise<Array<{path: string, csvPath?: string, error?: string}>> {
  const limit = pLimit(parallelism);

  const results = await Promise.allSettled(
    pdfPaths.map(pdfPath =>
      limit(async () => {
        const csvPath = generateCsvFilename(pdfPath);
        const command = `fin-extract \"${pdfPath}\" --output \"${csvPath}\"`;
        const fullCommand = `source ${getVenvPath()} && ${command}`;
        await execCommand(fullCommand);
        return { path: pdfPath, csvPath };
      })
    )
  );

  return results.map((result, idx) => {
    if (result.status === 'fulfilled') {
      return result.value;
    } else {
      return {
        path: pdfPaths[idx],
        // Include rich error output so callers see failing command + stderr/exit code
        error: (result.reason && (result.reason as any).message) ? (result.reason as any).message : String(result.reason)
      };
    }
  });
}
```

### Batch Import Strategy

For Phase 3, use **Option A (Batch Import)**:

```typescript
// After all PDFs extracted, collect successful CSV paths
const successfulCsvPaths = extractionResults
  .filter(r => r.csvPath)
  .map(r => r.csvPath!);

if (successfulCsvPaths.length === 0) {
  throw new Error("No PDFs were successfully extracted");
}

// Import all at once
const csvPathArgs = successfulCsvPaths.map(p => `\"${p}\"`).join(' ');
const reviewPath = path.join(logsDir, `bulk-review-${timestamp}.json`);
const command = autoApprove
  ? `fin-enhance ${csvPathArgs} --auto`
  : `fin-enhance ${csvPathArgs} --review-output \"${reviewPath}\"`;

const fullCommand = `source ${getVenvPath()} && ${command}`;
const result = await execCommand(fullCommand);
```

**Why batch is better:**
- `fin-enhance` already handles multiple CSV files (see `main.py:21` - `nargs=-1`)
- Single invocation/connection = fewer edge cases (not one big SQLite transaction)
- LLM categorizer can potentially batch similar merchants
- Simpler code, fewer edge cases

### Path Expansion Helper (2025-10-03)
- Added `expandImportPaths` utility in `ccsdk/bulk-import.ts` to normalise arrays/globs/directories into a deduplicated list of supported `.pdf` / `.csv` files.
- The helper returns `missing` and `unsupported` lists so both MCP tool and HTTP endpoint can surface helpful feedback.
- Directory inputs walk recursively using `glob` while filtering unsupported extensions to avoid surprising imports.

### Glob Pattern Support

```typescript
import { glob } from 'glob';

async function expandPdfPaths(input: string | string[]): Promise<string[]> {
  if (Array.isArray(input)) {
    return input;
  }

  // If it's a string, check if it contains glob patterns
  if (input.includes('*') || input.includes('?')) {
    const matches = await glob(input, { nodir: true });
    return matches.filter(f => f.toLowerCase().endsWith('.pdf'));
  }

  // Check if it's a directory
  try {
    if (fs.statSync(input).isDirectory()) {
      const matches = await glob(`${input}/**/*.pdf`, { nodir: true });
      return matches;
    }
  } catch (e) {
    // Treat ENOENT as no matches instead of throwing
    return [];
  }

  // Single file path
  return [input];
}
```

### Filename Collision Strategy

Multiple folders can contain the same basename (e.g., `Jan.pdf`). To avoid CSV
collisions in `~/.finagent/output`, generate a short, stable suffix derived
from the absolute path, e.g., an 8‑char SHA1 of `path.resolve(pdfPath)`. Also
ensure both `getOutputDir()` and `getLogsDir()` exist before writing.

## Sub-Agent Analysis

**Should we use sub-agents for parallelization?** ❌ **NO**

### Why NOT to use sub-agents:

1. **Overkill for simple operations**
   - Sub-agents are designed for complex multi-step reasoning tasks
   - Extracting a PDF and importing a CSV is a simple command execution
   - No benefit from LLM reasoning here

2. **Database contention**
   - Multiple agents trying to write to SQLite simultaneously
   - SQLite serializes writes anyway, so no real parallelism benefit
   - Risk of lock errors and transaction conflicts

3. **Token cost**
   - Each sub-agent instance consumes tokens for its context
   - Expensive for what amounts to running bash commands

4. **Complexity**
   - Harder to aggregate results across agents
   - More difficult error handling
   - Requires coordination logic

5. **We already have the infrastructure**
   - `execCommand()` helper can run commands
   - TypeScript `Promise.all()` provides concurrency
   - Much simpler and more efficient

### When sub-agents WOULD make sense:

- Complex decision-making per file (e.g., "review each statement and decide which to import")
- Different processing strategies per file based on analysis
- Tasks requiring multi-step reasoning or tool use per file
- When parallelizing truly independent AI reasoning tasks

For this use case, **native TypeScript concurrency is the right choice**.

## File Locations

### Files to modify:
- `ccsdk/custom-tools.ts` - Add new `bulk_import_statements` tool
- `ccsdk/cc-client.ts` - Add `mcp__finance__bulk_import_statements` to `allowedTools`

### Dependencies to add:
- `p-limit` (for concurrency control)
- `glob` (for pattern expansion)

Also create the `~/.finagent/output` and `~/.finagent/logs` directories on first use.

### Defaults & Limits
- Parallelism default: `min(3, os.cpus().length)`; cap at 10
- Batch import writes a single review JSON when `--review-output` is specified and `--auto` is false

### Flag Passthrough (optional)
- Support advanced fin-enhance flags: `--skip-llm`, `--confidence <float>`, `--force`

## Testing Strategy

### Manual Testing Scenarios:

1. **Basic array input**
   ```json
   {
     "pdfPaths": ["/path/to/statement1.pdf", "/path/to/statement2.pdf"],
     "autoApprove": false,
     "parallelism": 2
   }
   ```

2. **Glob pattern**
   ```json
   {
     "pdfPaths": "/path/to/statements/*.pdf",
     "autoApprove": true,
     "parallelism": 3
   }
   ```

3. **Error handling**
   - Mix of valid and invalid PDF paths
   - Verify partial success is reported correctly

4. **Review aggregation**
  - Import multiple CSVs with unresolved transactions
  - Verify consolidated review file is correct (dedupe by `id`; merge proposals by `(category, subcategory)`)

5. **Filename collisions**
  - Two PDFs sharing the same basename from different folders
  - Verify distinct CSV outputs are created and processed

6. **Unsupported bank PDF**
  - Ensure extraction failure is reported and batch continues

7. **Hybrid review flow**
  - New category, confidence 0.82, 3 occurrences in batch → auto-created and assigned
  - New category, confidence 0.78, 5 occurrences → routed to review (low confidence)
  - New category, confidence 0.90, 1 occurrence but history support_count=2 → auto-created (meets N via history+batch)
  - Existing category unaffected: still uses confidence-only auto-assign

### Unit Tests:

Consider adding:
- `tests/ccsdk/test-bulk-import.ts` if CCSDK supports testing
- Mock `execCommand` to test orchestration logic
- Test glob expansion logic
- Test result aggregation
- Test filename collision helper
- Test concurrency limiter (at-most-N tasks) by stubbing `execCommand`
- Hybrid policy tests in `tests/fin_enhance/test_hybrid_categorizer.py`:
  - Auto-assign when confidence≥0.80 and occurrences≥min
  - No auto-assign when confidence<threshold or occurrences<min
  - Dry-run logs “would auto-create” without side-effects

## Implementation Phases

### Phase 1: Basic Sequential Bulk Import
- [x] Add `bulk_import_statements` tool to `custom-tools.ts` *(2025-10-03; wraps new shared pipeline and emits JSON summary.)*
- [x] Implement path expansion (array + glob support) *(Tool expands globs via `glob` package; falls back to existence checks.)*
- [x] Implement sequential extraction (parallelism = 1) *(`ccsdk/bulk-import.ts` runs fin-extract per PDF sequentially.)*
- [x] Implement batch import *(Shared helper invokes single fin-enhance pass with aggregated CSVs.)*
- [ ] Test with 2-3 PDFs

### Phase 2: Parallel Extraction
- [ ] Add `p-limit` dependency
- [ ] Implement parallel extraction with concurrency control
- [ ] Add progress logging
- [ ] Test with 5-10 PDFs

### Phase 3: Error Handling (Batch Import Path)
- [x] Implement robust error handling (Promise.allSettled) *(Sequential loop captures per-file failures without aborting; summary includes errors.)*
- [x] Ensure single review file path is generated when `autoApprove = false` *(Shared helper writes `bulk-review-*.json` once.)*
- [x] Return detailed per-file status (extraction success/failure + import summary) *(Extraction array plus unsupported list returned to callers.)*
- [ ] Test error scenarios

### Phase 4: Review Flow (Hybrid Auto-Assign for New Categories)
- [ ] Add config flag `categorization.dynamic_categories.auto_assign_when_confident` (env: `FINCLI_DYNAMIC_CATEGORIES_AUTO_ASSIGN_WHEN_CONFIDENT`) default: enabled
- [ ] Use `categorization.confidence.auto_approve` (default 0.80) for both existing and new categories
- [ ] Require `min_transactions_for_new` (default 3) by combining in-batch occurrences with historical support counts
- [ ] Implement merchant-batch-level decision to ensure consistency; assign `method="llm:auto-new"` and create categories with `auto_generated=True`, `user_approved=False`
- [ ] Keep dry-run side-effects off; log “would auto-create” and include in summary
- [ ] Tests: high-confidence ≥ 0.80 and N≥min auto-assigns; below either threshold routes to review; existing categories unchanged

### Phase 5: Documentation & Polish
- [ ] Update CLAUDE.md with bulk import tool documentation
- [ ] Add usage examples
- [ ] Consider adding progress indicators
- [x] Update `ccsdk/cc-client.ts` allowed tools *(Added `mcp__finance__bulk_import_statements` so agents can call pipeline.)*
- [ ] Document flags passthrough and defaults

## Alternative Approaches Considered

### 1. Add `--bulk` flag to existing tools
**Rejected**: Would complicate existing simple tools unnecessarily

### 2. CLI-level batch command
**Rejected**: Doesn't solve the "agent trying to write bash scripts" problem

### 3. Full sub-agent parallelization
**Rejected**: Overkill, expensive, database contention issues (see analysis above)

## Open Questions

1. **Should we limit parallelism based on system resources?**
   - Proposal: Default 3, max 10
   - Consider: Detect CPU count and limit to CPU cores?

2. **Should extraction and import happen in one phase or two?**
   - Proposal: Extract all, then batch import (simpler, more efficient)
   - Alternative: Pipeline style (extract + import per file)

3. **How to handle review files when autoApprove = true?**
   - Proposal: Don't create review files at all
   - Alternative: Create empty review file for consistency

4. **Should we support recursive directory scanning?**
   - Proposal: Yes, via glob patterns (`/path/**/*.pdf`)
   - Keep simple: no need for separate recursive flag

## Success Criteria

1. Agent can import 10+ PDFs without writing bash scripts
2. Parallel extraction shows measurable speedup (e.g., 3x faster with parallelism=3)
3. Consolidated review file correctly aggregates all unresolved transactions
4. Partial failures don't abort the entire batch
5. Clear error messages for each failed file
6. No filename collisions across inputs with same basename

## Architecture Notes

- Batch mode uses one `fin-enhance` invocation for all CSVs. That yields one
  review JSON when `--review-output` is provided and `--auto` is not set. The
  earlier “single transaction” phrasing is corrected to “single invocation and
  connection,” not a monolithic SQLite transaction.
- Batching increases consistency: merchants are grouped once and LLM results are
  reused across all matching transactions in the run. Learned patterns and LLM
  cache continue to make later runs cheaper and faster.
- For very large batches, `fin-enhance` currently loads rows in memory; document
  this as a limitation and recommend splitting extremely large imports into
  several runs.

## Review Flow Policy (Hybrid)

Goal: Reduce first‑run review overload by allowing “new categories” to auto‑assign when both:
- Confidence is high (use `categorization.confidence.auto_approve`, default 0.80).
- Occurrences meet or exceed `categorization.dynamic_categories.min_transactions_for_new` (default 3), counting in‑batch occurrences for the merchant plus historical support from `category_suggestions`.

Details:
- Add config flag `categorization.dynamic_categories.auto_assign_when_confident` (env: `FINCLI_DYNAMIC_CATEGORIES_AUTO_ASSIGN_WHEN_CONFIDENT`). Default: enabled.
- Threshold: use `categorization.confidence.auto_approve` (0.80) for both existing and new categories.
- No per‑run cap (explicit decision for now).
- Behavior:
  - If a new category suggestion meets the above criteria and the category doesn’t exist yet, create it with `auto_generated=True`, `user_approved=False`, and assign immediately (`method="llm:auto-new"`).
  - Otherwise, route to review and continue recording suggestion support as today.
- Implementation approach:
  - Decide auto-assign at the merchant batch level for consistency: compute `batch_count = len(entries)` for the merchant; combine with existing `category_suggestions.support_count` to satisfy the N threshold once, then apply to all entries for that merchant.
  - Keep dry-run side-effects disabled, but log “would auto-create” and include in `auto_created_categories` summary for transparency.

Risks & mitigations:
- Potential taxonomy sprawl: mitigated by the N-occurrences rule and the global confidence threshold. Users can audit via `fin-analyze category_suggestions` and merge categories later.
