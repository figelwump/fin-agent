# Asset Transfer Support

**Created:** 2025-12-10
**Status:** Complete

## Overview

Add support for detecting and handling asset transfers between institutions. Uses a hybrid approach:
1. Core transfer logic in `fin-edit holdings transfer` command
2. Detection/suggestion during asset-tracker imports

## Phase 1: Transfer Command (`fin-edit holdings transfer`)

### 1.1 Add CLI command
- [x] Add `transfer` subcommand to `fin_cli/fin_edit/main.py`
- [x] Parameters:
  - `--symbol` (required): Instrument symbol to transfer
  - `--from` (required): Source account name/ID
  - `--to` (required): Destination account name/ID
  - `--transfer-date` (optional): Date of transfer, defaults to today
  - `--carry-cost-basis` (flag): Copy cost basis to new holding
  - `--quantity` (optional): Partial transfer support (future)
  - `--apply` (flag): Actually execute, otherwise preview

### 1.2 Transfer logic
- [x] Validate source holding exists and is active
- [x] Validate destination account exists
- [x] Validate instrument exists
- [x] Check if destination holding already exists (update vs create)
- [x] Execute transfer:
  1. Close source holding (`status='closed'`, `closed_at=transfer_date`)
  2. Create/update destination holding (`status='active'`, `opened_at=transfer_date`)
  3. If `--carry-cost-basis`: copy `cost_basis_total` and `cost_basis_method`
- [x] Preview mode shows what would happen without committing

### 1.3 Output
```
Transfer Preview:
  Symbol: CRM (Salesforce, Inc.)
  From: UBS-Y7-01487-28 (holding #3)
    → Set status='closed', closed_at=2025-12-10
  To: Schwab-1234 (new holding)
    → Set status='active', opened_at=2025-12-10
    → Cost basis: $61,195.77 (carried from source)

Use --apply to execute.
```

## Phase 2: Detection in Asset-Tracker

### 2.1 Add detection helper
- [x] Created `detect_potential_transfers()` and `print_transfer_warnings()` in `.claude/skills/asset-tracker/scripts/postprocess.py`
- [x] Input: enriched JSON payload + current database state
- [x] Logic:
  - For each holding in payload, check if instrument has active holding at *different* account
  - Return list of potential transfers with details

### 2.2 Integrate into postprocess.py
- [x] After validation, run transfer detection
- [x] If potential transfers found, emit warnings with suggested commands
- [x] Added `--detect-transfers/--no-detect-transfers` CLI flag (default: enabled)
- [x] Example output:
  ```
  ⚠️  Potential transfer detected:
      CRM (Salesforce, Inc.) - active at UBS-Y7-01487-28, now appearing at Schwab-1234
      Suggested: fin-edit holdings transfer --symbol CRM --from UBS-Y7-01487-28 --to Schwab-1234 --carry-cost-basis
  ```

### 2.3 Update SKILL.md
- [x] Add "Handling Transfers" section
- [x] Document the detection behavior
- [x] Document manual transfer command usage
- [x] Document viewing closed holdings

## Phase 3: Tests

- [x] Unit tests for transfer command (preview and apply modes)
- [ ] Test partial transfer (future: quantity-based) - deferred
- [x] Test cost basis carry-over
- [ ] Test detection logic with mock database state - deferred
- [ ] Integration test: import statement with transfer scenario - deferred

## Schema Notes

No schema changes required. Uses existing fields:
- `holdings.status`: 'active' → 'closed'
- `holdings.opened_at`, `holdings.closed_at`: Track transfer dates
- `holdings.cost_basis_total`: Carried to new holding

## Edge Cases

1. **Same instrument, multiple accounts (intentional)**: User may hold CRM at both UBS and Schwab legitimately. Detection should warn but not auto-close.
2. **Partial transfers**: Future enhancement - transfer portion of shares.
3. **Transfer to new account**: Destination account may not exist yet - prompt to create or fail gracefully.
4. **Cost basis complications**: Some transfers have wash sale implications - out of scope, just carry the number.

## Files to Modify

- `fin_cli/fin_edit/main.py` - Add transfer command
- `.claude/skills/asset-tracker/scripts/detect_transfers.py` - New file
- `.claude/skills/asset-tracker/scripts/postprocess.py` - Add detection call
- `.claude/skills/asset-tracker/SKILL.md` - Documentation
- `tests/fin_edit/test_holdings_transfer.py` - New test file

## Decisions

1. **Detection scope**: Only in skill's postprocess step, NOT during `fin-extract asset-json --apply`
2. **Batch transfers**: Not yet - single symbol at a time for now
3. **Query defaults**: Hide closed holdings by default (queries already had `status` parameter defaulting to `active`)

## Implementation Notes

**Files modified:**
- `fin_cli/fin_edit/main.py` - Added `holdings-transfer` command (~150 lines)
- `.claude/skills/asset-tracker/scripts/postprocess.py` - Added detection functions (~80 lines)
- `.claude/skills/asset-tracker/SKILL.md` - Added "Handling Transfers" section
- `tests/fin_edit/test_asset_cli_commands.py` - Added 4 test functions

**Key implementation details:**
- Transfer command resolves accounts by name or ID
- Source holding is closed (not deleted) to preserve history
- Cost basis can optionally be carried to destination
- Detection runs by default during postprocess, can be disabled with `--no-detect-transfers`
- Queries already filter to active holdings by default via `status=active` parameter
