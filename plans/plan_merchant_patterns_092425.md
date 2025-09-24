# plan_merchant_patterns_092425

## Phase 1 – Discovery & Design
- [x] Inspect current merchant normalization heuristics (`merchant_pattern_key`) and rule usage to document failure modes (ticket numbers, phone numbers, aggregator partners).
- [x] Define desired schema for enriched merchant data: which fields belong on `merchant_patterns` vs `transactions` metadata, JSON structure, and backwards compatibility expectations.
- [x] Draft LLM output contract covering `pattern_key`, human-friendly display names, and optional enrichment (e.g., DoorDash restaurant).

## Phase 2 – Schema & Model Updates
- [x] Author migration adding `pattern_display` + `metadata` columns to `merchant_patterns` and `metadata` column to `transactions`; ensure indices/constraints remain valid.
- [x] Extend shared dataclasses (`Transaction`, `CategorizationOutcome`, etc.) and persistence helpers to accept/store metadata while preserving existing call sites.

## Phase 3 – LLM Contract & Utilities
- [x] Update `LLMResult`/`LLMSuggestion` parsing + serialization to honor the new contract, including prompt revisions that instruct the model to emit stable pattern keys, canonical merchant names, and enrichment metadata.
- [x] Enhance deterministic normalization helpers (e.g., `merchant_pattern_key`) to apply explicit stripping patterns (transaction IDs `"\b\d{10,16}\b"`, phone numbers `"\d{3}[-.]?\d{3}[-.]?\d{4}"`, dates `"\d{2}[-/]\d{2}"`, URLs `"\w+\.\w{2,4}"`, order prefixes `"^\w+\*\d+"`), then leverage LLM-provided hints when needed.

## Phase 4 – Pattern Learning & Persistence
- [x] Propagate LLM-derived display names/metadata through `HybridCategorizer` and `_record_merchant_pattern`, keeping the regex-normalized key as the stored lookup (`merchant_patterns.pattern`) so repeat transactions skip the LLM.
- [x] Persist merchant metadata onto transactions during import, and surface stored metadata when rules match existing patterns.

## Phase 5 – Verification & Documentation
- [x] Update/extend unit tests covering migrations, normalization edge cases (United tickets, DoorDash restaurants), and metadata persistence on transactions and rules reuse.
- [x] Refresh relevant docs or in-code comments to explain the new enrichment flow and how downstream analysis can consume metadata.

### Notes
- Tests updated across categorizer, CLI, importer, and shared models to validate normalization, caching behavior, and metadata persistence (35 passing). Inline comments document metadata propagation.
- Hybrid categorizer now batches by regex-normalized keys, injects display + metadata into outcomes, and records patterns with display/metadata; import pipeline writes metadata JSON to transactions.
- LLM payload now carries `pattern_key`, `pattern_display`, and `metadata`; caching serialization/deserialization upgraded accordingly.
- Regex cleanup enforced in `merchant_pattern_key` drops ticket IDs, phone numbers, dates, URLs, and order prefixes; fallback preserves a brand token if everything strips away.

- Migration 004 adds nullable `pattern_display` and JSON-checked `metadata` columns to `merchant_patterns` plus `transactions.metadata`; existing rows remain untouched.
- Shared models now serialize metadata via `_serialize_metadata`, extend `Transaction` + `CategorizationOutcome`, and update `record_merchant_pattern`/`insert_transaction` to accept display + metadata payloads.

- Deterministic cleanup: enforce regex-stripping for ticket IDs, phone numbers, dates, URLs, and order prefixes before handing merchants to the LLM.
- LLM duties: return canonical merchant names (e.g., "UNITED AIRLINES"), which we store in `pattern_display`/transaction metadata; `merchant_patterns.pattern` always keeps the deterministic regex-normalized key so lookups stay LLM-free after the first match.

- Schema: add `pattern_display`+`metadata` (TEXT JSON) to `merchant_patterns`; add `metadata` to `transactions` storing `{merchant_pattern_key, merchant_pattern_display, merchant_metadata}`.
- LLM contract: per-merchant object includes `pattern_key` (stable uppercase brand), `pattern_display` (human label), optional `metadata` dict (e.g., `{"platform": "DoorDash", "restaurant_name": "Dosa Point"}`), alongside existing `suggestions`.
- Normalization gap: current `merchant_pattern_key` leaves ticket/phone numbers; Phase 3 will enhance regex heuristics, but rule lookup continues to use deterministic keys.
- Touch points: `fin_cli/fin_enhance/categorizer/{llm_client,hybrid,rules}.py`, `fin_cli/shared/models.py`, migrations, importer/pipeline tests.
- Ensure JSON metadata remains compact (no large blobs) and guard against `None` vs `{}` so we avoid noisy DB diffs.
- Consider backward compatibility: existing `merchant_patterns.pattern` remains the lookup key; new display field is additive.
