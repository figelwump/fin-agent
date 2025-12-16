# Asset Tracking Plan
**Created:** 2025-12-10
**Updated:** 2025-12-16 (phase 5 complete: analysis workflows, preferences module, skill docs)
**Goal:** Add first-class asset tracking (schema, import, analysis) so users can ingest statements/screenshots, maintain asset history, view allocations/trends, and reuse spending knowledge across skills.

## Architecture & Data Model

### Key Design Decision: Instrument vs Holding Split
Per Oracle review, split securities from positions to avoid duplication and simplify cross-account consolidation:
- **Instruments** (security master): global securities with identifiers
- **Holdings** (per-account positions): account-scoped positions referencing instruments
- **Prices**: instrument-level price history (separate from holding values)

### Schema (finalized)

Extend SQLite schema via new migrations (`fin_cli/shared/migrations/006+`). Keep JSON metadata columns for broker-specific payloads.

#### Core Tables

**`asset_classes`** (formerly `asset_types`)
- id, main_class (equities/bonds/alternatives/cash/other), sub_class, vehicle_type_default NULL, metadata
- UNIQUE(main_class, sub_class)
- Note: ETFs are vehicles, not classes; use sub_class like "US equity", "intl equity", "treasury", etc.

**`instruments`** (security master - NEW)
- id, name, symbol, exchange, currency, vehicle_type (stock/ETF/mutual_fund/bond/MMF/fund_LP/note/option/crypto)
- identifiers JSON (cusip, isin, sedol, figi, fund_id)
- metadata
- UNIQUE(symbol, exchange) nullable-safe; also unique per identifier when present

**`holdings`** (per-account positions - replaces `assets`)
- id, account_id (FK->accounts), instrument_id (FK->instruments)
- status (active/closed), opened_at, closed_at
- cost_basis_total, cost_basis_per_unit, cost_basis_method (FIFO/LIFO/Specific/Avg)
- position_side (long/short), metadata
- UNIQUE(account_id, instrument_id, status='active')
- Note: removed `institution` (redundant with accounts.institution)

**`holding_values`** (formerly `asset_values`)
- id, holding_id (FK->holdings), as_of_date (DATE), as_of_datetime (TEXT ISO-8601, optional)
- quantity, price, market_value, accrued_interest, fees
- source_id (FK->asset_sources), document_id (FK->documents)
- valuation_currency (default 'USD'), fx_rate_used (default 1.0)
- ingested_at, metadata
- UNIQUE(holding_id, as_of_date, source_id)
- INDEX(holding_id, as_of_date DESC)

**`asset_prices`** (instrument price history - NEW)
- id, instrument_id (FK->instruments), as_of_date, as_of_datetime
- price, currency, source_id (FK->asset_sources), metadata
- UNIQUE(instrument_id, as_of_date, source_id)
- INDEX(instrument_id, as_of_date DESC)

**`asset_sources`** (enhanced)
- id, name (broker/app), source_type (statement/upload/api/manual)
- priority INTEGER (lower = higher: statement=1, manual=2, api=3)
- contact_url, metadata

**`documents`** (NEW - for idempotent re-imports)
- id, document_hash (SHA256), source_id (FK->asset_sources)
- period_end_date, broker, file_path, metadata
- UNIQUE(document_hash)

**`instrument_classifications`** (NEW - mapping instruments to classes)
- id, instrument_id (FK->instruments), asset_class_id (FK->asset_classes)
- UNIQUE(instrument_id, asset_class_id)

**`portfolio_targets`** (NEW - for rebalance suggestions)
- id, scope (account/portfolio), scope_id, asset_class_id (FK->asset_classes)
- target_weight, as_of_date, metadata

#### Constraints & Checks
- NOT NULL: all foreign keys, as_of_date on values/prices
- CHECK: currency = UPPER(3 chars); quantity >= 0 (unless position_side='short'); price >= 0; market_value >= 0
- json_valid(metadata) on all JSON columns
- PRAGMA foreign_keys=ON in CLI sessions

#### Views/Saved Queries (Phase 1)
- `holding_latest_values`: one row per holding using source priority then recency
- `portfolio_snapshot`: join accounts, holdings, latest values, classifications for allocation
- `allocation_by_main_sub`: allocation breakdown by main/sub class
- `allocation_by_account`: allocation breakdown by account
- `concentration_top_n`: top N holdings by weight (parameterized)
- `stale_holdings`: holdings without updates in N days
- `holdings_missing_classification`: instruments without asset_class mapping

### Source Precedence Rule
Select latest value using: `(source.priority ASC, as_of_datetime DESC, ingested_at DESC)`
- Statement (priority 1) > Manual (2) > API (3)

### Existing Tables (reuse)
- `accounts`: reuse for account_id FK
- `categories`: no changes needed
- `transactions`: do not overload

### Ingestion JSON Contract (Phase 3 -> Phase 2)
```json
{
  "document": {"document_hash": "sha256...", "broker": "UBS", "as_of_date": "2025-12-31"},
  "instruments": [{"name": "Apple Inc", "symbol": "AAPL", "identifiers": {"cusip": "..."}, "currency": "USD"}],
  "holdings": [{"account_key": "UBS-123", "symbol": "AAPL", "status": "active"}],
  "holding_values": [{"account_key": "UBS-123", "symbol": "AAPL", "as_of_date": "2025-12-31", "quantity": 100, "price": 150.00, "market_value": 15000.00, "source": "statement", "document_hash": "sha256..."}]
}
```
Importer resolves account_key -> account_id and symbol/cusip -> instrument_id, creating as needed with dry-run preview.

## Implementation Phases

### Phase 0: Discovery & Scope Lock
- [x] Review current skills + analyzers to reuse patterns (`.claude/skills/*`, `fin_analyze`).
- [x] Confirm statement inputs & brokers: prioritize PDFs (scrub with fin-scrub) for UBS, Schwab, Mercury (cash + investments), AngelList, private real-estate/VC fund PDFs (often unstructured). CSV/screenshots optional later.
- [x] Decide initial scope: focus on balances/allocations (fees/cost-basis/performance/tax = v2).
- [x] Currency scope: USD-only for v1 (but schema includes valuation_currency + fx_rate_used for v2).
- [x] Surface: CLI + skills first; UI optional later.
- [x] Decide minimal taxonomy: main = equities, bonds, alternatives, cash, other; subs = US equity, intl equity, treasury, muni, corp IG/HY, private equity, VC/Angel, real estate fund, cash sweep, money market, other. Note: ETFs are vehicles, not classes.
- [x] **Data model decision locked**: instrument/holding split per Oracle review.
- [x] Choose migration version numbers (006+) and backward-compat strategy (idempotent, safe reruns).
- [x] Update `.gitignore` to exclude `~/.finagent/` directory (preferences.json, any local state).

### Phase 0.5: Fixtures & Golden Tests (NEW)
- [x] Create fixture JSON files matching ingestion contract for test brokers (UBS, Schwab, Mercury).
- [x] Write golden tests validating ingestion JSON structure before wiring parsers.
- [x] Test migration idempotence (run twice, no errors).

Notes:
- Fixtures live under `tests/fixtures/asset_tracking/` as `{ubs,schwab,mercury}_statement.json` using the normalized ingestion contract (document + instruments + holdings + holding_values).
- Golden contract tests in `tests/fin_edit/test_asset_ingestion_contract.py` enforce schema shape, referential integrity, ISO dates, and valuation arithmetic for the fixtures.
- Added idempotence regression in `tests/shared/test_database.py` to ensure rerunning migrations (incl. seeded asset_sources) is safe.

### Phase 1: Schema & Saved Queries
- [x] Add migrations for: `asset_classes`, `instruments`, `holdings`, `holding_values`, `asset_prices`, `asset_sources`, `documents`, `instrument_classifications`, `portfolio_targets`.
  - Created: `006_asset_tracking.sql` (schema), `007_asset_classes_seed.sql` (seed data)
- [x] Include indexes: (holding_id, as_of_date DESC), (instrument_id, as_of_date DESC), (account_id), unique constraints.
- [x] Add CHECK constraints and json_valid() checks.
- [x] Seed initial `asset_classes` rows via migration or fixture script (include "other/unknown" to avoid import failures).
- [x] Create saved queries/views: `holding_latest_values`, `portfolio_snapshot`, `allocation_by_class`, `allocation_by_account`, `stale_holdings`, `holdings_missing_classification`, `asset_classes`, `instruments`, `holding_history`.
- [x] Update `fin-query` CLI to expose new saved queries (added to `index.yaml`).
- [x] Add tests for each saved query with fixture data.
- [x] Add index.yaml entries so skills can discover new queries.

Notes:
- Asset query regression tests live in `tests/fin_query/test_asset_queries.py` with an inline seeding helper to exercise source precedence, allocations, staleness detection, and history/doc provenance.

### Phase 2: Import & Edit CLI
- [x] Add `fin-edit` commands:
  - `fin-edit instruments-upsert --from parsed.json`
  - `fin-edit holdings-add|holdings-deactivate|holdings-move --account "<acct>" --instrument "<symbol>"`
  - `fin-edit holding-values-upsert --from values.json`
  - `fin-edit documents-register --hash <sha256>` and `documents-delete`
- [x] Implement validation: required fields, UNIQUE(holding_id, as_of_date, source_id), currency handling. (Normalized currency, source mapping, derived price/market_value; rejects missing requireds.)
- [x] Implement source precedence for latest-value resolution. (Uses seeded asset_sources priorities + query ordering; upsert maps logical sources to ids.)
- [x] Provide helper to map broker metadata -> canonical columns (ticker, quantity, price, fees, cost basis). (Normalization derives price/market_value and validates FX/currency; broker metadata mapping hooks in CLI helpers.)
- [x] Add dry-run preview mode (consistent with existing fin-edit patterns).
- [x] Add deletion/rollback: `fin-edit documents delete --hash <sha256>` with cascade to holding_values.
- [x] Add regression tests covering upsert, dedupe, and latest-value resolution.

Notes:
- CLI surface lives in `fin_cli/fin_edit/main.py`; asset helpers in `fin_cli/shared/models.py`.
- Validation: currency/vehicle enums enforced, required fields checked, price/market_value derived when one is missing, fx_rate > 0, ISO date parsing, source strings mapped to seeded priorities.
- Regression tests in `tests/fin_edit/test_asset_cli_commands.py` cover instrument/holding/holding_value/document flows using the UBS fixture; reruns assert idempotence; extra test covers validation + derived price.
- Added convenience `asset-import` command (one-shot ingest of document+instruments+holdings+values) tested with Schwab fixture.

### Phase 3: Extraction Pipeline for Asset Statements
- [x] Extend statement processor (or new `asset-import` helper) to parse PDFs/CSVs/screenshots: scrub PII via `fin-scrub`, extract holdings/valuations, emit normalized JSON matching Phase 2 contract. (Added `fin-extract asset-json` CLI for validated JSON ingest; PDF parsing still TODO.)
- [x] Compute document_hash (SHA256) for each statement; store in documents table for idempotent re-imports. (`fin-extract asset-json --document-path` derives hashes and propagates to values.)
- [x] Add CSV ingest path for holdings (`fin-extract asset-csv`) as the first broker-neutral template; PDF templates/LLM fallback still pending.
- [x] Include categorization step that maps holdings -> `asset_classes` (rule-based on ticker/description + LLM backstop). (Heuristics infer cash sweeps, bonds, crypto, equity flavors; idempotent classifications on import.)
- [ ] Handle edge cases:
  - Security aliases (same security, different names across brokers)
  - Fractional shares (6-8 decimal precision)
  - Private funds with quarterly-lag NAV (capture in metadata, surface staleness)
  - CUSIP/symbol changes, corporate actions (log in metadata)
- [x] Write tests/fixtures under `tests/` for parsers with golden outputs. (Validator + asset-json CLI tests on broker fixtures.)

### Phase 4: Analysis & Reporting
- [x] Add `fin-analyze` analyzers:
  - `allocation_snapshot`: current allocation by class/account
  - `trend` (alias `portfolio-trend`): time-series of market_value
  - `concentration_risk`: top-N holdings by weight + optional fee flags
  - `cash_mix`: cash vs non-cash breakdown
  - `rebalance_suggestions`: compare to portfolio_targets
- [x] Incorporate spending knowledge where relevant (cash runway uses trailing spend for context).
- [x] Add CLI flags for date windows, target mix, and fee highlighting; ensure CSV output for skills.
- [x] Tests for analyzers using fixture data.

Notes:
- New analyzers live under `fin_cli/fin_analyze/analyzers/` with shared asset loaders in `fin_cli/fin_analyze/assets.py`.
- Saved query `portfolio_snapshot` now returns accrued_interest/fees to support fee highlighting.
- Asset test fixture `tests/fixtures/analyze/assets_portfolio.json` seeds holdings + targets; loader in `tests/fin_analyze/conftest.py` now supports asset tables.
- Regression coverage added in `tests/fin_analyze/test_asset_analyzers.py` (allocation, trend, concentration, cash runway, rebalance deltas).

### Phase 5: Skills Integration
- [x] Create new skill `asset-tracker` with workflows: ingest statements -> import -> analyze; reuse spending-analyzer patterns for narrative assembly.
  - Created `.claude/skills/asset-tracker/` with SKILL.md, templates, and scripts
  - `preprocess.py`: Builds LLM prompts with asset class taxonomy and existing instruments
  - `postprocess.py`: Validates JSON, auto-classifies instruments by name/vehicle_type, computes document_hash
  - Tested end-to-end with scrubbed UBS November 2025 statement (13 holdings, $6M portfolio)
- [x] Add workflows for "view allocation", "trend/history", "rebalance suggestions", "over/under cash vs spend rate".
  - Created `workflows/allocation-analysis.md`, `portfolio-trend.md`, `rebalance-analysis.md`, `cash-runway.md`
  - Created `reference/all-analyzers.md` documenting all asset analyzers and saved queries
- [x] Add preference capture: quiz user for target allocations/risk/liquidity/geo preferences; persist in DB (`portfolio_targets` table) AND JSON file under `~/.finagent/preferences.json` (gitignored).
  - Created `workflows/preference-capture.md` with step-by-step quiz workflow
  - Defines JSON schema for preferences including profile, targets, and settings
- [x] Implement safe preferences file handling:
  - Created `fin_cli/shared/preferences.py` with atomic writes (temp file + rename)
  - Creates `~/.finagent/` directory with mode 0o700 if missing
  - Logs warning if preferences file missing; returns sensible defaults
  - Full test coverage in `tests/shared/test_preferences.py` (13 tests passing)
- [x] Update skill READMEs and prompts to document new commands/flags and safety (scrub before send).
  - Updated `SKILL.md` description to include analysis capabilities
  - Added "Analysis Workflows" section with quick commands and workflow references
  - Added "Reference" section pointing to all-analyzers.md

### Phase 6: Web/UI Touchpoints (optional but recommended)
- [ ] Add API endpoints + minimal UI panels (web_client) for asset list, latest values, allocation chart, history sparkline.
- [ ] Wire endpoints to new queries/analyzers; ensure authentication/paths align with existing agent UI.

### Phase 7: QA, Backfill, and Docs
- [ ] Run `pytest` for new/affected modules; add coverage for migrations and saved queries.
- [ ] Provide backfill script (optional) to load historical statements for initial dataset; document rollback/recovery.
- [ ] Update top-level docs (`README.md`, skill docs) with setup steps, schema reference, and examples.
- [ ] Add schema diagram snippet and migration numbers.

## Risk Areas & Mitigations

| Risk | Mitigation |
|------|------------|
| **Identity/Dedupe**: same security across brokers, symbol changes, CUSIP rollover | Use `instruments` table with robust identifiers + aliases in metadata; prefer CUSIP/ISIN when available |
| **Duplicate values**: same date from statement vs API | Use `source_id` + source priority for deterministic latest selection |
| **Re-import same statement** | Require `document_hash` and UNIQUE constraint; store in `documents` table |
| **Private funds**: quarterly-lag NAV, capital calls | Capture in `metadata`; surface staleness in `stale_holdings` view |
| **Position mechanics**: fractional shares, shorts, accrued interest | Ensure numeric precision (Decimal in Python); allow negative quantities where appropriate |
| **Corporate actions**: splits, spinoffs, ACAT transfers | Add audit trail; use `instrument_aliases` in metadata |
| **Privacy**: raw PII in statements | Always go through `fin-scrub` per CLAUDE.md; never read raw PDFs directly |
| **SQLite precision**: float drift | Use `Decimal` in Python; store scaled integers where feasible (cents, micro-shares) |

## Open Questions / Decisions Needed
- [x] Data model: instrument/holding split - **DECIDED** per Oracle review
- [x] Preference persistence: JSON file under `~/.finagent/preferences.json` + DB table `portfolio_targets`
- [x] Source precedence: statement > manual > api (priority 1 > 2 > 3)
- [ ] Migration version numbers: 006+ (to be finalized in Phase 0)

## Notes from Oracle Review (2025-12-10)
- Split `assets` into `instruments` (security master) + `holdings` (per-account positions)
- Add separate `asset_prices` table for instrument-level price history
- ETFs are vehicles, not asset classes
- Add `documents` table for idempotent re-imports via document_hash
- Add provenance fields: `ingested_at`, `source_id`, `document_id` on all value rows
- Define CLI contracts before building extractors
- Use source priority for deterministic latest-value selection
