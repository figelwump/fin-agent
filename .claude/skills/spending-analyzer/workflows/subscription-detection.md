# Subscription Detection (Hybrid Workflow)

## Purpose
Identify recurring subscriptions by running the heuristic analyzer first, then asking the LLM to validate, explain, and extend the findings with supporting transaction slices.

## Data Collection
1. `source .venv/bin/activate`
2. Run the heuristic analyzer (captures diagnostics + fallback flag):
   ```bash
   fin-analyze subscription-detect --period 12m --format json > /tmp/subscriptions.json
   ```
3. Pull recurring merchant context for the same window:
   ```bash
   fin-analyze merchant-frequency --period 12m --min-visits 3 --format json > /tmp/merchant_frequency.json
   ```
4. Fetch detailed transactions for the latest quarter (adjust dates as needed):
   ```bash
   fin-query saved transactions_range --param start_date=2025-07-01 --param end_date=2025-10-01 --param limit=0 --format json > /tmp/transactions_range.json
   ```

## Analysis Steps
1. Parse `/tmp/subscriptions.json`. Note `subscriptions`, `new_merchants`, `cancelled`, and `diagnostics.fallback_recommended`.
2. If `fallback_recommended` is true or the list is sparse, flag for deeper review.
3. Cross-reference merchants with `/tmp/merchant_frequency.json` to confirm cadence/visit counts.
4. Use `/tmp/transactions_range.json` to pull exemplar transactions (amount, dates) for each candidate merchant.
5. Prompt the LLM with:
   - Heuristic output (including `diagnostics.skipped_summary` for reasoning gaps).
   - Merchant frequency snapshot.
   - Relevant slices from `transactions_range`.
   Ask it to confirm true subscriptions, add any missing recurring charges it infers, and provide rationale (cadence, amounts, latest date, cancellation opportunities).
6. Merge heuristic + LLM findings, deduplicate by canonical merchant, and present a final structured list.

## Output Format
- Table or bullet list grouped by category (e.g., Entertainment, Utilities, Services).
- For each subscription: merchant name, cadence estimate, average amount, latest charge date, confidence/comments, cancellation watch items.
- Summary totals (monthly and annualised).
- Note whether heuristics were sufficient or if the LLM filled gaps due to data sparsity.

## Example
```
Subscriptions detected (heuristic + LLM confirmation):
- Netflix — ~$33.98/mo (last charge 2025-07-25). Heuristic skipped due to cadence gap; LLM confirmed via 2025-07 charge + earlier pattern.
- AT&T — ~$228.00/mo (last charge 2025-09-14). Heuristic flagged inactive; LLM confirmed ongoing usage.
- PG&E — $17–64/mo (variance high). Heuristic variance penalty triggered; LLM validated as utility with variable billing.

Additional recurring charges inferred by LLM:
- Disney Plus — $19.32/mo (charges on 2024-12-24, 2025-01-25, 2025-07-25).

Cancelled subscriptions:
- Hulu — last seen 2025-04-20.

Total estimated monthly spend: ~$473.
Diagnostics: Heuristic skipped 22 merchants for cadence outside 20–365 days; fallback recommended (true).
```
