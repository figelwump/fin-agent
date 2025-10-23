# LLM-Based Statement Processor - Implementation Plan

**Created:** 2025-10-20
**Status:** Planning
**Goal:** Replace fin-extract/fin-enhance with LLM-based extraction via statement-processor skill

## Overview

Simplify the statement processing pipeline by using fin-scrub + LLM to extract and categorize transactions in one pass, eliminating the need for bank-specific extractors and separate categorization steps.

### Current Flow (Complex)
```
PDF → fin-extract (bank-specific parsers) → CSV → fin-enhance (OpenAI API) → review.json → manual edit → apply-review → SQLite
```

### New Flow (Simplified)
```
PDF → fin-scrub (PII redaction) → scrubbed text → Claude (with taxonomies) → CSV/SQLite
                                                            ↓
                                                   (if low confidence)
                                                            ↓
                                             Interactive conversation with user
```

## Key Benefits

- **Single LLM context**: Claude already in conversation, no separate API calls
- **No bank-specific code**: LLM handles parsing variations
- **Better UX**: Direct conversation vs JSON file editing
- **Less maintenance**: No extractors to update when banks change formats
- **Taxonomy consistency**: Existing merchants/categories fed to prompt
- **Flexible**: Handles edge cases conversationally
- **Batch processing**: Process multiple statements efficiently in one LLM call

## Architecture

### Components

1. **fin-scrub** (exists): PDF → scrubbed text with transactions visible
2. **fin-query saved merchants** (new): Query to get unique merchant list
3. **statement-processor preprocess helper** (new): Deterministic prompt builder that lives alongside the skill
4. **statement-processor skill** (updated): Orchestrate extraction + review
5. **Post-processing helper** (new): Convert LLM CSV rows into enriched records (`account_key`, `fingerprint`, normalized fields)
6. **fin-edit** (exists): Write validated transactions to DB

### CSV Output Format

Must match database schema + include deduplication support. The LLM-generated rows supply the business fields (date, merchant, amount, original_description, account metadata, categories); the statement-processor skill post-processes those rows to add the derived `account_key` and `fingerprint` hashes before import.

```csv
date,merchant,amount,original_description,account_name,institution,account_type,category,subcategory,confidence,account_key,fingerprint
2025-09-15,Amazon,45.67,"AMZN Mktp US*7X51S5QT3",Chase Prime Visa,Chase,credit,Shopping,Online Retail,0.95,chase-prime-visa,abc123def456
```

**Columns:**
- `date`: YYYY-MM-DD
- `merchant`: Normalized merchant name
- `amount`: Positive decimal for debits
- `original_description`: Raw from statement
- `account_name`: Account identifier (e.g., "Chase Prime Visa")
- `institution`: Bank/issuer name surfaced in the statement header
- `account_type`: "credit" | "checking" | "savings"
- `category`: Main category
- `subcategory`: Sub-category
- `confidence`: 0.0-1.0 categorization confidence
- `account_key`: Derived via `compute_account_key(account_name, institution, account_type)` during post-processing
- `fingerprint`: Derived via `compute_transaction_fingerprint(date, amount, merchant, account_key)` during post-processing

## Phase 1: Add Saved Query for Merchants

**Goal:** Enable `fin-query saved merchants` to get unique merchant list for prompt building

### Tasks

- [x] Extend `fin_cli/fin_query` saved query catalog with a `merchants` query that returns `merchant` and `count` *(completed 2025-10-20 — added SQL + CLI wiring + tests)*
  - Base query orders by `count DESC, merchant` so `--limit` doubles as `--top`
  - Wire `--min-count N` to a `HAVING count >= :min_count` clause (default 1)
  - Ensure JSON output is an array of `{"merchant": str, "count": int}` objects for prompt-friendly consumption

### Implementation Notes

```python
# in saved_queries.py
SAVED_QUERIES["merchants"] = {
    "sql": """
        SELECT merchant, COUNT(*) as count
        FROM transactions
        WHERE merchant IS NOT NULL AND merchant != ''
        GROUP BY merchant
        HAVING count >= :min_count
        ORDER BY count DESC, merchant
    """,
    "description": "List unique merchants for LLM prompt building",
    "supports_limit": True,
    "default_params": {"min_count": 1},
}
```

### Acceptance Criteria

- [x] `fin-query saved merchants --format json` returns `[{"merchant": "Amazon", "count": 42}, …]`
- [x] `fin-query saved merchants --top 100` limits to top 100 by frequency *(via --limit)*
- [x] `fin-query saved merchants --min-count 5` filters out low-frequency merchants *(new CLI flag)*
- [x] Documentation updated in statement-processor skill notes so LLM prompt builders know how to consume the query *(2025-10-21 — added taxonomy refresh section to `.claude/skills/statement-processor/SKILL.md`)*

## Phase 2: Build Preprocessing Helper

**Goal:** Deterministic prompt builder that lives inside the statement-processor skill package

### Tasks

- [x] Add `skills/statement-processor/preprocess.py` *(2025-10-20 — includes callable + Click CLI shim)*
  - Provide a callable `build_prompt(scrubbed_texts: list[str], *, max_merchants: int | None, categories_only: bool) -> str`
  - Load existing merchants via `fin-query saved merchants`
  - Load existing categories via `fin-query saved categories`
  - Format taxonomies for prompt injection
  - Assemble final prompt from a Jinja-style template
  - Expose a simple CLI wrapper (`python skills/statement-processor/preprocess.py --input …`) for local use, but keep it colocated with the skill

- [x] Create prompt template in `skills/statement-processor/templates/extraction_prompt.txt`
  - Include all rules from the prompt in previous message
  - Use placeholder tokens: `{EXISTING_MERCHANTS}`, `{EXISTING_CATEGORIES}`, `{SCRUBBED_STATEMENT_TEXT}`
  - Include CSV format specification with all required columns
  - Include account detection guidance
  - Clarify that LLM returns `account_name`, `institution`, and `account_type`; downstream tooling derives `account_key`/`fingerprint`

- [x] Support batch mode directly in the helper
  - Accept multiple scrubbed statement files; auto-label sections with headers
  - Optional: `--max-merchants N` to limit taxonomy size
  - Optional: `--categories-only` to include only categories (for re-categorization tasks)
  - Optional: `--max-statements-per-prompt M` to auto-chunk large batches

### Account Detection Guidance

Add to prompt template:

```
# ACCOUNT IDENTIFICATION
From the statement, determine:
- account_name: The specific account name (e.g., "Chase Sapphire Reserve", "Mercury Checking")
- institution: Bank/issuer name as shown in the statement header (e.g., "Chase", "Mercury")
- account_type: One of: "credit", "checking", "savings"

Look for account identifiers in:
- Statement headers/titles
- Account numbers (last 4 digits)
- Card names
- Institution names + account type

Examples:
- "Amazon Prime Visa" → account_name: "Chase Amazon Prime Visa", institution: "Chase", account_type: "credit"
- "Mercury ••2550" → account_name: "Mercury Checking 2550", institution: "Mercury", account_type: "checking"
- "Chase Sapphire Reserve" → account_name: "Chase Sapphire Reserve", institution: "Chase", account_type: "credit"

The post-processing step will convert these fields into a stable `account_key` using the shared helper.
```

### Helper Usage

```bash
# Build prompt with taxonomies for single statement
python skills/statement-processor/preprocess.py --input statement-scrubbed.txt --output extraction-prompt.txt

# Limit merchant taxonomy size
python skills/statement-processor/preprocess.py --input statement-scrubbed.txt --max-merchants 100

# Output to stdout for piping
python skills/statement-processor/preprocess.py --input statement-scrubbed.txt

# Batch mode: process multiple statements
python skills/statement-processor/preprocess.py --batch \
  --input chase-sept.txt bofa-sept.txt mercury-sept.txt \
  --output batch-prompt.txt

# Override default chunk size for long batches
python skills/statement-processor/preprocess.py --batch --max-statements-per-prompt 2 --input *.txt
```

### Acceptance Criteria

- [x] Helper loads taxonomies from database *(preprocess.build_prompt fetches categories/merchants via fin-query executor)*
- [x] Helper formats taxonomies clearly for LLM *(merchants/categories rendered as bullet lists in templates)*
- [x] Helper injects scrubbed statement text *(single and batch templates embed the redacted text blocks)*
- [x] Prompt includes all required columns in CSV format *(templates specify `date,…,confidence` header)*
- [x] Prompt includes account detection guidance *(copied guidance block in both templates)*
- [x] Helper is deterministic (same input = same output) *(pure functions + tests cover stable rendering)*
- [x] Helper has tests validating prompt structure and chunking *(see tests/statement_processor/test_preprocess.py)*
- [x] Batch mode supported: multiple statements in one prompt *(batch template + CLI `--batch`)*
- [x] Batch mode clearly separates statements and output expectations *(templates emit per-statement headers)*
- [x] Batch mode auto-chunks when more statements than `--max-statements-per-prompt`
- [x] Post-processing utility appends `account_key` and `fingerprint` using shared model helpers before persistence/CSV export *(see skills/statement-processor/postprocess.py)*

## Phase 3: Update statement-processor Skill

**Goal:** Rewrite skill to use LLM-based extraction workflow

### Tasks

- [x] Update `skills/statement-processor/SKILL.md` *(2025-10-20 — rewritten for preprocess/postprocess pipeline; examples still pending)*
  - Simplify workflow to 4 steps: scrub, build-prompt, extract, review
  - Add examples showing full flow
  - Document how to handle low-confidence items
  - Remove references to fin-extract, fin-import, fin-enhance
  - Document the interactive fallback path for ambiguous account detection (prompt user for `account_name`/`account_key` before write)
  - Call out that the skill computes `account_key`/`fingerprint` automatically before persistence so the LLM only provides raw account metadata
  - Document the canonical working directory for artifacts (`~/.finagent/skills/statement-processor/<timestamp>/`)
  - Flag legacy examples/troubleshooting docs for rewrite or archival

- [x] Implement `skills/statement-processor/postprocess.py` *(2025-10-20 — enrich_rows helper + CSV CLI)*
  - Accept parsed LLM rows and inject `account_key`/`fingerprint` via shared model helpers
  - Normalize merchant casing/whitespace to match existing dedupe expectations
  - Provide reusable function for both CSV export and direct DB writes

- [x] Create `skills/statement-processor/examples/llm-extraction.md`
  - Step-by-step example with real scrubbed statement
  - Show prompt building
  - Show LLM extraction
  - Show validation and review
  - Show post-processing that derives `account_key`/`fingerprint`
  - Show writing to database

- [x] Update `skills/statement-processor/examples/single-statement.md`
  - Replaced with `examples/llm-extraction.md` walkthrough for the new pipeline

- [x] Create `skills/statement-processor/reference/csv-format.md`
  - Document required CSV columns
  - Document how the post-processing step derives `account_key` and `fingerprint`
  - Document account identification
  - Call out that `account_key` must combine institution + account slug for stable dedupe
  - Provide examples

- [x] Update or archive `skills/statement-processor/examples/batch-processing.md`
  - Rewrote to follow preprocess/postprocess workflow with chunked prompts

- [x] Update or archive `skills/statement-processor/examples/pipe-mode.md`
  - Removed legacy doc; new workflow documented in SKILL.md and `examples/batch-processing.md`

- [x] Remove or replace `skills/statement-processor/troubleshooting/extraction-errors.md` *(legacy extractor doc deleted 2025-10-20; add LLM-focused troubleshooting later if needed)*

### New Skill Workflow

```markdown
# Statement Processor Skill (LLM-Based)

## Quick Start - Single Statement

1. **Extract and redact PII**
   ```bash
   fin-scrub statement.pdf --output statement-scrubbed.txt
   ```

2. **Build extraction prompt with taxonomies**
   ```bash
   python skills/statement-processor/preprocess.py --input statement-scrubbed.txt --output prompt.txt
   ```

3. **Extract transactions** (Claude does this)
   - Read the prompt file
   - Call Claude's LLM with the prompt
   - Parse CSV response
   - Validate format and required columns

4. **Post-process rows**
   - Use `statement_processor.postprocess.enrich_rows` to add `account_key` + `fingerprint`
   - Normalize merchant casing/whitespace for dedupe consistency
   - Produce enriched CSV/records for review

5. **Review low-confidence items** (if any)
   - For transactions with confidence < 0.7, ask user interactively
   - Update category/merchant as needed
   - Increase confidence to 1.0 after user confirms

6. **Write to database**
   ```bash
   # Option A: Use fin-edit for validated writes
   fin-edit import-transactions transactions.csv

   # Option B: Direct SQL (for batch)
   sqlite3 ~/.finagent/data.db < import.sql
   ```

## Quick Start - Batch Processing

1. **Scrub all statements**
   ```bash
   for pdf in *.pdf; do
     fin-scrub "$pdf" --output "${pdf%.pdf}-scrubbed.txt"
   done
   ```

2. **Build batch prompt**
   ```bash
   python skills/statement-processor/preprocess.py --batch \
     --input *-scrubbed.txt \
     --output batch-prompt.txt
   ```

3. **Extract all transactions in one pass**
   - Claude processes all statements together
   - Returns single CSV with all transactions
   - Account info disambiguates statements

4. **Post-process rows**
   - Enrich each row with `account_key`/`fingerprint`
   - Split oversized batches into multiple chunks as needed

5. **Batch review**
   - Review all low-confidence items together
   - Efficient for multiple statements from same month

6. **Import to database**
   ```bash
   fin-edit import-transactions all-transactions.csv
   ```

## Environment
```bash
source .venv/bin/activate
```

## Available Commands

- `fin-scrub <pdf>` - Extract and redact PII from statement
- `python skills/statement-processor/preprocess.py` - Build extraction prompt with taxonomies
- `python skills/statement-processor/postprocess.py` - Enrich LLM CSV rows with `account_key`/`fingerprint`
- `fin-query saved merchants` - Get existing merchant list
- `fin-query saved categories` - Get existing category taxonomy
- `fin-edit import-transactions` - Import validated CSV to database
```

### Acceptance Criteria

- [x] Skill instructions are clear and actionable *(2025-10-21 — SKILL.md clarifies manual corrections, merchant pattern learning, and validation steps)*
- [x] Examples show complete end-to-end flow *(2025-10-21 — updated `examples/llm-extraction.md` and `examples/batch-processing.md` with review, import, and archival guidance)*
- [x] Low-confidence review process is documented *(2025-10-21 — SKILL.md and examples now outline CLI correction workflow and confidence escalation)*
- [x] Database write options are explained *(2025-10-21 — added explicit preview/apply instructions and validation commands in SKILL.md)*
- [x] No references to deprecated tools *(2025-10-21 — scrubbed fin-extract/fin-enhance mentions and refreshed reference section)*

## Phase 4: Test and Validate

**Goal:** Validate accuracy vs existing extractors and measure performance

### Test Strategy

#### 4.1 Extraction Accuracy Test

- [ ] Maintain `statements/validation/` corpus with anonymised statements + gold CSVs (target ≥10 docs spanning Chase, BofA, Mercury, and at least 2 "unknown" issuers)
- [ ] Run gold set through current flow (fin-extract + fin-enhance) to establish baseline metrics
- [ ] Replay the same set through new flow (fin-scrub + LLM)
- [ ] Compare outputs:
  - Transaction count match
  - Date/amount accuracy
  - Merchant normalization consistency
  - Category assignment agreement
  - False positives/negatives (excluded transactions)

#### 4.2 Taxonomy Consistency Test

- [ ] Process 5 statements with existing merchants/categories in taxonomy
- [ ] Qualitatively assess:
  - Are existing merchants being reused appropriately?
  - Are new merchants normalized consistently?
  - Are existing categories being chosen appropriately?
  - Is the LLM creating unnecessary duplicate categories/merchants?
- [ ] Document any taxonomy bloat issues and refine prompt if needed; keep diffs with validation fixture

#### 4.3 Edge Cases Test

Test handling of:
- [ ] Foreign currency transactions
- [ ] Multi-line transactions
- [ ] Transfers vs purchases (filtering accuracy)
- [ ] Credit card payments (should be excluded)
- [ ] Refunds/credits (should be excluded)
- [ ] Duplicate entries within same statement
- [ ] Account identification accuracy

#### 4.4 Performance Metrics

- [ ] Token usage per statement (for cost estimation)
- [ ] Time to process (vs current pipeline)
- [ ] User intervention rate (low-confidence items requiring review)

### Success Criteria

- ✓ >95% accuracy on transaction extraction (date/amount/merchant)
- ✓ >95% correct transaction filtering (debits only, excludes transfers/payments)
- ✓ <10% require user review (confidence < 0.7)
- ✓ Faster than current pipeline for single statements
- ✓ Cost-effective for typical monthly usage

## Phase 5: Migration and Deprecation Strategy

**Goal:** Plan transition from old tools to new workflow

### 5.1 Deprecation Decision Tree

```
IF (Phase 4 tests pass success criteria)
  THEN:
    - Mark fin-extract as deprecated
    - Mark fin-enhance as deprecated
    - Update README with new workflow
    - Add deprecation warnings to old tools
  ELSE:
    - Keep both workflows
    - Document trade-offs
    - Let users choose
```

### 5.2 What Gets Deprecated (if successful)

- [ ] `fin-extract` - Replaced by fin-scrub + LLM
- [ ] `fin-enhance` - Categorization now happens during extraction
- [ ] `fin-export` - Report generation replaced by spending-analyzer skill
- [ ] `fin-import` - Not needed (was going to be built, now unnecessary)
- [ ] Bank-specific extractors - No longer maintained
- [ ] Declarative YAML specs - No longer needed

### 5.3 What Gets Kept

- ✓ `fin-scrub` - Core component for PII redaction
- ✓ `fin-query` - Essential for reading data
- ✓ `fin-analyze` - Analysis unchanged
- ✓ `fin-edit` - Safe writes to database
- ✓ `statement-processor/preprocess.py` - Builds extraction prompts with taxonomies

### 5.4 Migration Path for Existing Users

```markdown
## Migrating to LLM-Based Processing

### For Interactive Users
1. Update to latest version
2. Use new statement-processor skill workflow
3. Old data remains compatible

### For Automated Scripts
Option A: Switch to new workflow (single statement)
- Replace: `fin-extract $pdf --output $csv && fin-enhance $csv`
- With: `fin-scrub $pdf --output scrubbed.txt && python skills/statement-processor/preprocess.py --input scrubbed.txt | claude-extract > transactions.csv`

Option B: Switch to new workflow (batch)
- Process multiple statements efficiently in one LLM call
- `fin-scrub *.pdf` → batch prompt → single CSV output

Option C: Keep using fin-extract (deprecated but functional)
- Tools remain available but unmaintained
- Security/bug fixes only
```

### 5.5 Documentation Updates

- [ ] Update main README with new workflow
- [ ] Add "Migration Guide" document
- [ ] Update fin-extract README with deprecation notice
- [ ] Update fin-enhance README with deprecation notice
- [ ] Add "Why we deprecated extractors" explainer
- [ ] Update CLAUDE.md with new architecture

## Phase 6: Polish and Optimization

**Goal:** Refine based on real usage

### 6.1 Prompt Optimization

- [ ] A/B test different prompt phrasings
- [ ] Optimize merchant normalization rules
- [ ] Refine confidence scoring guidance
- [ ] Add examples of ambiguous cases to prompt
- [ ] Test with different LLM models (if needed)

### 6.2 Error Handling

- [ ] Handle malformed CSV responses
- [ ] Handle missing required columns
- [ ] Handle invalid dates/amounts
- [ ] Handle fingerprint collisions
- [ ] Provide clear error messages

### 6.3 Batch Processing Optimization

- [ ] Test token efficiency: single prompt vs multiple prompts
- [ ] Optimize batch prompt structure for clarity
- [ ] Handle mixed statement types (checking + credit) in one batch
- [ ] Accumulate low-confidence items for batch review
- [ ] Progress reporting for multi-statement processing
- [ ] Consider statement ordering (chronological vs by account)

### 6.4 Advanced Features (Optional)

- [ ] Learning from corrections: Update prompt with user fixes
- [ ] Merchant aliasing: "AMZN" → "Amazon" via learned patterns
- [ ] Category suggestions based on similar transactions
- [x] Automatic pattern learning (similar to merchant_patterns table) *(2025-10-21 — `fin-edit import-transactions` now supports `--learn-patterns/--learn-threshold`, enabling the skill to persist high-confidence merchants automatically.)*
- [x] Post-process pattern application: apply `merchant_patterns` to rows before categorization prompts so known merchants skip the LLM; feed leftover rows into a lightweight LLM micro-prompt with live taxonomies. *(2025-10-21 — `postprocess.py --apply-patterns` now fills categories/confidence from the DB; `categorize_leftovers.py` assembles a compact prompt for the remaining transactions.)*

## Implementation Notes

### Taxonomy Size Management

Large taxonomies can bloat prompts. Strategies:

1. **Top N merchants**: Only include top 100-200 most frequent
2. **Recent merchants**: Only include merchants used in last 6 months
3. **Smart filtering**: Include merchants similar to those in statement
4. **Tiered approach**: Core taxonomy + extended taxonomy on-demand

### Fingerprint Generation

Critical for deduplication. Options:

1. **LLM generates**: Include md5 logic in prompt (may be inconsistent)
2. **Post-process**: Generate fingerprints after LLM extraction (more reliable)
3. **Hybrid**: LLM uses simple fingerprint, post-process validates/regenerates

**Recommendation**: Post-process fingerprints for consistency.

### Account Identification

Account detection from scrubbed statements may be challenging if account numbers are redacted. Strategies:

1. **Pattern matching**: Look for account name keywords (e.g., "Prime Visa")
2. **User hints**: Allow user to specify account upfront
3. **Interactive**: Ask user if account unclear
4. **Last 4 digits**: Use `[ACCOUNT_LAST4:1234]` placeholders preserved by fin-scrub

### Confidence Calibration

Initial confidence scores may be over/under-confident. Monitor and adjust:

- Track user corrections by confidence level
- If >50% of 0.9 confidence items need correction → recalibrate prompt
- Build calibration dataset over time

### Merchant Patterns

- `merchant_patterns` remains an active rules cache. Legacy `fin-enhance` still auto-upserts via `HybridCategorizer._record_merchant_pattern`, so the new statement-processor workflow must keep contributing to this table.
- Until automatic learning ships, the skill should call `fin-edit add-merchant-pattern` (dry-run, then `--apply`) whenever the user confirms that a merchant/category pairing should persist. Reuse `fin_cli.shared.merchants.merchant_pattern_key()` to derive the deterministic pattern string and pass any LLM-provided display/metadata through `--display`/`--metadata`.
- Follow-up enhancements:
  1. Add a post-processing pass that applies existing `merchant_patterns` (fill category/subcategory/confidence from the DB before any categorization prompt runs).
  2. For the remaining uncategorized merchants, issue a single lightweight micro-prompt seeded with live category + merchant taxonomies—no chunking needed because the leftover set should be small.

## Batch Processing Strategy

### Approach: Single Prompt with Multiple Statements

When processing multiple statements in batch mode, `python skills/statement-processor/preprocess.py --batch` will:

1. **Structure the prompt** with clear statement boundaries:
```
# STATEMENT 1: Chase Prime Visa (September 2025)
[scrubbed text for statement 1]

# STATEMENT 2: Mercury Checking (September 2025)
[scrubbed text for statement 2]

# STATEMENT 3: BofA Checking (September 2025)
[scrubbed text for statement 3]
```

2. **Request combined CSV output** with account metadata (account_name, institution, account_type) for downstream disambiguation
3. **Single LLM call** processes all statements together
4. **Taxonomy reuse** across statements (more consistent merchant/category assignment)

### Benefits of Batch Processing

- ✅ **Token efficiency**: Taxonomies sent once, not per statement
- ✅ **Consistency**: Same merchant across statements gets same normalized name
- ✅ **Faster**: One LLM call vs N calls
- ✅ **Cheaper**: Reduced API overhead
- ✅ **Better categorization**: LLM sees related transactions across accounts

### Batch Limits

- **Max statements per batch**: ~3-5 statements (token limit dependent)
- **Max tokens**: Monitor prompt + expected output < context window
- **Fallback**: If batch too large, split into multiple batches automatically

### Example Batch Output

```csv
date,merchant,amount,original_description,account_name,institution,account_type,category,subcategory,confidence,account_key,fingerprint
2025-09-15,Amazon,45.67,"AMZN Mktp US*7X",Chase Prime Visa,Chase,credit,Shopping,Online,0.95,chase-prime-visa,abc123
2025-09-16,Starbucks,5.50,"STARBUCKS #1234",Mercury Checking,Mercury,checking,Food & Dining,Coffee,1.0,mercury-checking-2550,def456
2025-09-17,Amazon,23.99,"AMZN Mktp US*8Y",BofA Checking,Bank of America,checking,Shopping,Online,0.95,bofa-checking-1234,ghi789
```

Note: Same merchant "Amazon" gets consistent normalization across different accounts.

## Technical Decisions

### Why Not Structured Output (JSON)?

CSV chosen over JSON because:
- Simpler to parse and validate
- More robust to LLM formatting errors
- Compatible with existing import tools
- Easier for humans to inspect/edit if needed

### Why Build Prompt with Script?

Deterministic prompt building (vs Claude doing it) because:
- Reproducible: same taxonomies → same prompt
- Testable: can validate prompt structure
- Cacheable: can cache prompt if taxonomies unchanged
- Debuggable: easier to inspect what LLM receives

### Why Post-Process Fingerprints?

Generate fingerprints after LLM extraction (vs having LLM generate) because:
- Consistency: MD5 generation must be exact for deduplication
- Reliability: LLMs can be inconsistent with hash generation
- Simplicity: Removes complex logic from prompt
- Validation: Can verify before database write

## Success Metrics

Track these metrics over time:

- **Accuracy**: % of transactions extracted correctly
- **Taxonomy growth**: Rate of new merchants/categories
- **Review rate**: % of transactions needing user review
- **Processing time**: Average time per statement
- **Token usage**: Average tokens per statement (cost proxy)
- **User satisfaction**: Qualitative feedback on workflow

## Rollback Plan

If LLM approach doesn't meet success criteria:

1. Keep fin-extract/fin-enhance as primary workflow
2. Offer LLM extraction as experimental opt-in feature
3. Document trade-offs (accuracy vs flexibility)
4. Continue maintaining bank extractors
5. Revisit when LLM accuracy improves

## Related Files

### New Files
- `fin_cli/fin_query/queries/merchants.sql` - Merchant frequency saved query
- `skills/statement-processor/preprocess.py` - Prompt builder helper (callable + CLI shim)
- `skills/statement-processor/postprocess.py` - Post-processing helper (account_key + fingerprint)
- `skills/statement-processor/templates/extraction_prompt.txt` - Prompt template
- `skills/statement-processor/templates/batch_extraction_prompt.txt` - Batch prompt template
- `skills/statement-processor/examples/llm-extraction.md` - LLM workflow example
- `skills/statement-processor/examples/batch-processing.md` - Batch workflow example
- `skills/statement-processor/reference/csv-format.md` - CSV format docs

### Updated Files
- `fin_cli/fin_query/main.py` - Add `--min-count` support for saved queries
- `fin_cli/fin_query/queries/index.yaml` - Register merchants saved query
- `skills/statement-processor/SKILL.md` - Updated workflow with LLM approach
- `skills/statement-processor/examples/single-statement.md` - Updated example
- `README.md` - Document new workflow
- `CLAUDE.md` - Update architecture notes

### Potentially Deprecated Files
- `fin_cli/fin_extract/extractors/*.py` - Bank-specific extractors
- `fin_cli/fin_extract/bundled_specs/*.yaml` - Declarative specs
- `fin_cli/fin_extract/declarative.py` - Declarative runtime
- `fin_cli/fin_enhance/` - Entire package (if successful)
- `fin_cli/fin_export/` - Report generation (replaced by spending-analyzer skill)

## Timeline Estimate

- **Phase 1** (Merchants query): 2-4 hours
- **Phase 2** (Prompt builder): 1-2 days
- **Phase 3** (Update skill): 1 day
- **Phase 4** (Testing): 2-3 days
- **Phase 5** (Migration planning): 4-8 hours
- **Phase 6** (Polish): 1-2 days

**Total**: 5-7 days of focused work

## Open Questions & Decisions

1. **Unknown/new banks** — Lean on the statement-processor skill's clarification flow: when the prompt builder cannot infer account metadata, the skill asks the user for the account label/institution before writing so the post-processor can derive `account_key` correctly. Document this in Phase 3 so the interactive path is the default fallback rather than bespoke bank code.
2. **Validation dataset** — Yes. Curate a sanitized corpus under `statements/validation/` with gold CSV outputs and wire Phase 4 tests to replay it. This gives us regression coverage for prompt/template changes.
3. **Fallback workflow** — No legacy fallback in the initial release. We’ll monitor validation metrics; if accuracy slips below SLAs, revisit adding an escape hatch in a future iteration.
4. **Format changes over time** — The validation suite above doubles as drift detection. Add a quarterly review task in Phase 6 to refresh prompts/taxonomies and capture new statement patterns.
5. **Fingerprint ingredients** — Stay with `{date}|{merchant}|{amount}|{account_key}`; `account_key` already encodes institution + account slug. Post-processing will call the shared helper, ensuring normalization stays consistent across pipelines.
6. **Batch strategy** — Default to a single prompt chunk per ≤3 statements; when more are passed, automatically chunk and run sequential prompts while reusing the taxonomy payload. Phase 2's CLI should expose a `--max-statements-per-prompt` knob to make this tunable.

## Next Steps

1. ✅ Review this plan with user
2. Get user approval on approach
3. Start with Phase 1 (merchants query)
4. Build Phase 2 prototype and test on sample statement
5. Evaluate accuracy before proceeding to Phase 3
