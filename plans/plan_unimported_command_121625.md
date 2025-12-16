# Plan: `fin-query unimported` Command

**Goal**: Add a CLI command to identify statement files that haven't been imported yet.

## Problem
When users have multiple PDFs in a statements directory, they currently need to:
1. List files with `ls`
2. Query the documents table
3. Manually compare to find unimported files

This is tedious for bulk imports.

## Solution Overview
Add `fin-query unimported <directory>` that:
1. Scans a directory for PDF files
2. Hashes each PDF
3. Compares against a new `source_file_hash` column in the `documents` table
4. Returns list of files not yet imported

## Design Decisions

### Why hash-based matching?
- **Filename matching is fragile**: filenames can change, be renamed, etc.
- **Hash is deterministic**: same PDF always produces same hash
- **Handles duplicates**: if same statement exists in multiple directories, only one is "imported"

### Storage approach
Store the original PDF hash in the `documents` table alongside the existing `document_hash` (which is the scrubbed content hash).

---

## Phase 1: Schema Migration

- [x] Add migration for `source_file_hash` column on `documents` table
  - File: `fin_cli/shared/migrations/NNN_add_source_file_hash.py`
  - Column: `source_file_hash TEXT` (nullable for backwards compat)
  - Add index for efficient lookups

**Files to modify:**
- `fin_cli/shared/migrations/` - new migration file

---

## Phase 2: Capture Source Hash During Import

- [x] Modify `fin-scrub` to output source file hash
  - Used Option C: Embed hash as first line comment in scrubbed file
  - Added `--no-source-hash` flag to disable if needed
  - File: `fin_cli/fin_scrub/main.py`

- [x] Update postprocess.py to parse embedded hash
  - Read hash from scrubbed file header
  - Add `source_file_hash` to the enriched payload
  - File: `.claude/skills/asset-tracker/scripts/postprocess.py`

- [x] Update `fin-edit asset-import` to store `source_file_hash`
  - Accept in payload document block
  - Insert into documents table
  - Files: `fin_cli/fin_edit/main.py`, `fin_cli/shared/models.py`

**Files to modify:**
- `fin_cli/fin_scrub/main.py` - embed hash in output
- `.claude/skills/asset-tracker/scripts/postprocess.py` - parse hash
- `fin_cli/fin_edit/main.py` (or wherever asset-import lives) - store hash

---

## Phase 3: Add `fin-query unimported` Command

- [x] Add new subcommand to fin-query CLI
  - Takes directory path as argument
  - Optional `--recursive` flag to scan subdirectories
  - Optional `--format` (table/csv/json) for output
  - File: `fin_cli/fin_query/main.py`

- [x] Implementation logic:
  1. Glob for `*.pdf` and `*.PDF` in directory
  2. For each PDF, compute SHA256 hash using `compute_file_sha256`
  3. Query documents table: `SELECT source_file_hash FROM documents WHERE source_file_hash IS NOT NULL`
  4. Filter to files whose hash is NOT in the DB
  5. Return list of unimported file paths with count summary

---

## Phase 4: Update SKILL.md Documentation

- [x] Add section about checking for unimported files before bulk import
- [x] Add command to Available Commands list
- [x] Example workflow added:
  ```bash
  # Check what hasn't been imported yet
  fin-query unimported statements/schwab/

  # Import each one...
  ```
- File: `.claude/skills/asset-tracker/SKILL.md`

---

## Implementation Notes

### Embedded hash format (Phase 2)
First line of scrubbed file:
```
# SOURCE_HASH: abc123def456...
```
This is easily parseable and won't interfere with content.

### Backwards compatibility
- Existing documents won't have `source_file_hash` - they'll show as "unknown" status
- The `unimported` command will only be reliable for newly imported documents
- Could add a backfill command later if needed

### Edge cases
- Multiple PDFs with same content (hash collision) - rare but possible
- Scanned vs native PDFs - hash will differ even for "same" statement
- Password-protected PDFs - can't hash content, only file bytes (this is fine)

---

## Testing

- [x] All existing tests pass (165 passed)
- [x] Manual testing: `fin-query unimported --help` shows correct options
- [x] Manual testing: `fin-query unimported statements/schwab/` runs correctly
- [ ] Future: Unit test for hash embedding in fin-scrub
- [ ] Future: Unit test for hash parsing in postprocess
- [ ] Future: Integration test for full import workflow with hash

---

## Future Enhancements (not in scope)
- Backfill existing documents with source hashes
- Support for non-PDF statements (CSV, etc.)
- "Smart" matching that suggests likely matches for unhashed documents
