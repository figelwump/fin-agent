# plan_subscription_detect_filters_092925

## Phase 1 — Current State Analysis
- [x] Review `subscription_detect` heuristics for cadence, amount stability, and confidence scoring.
- [x] Inspect recurring candidate dataset to confirm available category and merchant metadata signals.
- [x] Document target false positives (parking meters, domain registrars) and the distinguishing attributes we can leverage.

## Phase 2 — Heuristic Refinements
- [x] Extend merchant summarisation to retain category, subcategory, and amount range details for each canonical merchant.
- [x] Apply filters for incidental categories (e.g., parking/tolls) and domain-registration style merchants using metadata-aware checks.
- [x] Adjust confidence scoring to include penalties for noisy patterns (irregular intervals, high amount variability) before thresholding.

## Phase 3 — Validation & Documentation
- [x] Add regression fixture covering parking and domain registration transactions and ensure they are excluded from the detected subscriptions.
- [x] Update existing analyzer tests to exercise the new fixture and validate legitimate subscriptions still surface.
- [x] Refresh README or CLI help if needed to explain new heuristics/filters for subscription detection.
- [x] Run analyzer smoke tests (`fin-analyze subscription-detect`) against sample DB and record outcomes in plan notes.

### Notes
- Capture decisions on threshold values (e.g., cadence bounds, confidence penalties) in this plan as work progresses so future agents understand rationale.
- Keep heuristics data-driven; prefer reusable metadata/category signals over hardcoded merchant names when possible.
- Current heuristics filter on occurrences ≥2, cadence 20-40 days, relative amount std ≤0.3, and estimate confidence from total occurrences + cadence proximity.
- Recurring candidate frames include category/subcategory columns plus raw JSON metadata; metadata often contains `merchant_pattern_*` keys and optional `merchant_metadata.platform` values (e.g., `NameCheap`).
- False positives observed: municipal parking (category `Transportation/Parking`, canonical contains `PARKING`, low spend, no metadata) and domain registrars (`merchant_metadata.platform` like `NameCheap`, cadence variance with short burst + long gaps). These signals drive the upcoming filters.
- Merchant summarisation now captures category/subcategory modes, min/max spend, and metadata platforms/services for filtering; recurring candidate loader normalises metadata JSON so analyzers can read `merchant_metadata` fields.
- New filters skip merchants in `Transportation/Parking` (and similar) or with `PARKING` in the canonical label ≤$20, plus merchants with metadata/labels signaling domain registration; confidence is penalised for variance and cadence jitter before comparing to thresholds.
- 2025-09-29: CLI smoke test `fin-analyze subscription-detect --db /tmp/test.db --period 3m` → 16 active subscriptions; Redwood City Parking and NameCheap no longer present in the table or new-merchant list.
