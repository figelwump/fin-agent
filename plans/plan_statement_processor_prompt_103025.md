## plan_statement_processor_prompt_103025

- [x] Phase 1 – Assess Current Behavior
  - [x] Review extraction prompt language around transfers/ACH payments.
  - [x] Inspect example output showing ACH pulls included despite guidance.

- [x] Phase 2 – Prompt Updates
  - [x] Strengthen instructions to exclude ACH pulls, credit card/autopay transfers, and similar intra-account movements.
  - [x] Add explicit examples contrasting valid debits vs disallowed ACH pulls.
  - [x] Highlight negative examples to discourage tuition autopay duplication when already tracked elsewhere.

- [x] Phase 3 – Verification
  - [x] Update or add regression guidance/tests if applicable.
  - [x] Run targeted prompt rendering sanity check (no automated tests, but ensure template syntax intact).

**Notes**
- Focus on discouraging entries where description contains "ACH Pull", "payment", "transfer", or institution names matching known credit cards.
- Keep overall template tone consistent; additions should be brief but explicit.
