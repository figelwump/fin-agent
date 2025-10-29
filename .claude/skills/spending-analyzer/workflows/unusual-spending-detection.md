# Unusual Spending Detection (Hybrid Workflow)

## Purpose
Surface potential anomalies by combining the heuristic `unusual-spending` analyzer with targeted queries and LLM reasoning, especially when baseline windows are sparse or auto-extended.

## Data Collection
1. `source .venv/bin/activate`
2. Run the analyzer with comparison enabled (use latest month or quarter):
   ```bash
   fin-analyze unusual-spending --month 2025-09 --compare --sensitivity 3 --format json > /tmp/unusual_spending.json
   ```
3. Inspect baseline diagnostics inside the JSON (`baseline.source`, `fallback_recommended`).
4. Pull top merchants and category totals for context:
   ```bash
   fin-analyze merchant-frequency --month 2025-09 --min-visits 1 --format json > /tmp/merchant_frequency.json
   fin-analyze category-breakdown --month 2025-09 --format json > /tmp/category_breakdown.json
   ```
5. Capture raw transactions for the analysis window:
   ```bash
   fin-query saved transactions_range --param start_date=2025-09-01 --param end_date=2025-10-01 --param limit=0 --format json > /tmp/transactions_range.json
   ```

## Analysis Steps
1. Read `/tmp/unusual_spending.json`. Separate `anomalies` (spend deltas) from `new_merchants`.
2. If `baseline.source` is `"missing"` or `fallback_recommended` is true, note that heuristics relied on limited history.
3. For each flagged merchant, use `/tmp/transactions_range.json` to quote recent transactions and confirm the amount change.
4. Use merchant/categorical context to spot additional spikes the heuristics missed (e.g., high spend categories with no anomaly entry).
5. Prompt the LLM with:
   - The heuristic anomalies and diagnostics.
   - Merchant-frequency and category-breakdown summaries.
   - Relevant raw transactions.
   Ask it to validate each anomaly, explain drivers (one-offs vs recurring), and highlight any additional suspicious merchants or categories.
6. Produce a consolidated anomaly report with severity, spend change, visit change, and recommended follow-ups.

## Output Format
- Ranked list of anomalies with spend delta %, dollar change, visit change, and narrative explanation.
- Separate section for “new merchants” when baselines are missing (flag for manual review).
- Baseline commentary (e.g., “Baseline extended automatically to 2024-09-01–2025-09-01; sparse data may hide earlier activity.”).
- Action items (verify charges, dispute, budget adjustments).

## Example
```
Heuristic anomalies confirmed:
- BB Tuition Management — $63,581 (new merchant). No prior baseline; legitimate annual tuition payment.
- Altum PR — $12,631 (+100%). Appears to be a new vendor; confirm contract.
- PG&E — $231 (+45%). Seasonal usage spike; expected given July heat wave.

Additional spikes flagged by LLM:
- Costco — $751 this month vs $420 avg prior months (based on transactions_range).

Baseline notes: Analyzer auto-extended baseline window but still found no prior data (baseline.source=missing). Manual review recommended for all “new merchant” items.
```
