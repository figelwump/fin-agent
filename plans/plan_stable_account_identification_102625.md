# Stable Account Identification via Last 4 Digits

**Created:** 2025-10-26  
**Revised:** 2025-10-27  
**Status:** Planning  
**Goal:** Enforce `institution + account_type + last_4_digits` as the canonical account identity; adopt a v2 `account_key` based on that triple; make fingerprints DB‑independent. No data migration is needed (dev DB can be reset).

## Problem Statement

Current account identification relies on matching LLM‑generated `account_name` strings and a schema that enforces `UNIQUE(name)`. This causes:
- Duplicate accounts when `account_name` formatting varies.
- Duplicate transactions and inflated reports.

Root cause:
- `upsert_account()` matches only on `name`.
- `accounts.name` is `UNIQUE`, forcing name‑based identity.
- Extraction did not consistently include last 4 digits, and `account_key` excludes last 4.

## Solution Architecture

Adopt a stable triple identity and key:
1) Schema: add `last_4_digits` and drop `UNIQUE(name)`; add partial `UNIQUE (institution, account_type, last_4_digits)` when last4 present.
2) Extraction: require `last_4_digits` and standardize `account_name` without trailing digits.
3) Matching: update `upsert_account()` to match by `(institution, account_type, last_4_digits)` first.
4) Keys & fingerprints: introduce `account_key_v2 = sha256(lower(institution)|lower(account_type)|last_4_digits)` and make fingerprints prefer this key; downstream always recomputes the key and warns on mismatches.
5) Simplicity: reset the dev DB instead of migrating or merging legacy rows.

---

## Phase 1: Database Schema Changes

### 1.1 Add last_4_digits and new uniqueness (SQL migration)
- [ ] Create SQL migration `fin_cli/shared/migrations/005_accounts_last4.sql` using the existing runner:
  - Rebuild `accounts` to add `last_4_digits TEXT` and remove `UNIQUE(name)`.
  - `CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_inst_type_last4 ON accounts(institution, account_type, last_4_digits) WHERE last_4_digits IS NOT NULL;`
  - `CREATE INDEX IF NOT EXISTS idx_accounts_inst_last4 ON accounts(institution, last_4_digits);`

### 1.2 No backfill/migration of data (dev reset)
- [ ] Skip any data backfill; plan to reset the DB after deploying migration/code.

Relevant files:
- Schema reference: `fin_cli/shared/migrations/001_initial.sql`
- Migration loader: `fin_cli/shared/database.py`

Technical decisions:
- Keep `last_4_digits` nullable; enforce uniqueness only when present.

---

## Phase 2: Update CSV Schema and Extraction

### 2.1 Update LLM extraction prompt
File: `.claude/skills/statement-processor/templates/extraction_prompt.txt`

Changes:
- [ ] Update header to include last 4:
  - OLD: `date,merchant,amount,original_description,account_name,institution,account_type,category,subcategory,confidence`
  - NEW: `date,merchant,amount,original_description,account_name,institution,account_type,last_4_digits,category,subcategory,confidence`
- [ ] Rules: `last_4_digits` is REQUIRED (exactly 4 digits). `account_name` MUST NOT include trailing digits.
- [ ] Guidance: show where to find masked 4 digits and examples for omitting them from `account_name`.

### 2.2 Update CSV parsing and validation
File: `fin_cli/shared/importers.py`

- [ ] Add `last_4_digits` to `_REQUIRED_ENRICHED_COLUMNS` and the `EnrichedCSVTransaction` dataclass.
- [ ] Validate `last_4_digits` is exactly 4 digits.
- [ ] Recompute `account_key_v2` (institution+account_type+last_4_digits) and ignore supplied key for identity; if a CSV `account_key` exists, warn on mismatch.

### 2.3 Update postprocessing script
File: `.claude/skills/statement-processor/scripts/postprocess.py`

- [ ] Read `last_4_digits` from the LLM CSV.
- [ ] Normalize `account_name` to remove trailing digits if present.
- [ ] Compute and include `account_key_v2` in enriched CSV for traceability; downstream will still recompute.
- [ ] Validate presence and format (4 digits).

Technical decisions:
- Make `last_4_digits` REQUIRED in the prompt to force extraction.
- Keep `account_name` WITHOUT last 4 for readability.

---

## Phase 3: Update Account Matching and Fingerprints

### 3.1 Modify `upsert_account`
File: `fin_cli/shared/models.py`

New logic (pseudocode):
```
def upsert_account(connection, *, name, institution, account_type, last_4_digits=None, auto_detected=True) -> int:
    """Insert a new account if needed and return its ID.

    Primary match on (institution, account_type, last_4_digits) when provided;
    fallback to exact name match for legacy rows.
    """
    if last_4_digits:
        row = connection.execute(
            "SELECT id FROM accounts WHERE institution=? AND account_type=? AND last_4_digits=?",
            (institution, account_type, last_4_digits),
        ).fetchone()
        if row:
            return int(row[0])

    row = connection.execute("SELECT id FROM accounts WHERE name=?", (name,)).fetchone()
    if row:
        return int(row[0])

    cursor = connection.execute(
        "INSERT INTO accounts (name, institution, account_type, last_4_digits, auto_detected) VALUES (?, ?, ?, ?, ?)",
        (name, institution, account_type, last_4_digits, auto_detected),
    )
    return int(cursor.lastrowid)
```

Changes:
- [ ] Add `last_4_digits` parameter and triple‑match query.
- [ ] Keep name fallback for backward compatibility.
- [ ] Insert should include `last_4_digits`.

### 3.2 Update callers
Files to update:
- [ ] `fin_cli/fin_enhance/pipeline.py`: pass `last_4_digits`; compute/use v2 key for cache.
- [ ] `fin_cli/fin_edit/main.py`: in preview and apply, resolve accounts using `(institution, account_type, last_4_digits)` when present.
- [ ] Any other direct callers.

### 3.3 Fingerprint strategy (breaking allowed)
File: `fin_cli/shared/models.py`

- [ ] Prefer recomputed `account_key_v2` for `compute_transaction_fingerprint` when available; keep `account_id` as a defensive fallback only.
- Rationale: With a dev DB reset, adopting v2 fingerprints now provides immediate DB‑independent dedupe.

---

## Phase 4: Dev Database Reset (simplified)

Given this is a dev database, we will reset instead of migrating data:
- [ ] Remove the SQLite file (default `~/.finagent/data.db`).
- [ ] Run any write‑capable CLI (e.g., `fin-edit ...`) to trigger the migration runner and recreate schema.
- [ ] Re‑import transactions using the updated extraction + postprocess + import pipeline.

---

## Phase 5: Update Tests

### 5.1 Update existing tests
- [ ] `tests/fin_edit/test_fin_edit.py` – account creation/preview flows.
- [ ] `tests/statement_processor/test_postprocess.py` – CSV validation and name normalization.
- [ ] Any tests that verify fingerprints.

### 5.2 Add new tests
- [ ] `upsert_account()` triple‑match by institution+account_type+last_4.
- [ ] Fallback to name matching.
- [ ] CSV parsing w/ required `last_4_digits`.
- [ ] v2 `account_key` recomputation and fingerprint stability across runs.

---

## Phase 6: Documentation

### 6.1 Update skill documentation
- [ ] `.claude/skills/statement-processor/SKILL.md` – add `last_4_digits`.
- [ ] `.claude/skills/statement-processor/reference/csv-format.md` – update schema.
- [ ] `.claude/skills/statement-processor/examples/` – include examples with last 4.

### 6.2 Update README/changelog
- [ ] Note breaking CSV change and v2 fingerprint behavior.
- [ ] Quickstart: how to reset dev DB and re‑import.

---

## Implementation Checklist

### Pre-work
- [x] Understand current fingerprint and matching logic
- [x] Identify pain points around name variations
- [ ] Back up DB if needed (optional for dev)

### Phase 1: Database
- [ ] Create and test SQL migration (`005_accounts_last4.sql`)
- [ ] Apply migration locally; verify schema and indexes

### Phase 2: Extraction
- [ ] Update extraction prompt
- [ ] Update importers
- [ ] Update postprocessing
- [ ] Test with a sample statement

### Phase 3: Matching & Fingerprints
- [ ] Update `upsert_account()`
- [ ] Update callers (pipeline, fin-edit import path)
- [ ] Prefer v2 key in fingerprints

### Phase 4: Dev DB Reset
- [ ] Remove `~/.finagent/data.db`
- [ ] Recreate schema via migration runner
- [ ] Re‑import with new pipeline

### Phase 5: Tests
- [ ] Update affected tests
- [ ] Add new test coverage
- [ ] All tests passing

### Phase 6: Documentation
- [ ] Update skill docs/examples
- [ ] Update README/changelog

### Post-implementation
- [ ] Import new statements; confirm no duplicate accounts
- [ ] Confirm dedupe across runs via stable fingerprints
- [ ] Verify analytics sanity checks

---

## Decisions

- Uniqueness: enforce `(institution, account_type, last_4_digits)` (partial unique index where last4 present).
- CSV account_key: keep emitting for traceability; downstream recomputes v2 and logs warnings if a supplied key mismatches.
- last_4_digits: required by prompt and validated in postprocess/importers (exactly 4 digits).

---

## Success Criteria

- ✅ No duplicate accounts with the same `(institution, account_type, last_4_digits)`.
- ✅ New imports do not create duplicate accounts.
- ✅ v2 fingerprints are stable across runs and DB resets.
- ✅ All tests passing; docs updated.

---

## Architecture Notes (v2 key & fingerprints)

- `account_key_v2 = sha256(lower(institution) | lower(account_type) | last_4_digits)`; excludes `name` to avoid formatting drift.
- `compute_transaction_fingerprint` prefers `account_key_v2`; `account_id` is a fallback only.
- Enriched CSV includes `account_key` for human/pipeline workflows; importers and pipelines recompute v2 and warn on mismatches.

