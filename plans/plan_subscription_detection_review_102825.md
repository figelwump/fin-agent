# plan_subscription_detection_review_102825

## Phase 1 — Reproduce & Observe
- [x] Activate repo virtualenv and rerun `fin-analyze subscription-detect` against the user's dataset to confirm the empty result. *(2025-10-28: `fin-analyze subscription-detect --period all --format json` → `Error: No subscriptions matched the configured filters.`)*
- [x] Capture CLI flags/config in use (e.g., period, thresholds, filters) and note CLI/stdout diagnostics for reference. *(Using default config + `--period all`; CLI exits 1 with the above message, no additional hints.)*
- [x] Inspect current recurring transaction candidates (e.g., via `fin-analyze merchant-frequency` or saved queries) to verify subscriptions should exist. *(2025-10-28: `fin-analyze merchant-frequency --period all --min-visits 3 --format json` surfaced Costco, Norton, PG&E, AT&T, Netflix, etc. with ≥3 visits, confirming repeated merchants exist.)*

## Phase 2 — Heuristic Diagnosis
- [x] Review `fin_analyze.subscription_detect` implementation for recent filters/thresholds that could zero out matches on this dataset. *(Confirmed the analyzer enforces cadence window 20–40 days, rel. std. dev ≤0.3, excludes incidental categories/domains, and applies confidence penalties for cadence jitter.)*
- [x] Instrument or run with debug logging to trace candidate filtering stages and identify the drop-off point. *(Built ad-hoc inspection script: majority of merchants fail `cadence outside 20-40` because median gaps ≈289 days owing to 2025 entries resuming after 2023/early-2024 stops; others fail `rel_std > 0.3` from wide spend swings like Costco, BB Tuition Management.)*
- [x] Cross-check DB signals (categories, metadata, cadence) for the affected merchants to see which heuristics misclassify them. *(Spot checks: `Netflix` charges on 2023-12-24, 2024-01-25, 2025-07-25 ⇒ cadence diffs [32, 547]; `Backblaze`/`Disney Plus`/`Spotify` show similar 2023-2025 gaps; PG&E fails on rel_std 0.45 due to $17–64 oscillation even though cadence 24.5 days passes.)*

## Phase 3 — Recommendation & Next Steps
- [x] Summarize root cause(s) of the empty result and outline potential fixes or configuration knobs. *(Cadence filter (20–40 days) plus relative spend variance ≤0.3 eliminate essentially all candidates due to a multi-month transaction gap and volatile utility/retailer spend; confidence penalties keep remaining near zero.)*
- [x] Evaluate whether the LLM-only approach covers gaps or introduces risks, and document trade-offs versus heuristic detection. *(LLM easily surfaced subscriptions even with sparse cadence, but depends on prompt quality + cost; heuristics provide deterministic guardrails yet brittle when history is incomplete or amounts fluctuate.)*
- [x] Recommend a path forward (e.g., tweak heuristics, add fallback to LLM, retire code) with impact assessment and follow-up tasks. *(Propose: relax cadence window (e.g., allow 20–365 days with stronger recency weighting), tolerate higher std dev for utilities, and add optional LLM fallback when heuristics yield empty set; alternatively flag data gaps to user instead of hard failure.)*

## Phase 4 — fin-analyze Scope Review
- [x] Inventory current `fin-analyze` commands, their data dependencies, and overlap with LLM capabilities. *(Catalogued nine analyzers: trends, category breakdown/evolution/timeline, spending patterns, merchant frequency, unusual spending, subscription detect, category suggestions; most rely on aggregated pandas data over `/Users/vishal/.finagent/data.db`.)*
- [x] Assess real-world utility and maintenance cost for each analyzer relative to LLM-driven workflows. *(Trend/time-series analyzers deliver deterministic charts/numbers valuable for dashboards; category suggestions rarely trigger and are high-maintenance; subscription detection brittle; unusual spending useful but needs better baselines; others overlap with LLM summaries.)*
- [x] Propose keep/retire/delegate-to-LLM recommendations and capture any migration tasks or guardrails needed. *(Suggested: keep trends/category timeline/breakdown for structured reporting; modernise unusual-spending; rework subscription-detect w/ heuristics+LLM fallback; merchant-frequency can be LLM-derived or saved query; retire category-suggestions unless automated pattern mining is prioritized; document that LLM should cite underlying queries.)*

## Phase 5 — Implementation Follow-ups
- [x] Relax subscription cadence/variance heuristics, add diagnostic fields (drop reasons, baseline gaps), and surface optional LLM fallback triggers. *(Cadence now accepts 20–365 day medians, variance thresholds loosen for utilities/small-dollar charges, diagnostics expose skipped reasons + `fallback_recommended`, and the analyzer no longer hard-fails when no matches are found.)*
- [x] Enhance unusual-spending to require/auto-extend comparison windows, annotate baseline coverage, and guard against empty “new merchant” floods. *(Fallback baseline window loads automatically, baseline metadata is emitted in the payload, and new-merchant floods no longer populate anomalies when history is missing.)*
- [x] Deprecate `category-suggestions`, migrate its documentation references, and consolidate its guidance into category workflows. Retired `category-evolution` as a standalone analyzer by folding its new/dormant/significant-change metrics into `category-timeline` (payload now always includes an `evolution` block, and summary copy reflects the merged insights).
- [x] Introduce a new saved query (`transactions_range`) for flexible date windows rather than mutating `recent_transactions`; docs reference the new query for LLM workflows.
- [x] Update spending analyzer skill prompts and reference docs to follow the hybrid flow: run heuristics first, capture their JSON outputs, gather supporting `fin-query` slices (`transactions_range`, `merchant_frequency`, etc.), and feed the bundle into the LLM.
- [x] Add spending-analyzer workflow docs (`workflows/subscription-detection.md`, `workflows/unusual-spending-detection.md`) and refresh examples (`custom-reports.md`, `common-queries.md`) to point at the hybrid process; removed obsolete `category-suggestions` references and deleted the outdated insights example.
- [x] Add logging/telemetry so we can track when the LLM overrides heuristics and feed that back into future tuning. *(Both analyzers emit info-level notices when heuristics fall back to LLM review.)*

### Notes
- Record any environment quirks (e.g., missing `.claude/skills/spending-analyzer/.venv`) and dataset characteristics that impact reproducibility.
- 2025-10-28: CLI only supports `--format text|json`; prior attempt with `--format table` returns Click usage error.
- Dataset window resolved to `period_all_2023_12_22_to_2025_09_30`; many merchants show long gaps (2024-02 through 2025-06 missing), forcing median cadence ≈289 days despite appearing to be monthly subscriptions.
- Highlight affected modules/files (likely `fin_analyze/subscription_detect.py` and related analyzers) as findings emerge.
- Update checkbox status and add findings under each phase before requesting the user to review subsequent phases.
