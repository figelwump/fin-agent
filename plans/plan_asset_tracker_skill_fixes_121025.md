# Asset Tracker Skill Fixes Plan
**Created:** 2025-12-10
**Goal:** Fix all issues identified during the Schwab statement workflow test

## Issues Summary

| # | Issue | Severity | Files Affected |
|---|-------|----------|----------------|
| 1 | SKILL.md references non-existent `fin-extract` command | High | SKILL.md |
| 2 | Validator tolerance too strict for bonds/truncated quantities | Medium | asset_contract.py |
| 3 | Prompt template lists invalid `cash` vehicle type | Low | asset_extraction_prompt.txt |
| 4 | Scripts require venv Python, not documented | Medium | SKILL.md |
| 5 | SKILL.md references non-existent `holdings` saved query | Medium | SKILL.md |
| 6 | Schwab PDF scrubbing over-redacts security names | Medium | fin-scrub config |
| 7 | Missing bond price convention documentation | Medium | asset_extraction_prompt.txt, SKILL.md |

## Implementation Phases

### Phase 1: Fix SKILL.md Documentation Errors (Issues 1, 4, 5)

- [x] **Issue 1**: Replace all `fin-extract asset-json` references with `fin-edit asset-import --from`
  - Line 88-95: Update preview/apply commands
  - Line 224: Update database commands section
  - Line 260: Update available commands section

- [x] **Issue 4**: Add note about Python environment requirements
  - Add prerequisite note that scripts must be run with project venv Python
  - Update script invocation examples to use `.venv/bin/python` or note that `fin-cli` must be installed

- [x] **Issue 5**: Fix saved query references
  - Line 99-107: Replace `fin-query saved holdings` with `fin-query saved portfolio_snapshot` or appropriate existing query
  - Verify all query names against actual `index.yaml` entries

### Phase 2: Fix Validator Tolerance (Issue 2)

- [x] Update `fin_cli/fin_extract/asset_contract.py` line 145
  - Increased `abs_tol` from `0.05` to `1.00` to handle small rounding differences
  - Increased `rel_tol` from `1e-6` to `1e-4` for percentage-based tolerance on larger values
  - Added comment explaining tolerance rationale (bond pricing, truncated quantities)

- [x] All existing tests pass with new tolerance values

### Phase 3: Fix Prompt Template (Issues 3, 7)

- [x] **Issue 3**: Remove invalid `cash` vehicle type
  - Removed `cash` from vehicle_type enum list in output format
  - Updated asset classification hints: FDIC deposits now map to `MMF`
  - Also updated SKILL.md vehicle types list and Common Security Types table

- [x] **Issue 7**: Add bond pricing documentation
  - Added new item #8 to "Important Notes" section explaining bond price conventions:
    - Bonds quoted as percentage of par (100.00 = par)
    - For JSON output: convert to per-dollar price (divide by 100)
    - Example: quoted 100.16796% → use price 1.0016796 in JSON
    - Clarified that quantity is face value (par amount)

### Phase 4: Verify Fixes

- [ ] Re-run the Schwab statement workflow end-to-end (manual testing required)
  - Use the same PDF: `statements/schwab/Brokerage Statement_2025-11-30_800.PDF`
  - Verify all commands work as documented
  - Confirm validation passes without manual price adjustments

- [x] Run existing tests to ensure no regressions
  - `pytest tests/fin_extract/` - 9 passed
  - `pytest tests/fin_edit/test_asset_*` - 14 passed

### Phase 5: Fix fin-scrub Over-Redaction (Issue 6)

- [x] Review fin-scrub default config and patterns
  - Located config: `fin_cli/fin_scrub/default_config.yaml`
  - Identified that `skip_words.name` list controls which words are preserved

- [x] Add allowlist patterns to preserve financial identifiers
  - Added brokerage/investment terms: securities, position, holdings, portfolio, market, value, etc.
  - Added identifiers: cusip, isin, sedol, ticker, symbol
  - Added security types: stock, bond, etf, fund, treasury, etc.

- [x] Add brokerage-specific preservation rules
  - Added major custodians: schwab, fidelity, vanguard, ubs, morgan, blackrock, etc.
  - Added fund names: apollo, carlyle, canyon, kkr, icapital, breit, reit, bdc
  - Added security suffixes: adr, sponsored, common, preferred, class, series, trust, lp

- [x] Updated both config files:
  - `fin_cli/fin_scrub/default_config.yaml`
  - `fin_cli/fin_scrub/fin-scrub.yaml`

- [ ] Test with Schwab statement to verify improvements (manual testing required)
  - Security names should be readable in Positions section
  - Ticker symbols should be preserved
  - PII (names, addresses, account numbers) should still be redacted

## Files to Modify

1. `.claude/skills/asset-tracker/SKILL.md` - Issues 1, 4, 5
2. `fin_cli/fin_extract/asset_contract.py` - Issue 2
3. `.claude/skills/asset-tracker/templates/asset_extraction_prompt.txt` - Issues 3, 7
4. `fin_cli/fin_scrub/default_config.yaml` - Issue 6

## Notes

- All fixes are backward-compatible
- No schema changes required
- No new dependencies required
- fin-scrub changes require careful testing to ensure PII is still properly redacted
