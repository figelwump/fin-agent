# Plan: Deprecate Analyzers & Improve Subscription Detection

**Created:** 2025-10-29
**Status:** Not Started

## Overview

This plan deprecates 5 low-value fin-analyze analyzers and replaces subscription detection with an LLM-based approach using fin-query. The programmatic subscription-detect analyzer is too brittle for sparse transaction data, missing most actual subscriptions due to strict cadence thresholds (20-40 days only).

## Analyzers Being Deprecated

- `subscription-detect` - Too brittle, high false negative rate
- `unusual-spending` - Better handled by LLM reasoning
- `spending-patterns` - Niche use case
- `category-evolution` - Derivative of category-timeline
- `category-suggestions` - Should be LLM task

## Phases

### Phase 1: Create Branch
- [ ] Create feature branch: `deprecate-analyzers-improve-subscriptions`

### Phase 2: Extend recent_transactions Query

**Goal:** Add date range parameters for flexible time window filtering

**Files to modify:**
1. `fin_cli/fin_query/queries/recent_transactions.sql`
   - [ ] Remove existing `month` parameter logic
   - [ ] Replace with WHERE clauses for `start_date` and `end_date` parameters
   - [ ] Ensure proper date range logic: `start_date` inclusive, `end_date` exclusive

2. `fin_cli/fin_query/queries/index.yaml`
   - [ ] Remove `month` parameter declaration
   - [ ] Add `start_date` parameter declaration (type: string, default: null, description)
   - [ ] Add `end_date` parameter declaration (type: string, default: null, description)

**New capabilities:**
```bash
# Date range filtering
fin-query saved recent_transactions --start_date 2025-01-01 --end_date 2025-10-01

# All transactions
fin-query saved recent_transactions --limit 0

# Specific month (using date range)
fin-query saved recent_transactions --start_date 2025-09-01 --end_date 2025-10-01
```

**Implementation notes:**
- SQL WHERE clause: `(:start_date IS NULL OR t.date >= :start_date) AND (:end_date IS NULL OR t.date < :end_date)`
- No executor.py changes needed - parameter system is fully generic
- start_date is inclusive, end_date is exclusive (standard date range convention)
- Breaking change: existing `--month` parameter will no longer work

### Phase 3: Update spending-analyzer SKILL.md

**Location:** `.claude/skills/spending-analyzer/SKILL.md`

**Changes:**

1. **Report Assembly Patterns section (lines 26-42):**
   - [ ] Remove "Monthly Summary Report" pattern (references deprecated analyzers)
   - [ ] Remove "Spending Anomaly Investigation" pattern (references unusual-spending)
   - [ ] Keep "Category Deep-Dive" pattern (uses non-deprecated analyzers)
   - [ ] Update "Subscription Audit" pattern with new LLM-based workflow

2. **Common Analyzers section (lines 44-52):**
   - [ ] Remove example commands for `subscription-detect` and `unusual-spending`

3. **Add new Subscription Audit pattern:**

```markdown
**Subscription Audit**
Combine: See $BASEDIR/workflows/subscription-detection.md
Use case: Review all recurring charges and identify cancellation opportunities
```

### Phase 4: Update reference/all-analyzers.md

**Location:** `.claude/skills/spending-analyzer/reference/all-analyzers.md`

**Changes:**
- [ ] Remove lines 19-21: subscription-detect entry
- [ ] Remove lines 23-25: unusual-spending entry
- [ ] Remove lines 27-29: spending-patterns entry
- [ ] Remove lines 31-33: category-suggestions entry
- [ ] Remove lines 35-37: category-evolution entry

**Keep these analyzers:**
- spending-trends
- category-breakdown
- merchant-frequency
- category-timeline

### Phase 5: Create Workflow Documentation

**Goal:** Create reusable workflow files for common analysis patterns

**Files to create:**

1. `.claude/skills/spending-analyzer/workflows/subscription-detection.md`
   - [ ] Create workflow for LLM-based subscription detection
   - [ ] Document how to query transactions with fin-query
   - [ ] Explain LLM reasoning steps
   - [ ] Show example output format

2. `.claude/skills/spending-analyzer/workflows/unusual-spending-detection.md`
   - [ ] Create workflow for LLM-based anomaly detection
   - [ ] Document which analyzers to run (category-breakdown, merchant-frequency)
   - [ ] Explain how LLM identifies anomalies
   - [ ] Show example output format

**Template structure for workflows:**
```markdown
# [Workflow Name]

## Purpose
[What this workflow accomplishes]

## Data Collection
[Commands to run to gather data]

## Analysis Steps
[How to apply LLM reasoning to the data]

## Output Format
[What the final result should look like]

## Example
[Concrete example with sample data and output]
```

### Phase 6: Update examples/custom-reports.md

**Location:** `.claude/skills/spending-analyzer/examples/custom-reports.md`

**Changes:**
- [ ] Replace `unusual-spending` command reference with: "See $BASEDIR/workflows/unusual-spending-detection.md"
- [ ] Replace `subscription-detect` command reference with: "See $BASEDIR/workflows/subscription-detection.md"
- [ ] Remove complete output sections for deprecated analyzers (lines 85-129)
- [ ] Add note that workflow files contain detailed steps for these analyses

**Ensure examples demonstrate:**
- Using spending-trends for temporal analysis
- Using category-breakdown for spending distribution
- Using merchant-frequency for recurring patterns
- Using category-timeline for category-specific trends

### Phase 7: Update examples/common-queries.md

**Location:** `.claude/skills/spending-analyzer/examples/common-queries.md`

**Changes:**

1. **"Find all my subscriptions" query (line 15):**
   - [ ] Replace with reference to workflow: "See $BASEDIR/workflows/subscription-detection.md"

2. **"Any unusual charges this month?" query (line 41):**
   - [ ] Replace with reference to workflow: "See $BASEDIR/workflows/unusual-spending-detection.md"

### Phase 8: Delete examples/insights.md

**Location:** `.claude/skills/spending-analyzer/examples/insights.md`

**Changes:**
- [ ] Delete file entirely (heavily references deprecated analyzers)

**Rationale:** This file recommends using subscription-detect, unusual-spending,
category-evolution, and spending-patterns - all deprecated. Rather than rewrite,
remove it since the other example files cover the remaining analyzers adequately.

---

## Testing Checklist

After implementation, verify:
- [ ] `fin-query saved recent_transactions --limit 0` returns all transactions
- [ ] `fin-query saved recent_transactions --start_date 2025-01-01 --end_date 2025-10-01` filters correctly
- [ ] `fin-query saved recent_transactions --month 2025-09` fails with appropriate error (breaking change)
- [ ] spending-analyzer skill successfully identifies subscriptions using workflow
- [ ] unusual spending detection workflow produces useful results
- [ ] No references to deprecated analyzers remain in skill documentation
- [ ] all-analyzers.md only lists the 4 retained analyzers
- [ ] Workflow files are properly referenced from SKILL.md and examples

## Files Modified Summary

**Code changes:**
1. `fin_cli/fin_query/queries/recent_transactions.sql` - Add date range parameters
2. `fin_cli/fin_query/queries/index.yaml` - Declare new parameters

**Documentation changes:**
3. `.claude/skills/spending-analyzer/SKILL.md` - Update patterns, remove deprecated analyzers
4. `.claude/skills/spending-analyzer/reference/all-analyzers.md` - Remove 5 analyzer entries
5. `.claude/skills/spending-analyzer/workflows/subscription-detection.md` - CREATE
6. `.claude/skills/spending-analyzer/workflows/unusual-spending-detection.md` - CREATE
7. `.claude/skills/spending-analyzer/examples/custom-reports.md` - Reference workflows
8. `.claude/skills/spending-analyzer/examples/common-queries.md` - Reference workflows
9. `.claude/skills/spending-analyzer/examples/insights.md` - DELETE

## Notes

- The subscription-detect analyzer remains in the codebase but is no longer documented
- Users with existing scripts using deprecated analyzers will not break (commands still exist)
- This is a documentation deprecation, not a code removal
- Can fully remove deprecated analyzer code in a future cleanup phase if desired
- The LLM-based subscription detection proved more effective in testing (found 10+ subscriptions vs 0 from programmatic)

## Architecture Decision

**Why LLM over programmatic for subscriptions?**
- Programmatic requires 20-40 day cadence (monthly only) - misses quarterly, annual, irregular
- Programmatic fails with sparse data (gaps between imports cause cadence calculation failure)
- LLM handles semantic understanding ("this looks like a subscription even with gaps")
- LLM can reason about edge cases programmatic code can't anticipate
- User's test case: programmatic found 0, LLM found 10+ actual subscriptions

**Tradeoff accepted:**
- LLM costs money (API calls) vs programmatic is free
- LLM is slower vs programmatic is instant
- LLM is non-deterministic vs programmatic is consistent
- BUT: Accuracy matters more than speed/cost for this use case
