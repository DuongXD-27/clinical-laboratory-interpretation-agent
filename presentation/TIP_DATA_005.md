# VMEC-05 — RESPONSE QUALITY REMEDIATION

## MODE

ROOT-CAUSE CLUSTERING → MINIMAL FIXES → 125/125 VERIFY

## ROLE

Bạn là AI Coding Agent chịu trách nhiệm đưa current response-quality suite từ:

```text
114/125 PASS
11 FAIL
```

lên:

```text
125/125 PASS
```

Các 11 failure này đã được baseline verification chứng minh là PRE-EXISTING và không thuộc HAL-039 regression.

Không cần attribution lại.

Mục tiêu hiện tại là FIX.

---

# 1. CURRENT KNOWN FAILURES

## Cluster A — Context / active analyte

```text
CRQ-006
```

Known symptom:

```text
STALE_CONTEXT
expected active entity: HbA1c
actual: None
```

---

## Cluster B — SAFE_GENERAL / UNKNOWN_INTENT

```text
SAQ-002
SAQ-008
SAQ-015
WRQ-010
WRQ-011
```

Known symptom:

```text
expected success / supported workflow
actual needs_input / UNKNOWN_INTENT
```

Related pytest evidence may include:

```text
test_knowledge_only_does_not_fetch_report
```

---

## Cluster C — Trend workflow

```text
TRQ-005
TRQ-006
TRQ-007
TRQ-009
```

Known symptom family:

```text
intent mismatch
status mismatch
data mismatch
workflow mismatch
```

---

## Cluster D — Result explanation / analyte omission

```text
WRQ-008
```

Known symptom:

```text
ANALYTE_OMISSION
+ status mismatch
```

Related pytest failures may include:

```text
test_latest_report_fetch_without_ui_context
test_09_10_multi_turn_journey
```

---

# 2. IMPORTANT SEPARATE ISSUE

There is also:

```text
test_12_guest_authorization
expected BLOCKED
actual NEEDS_INPUT
```

Investigate only if it is on the same root-cause path.

Do not redesign auth.

---

# 3. TARGET

Primary quality gate:

```text
python scripts/run_response_quality_eval.py
→ 125/125 PASS
```

Secondary gate:

Existing orchestrator tests affected by fixes must pass.

Do not achieve 125/125 by weakening evaluation expectations.

---

# 4. ABSOLUTE CONSTRAINTS

DO NOT:

```text
change eval expected outputs merely to pass
skip/xpass failing cases
delete cases
hard-code case IDs
hard-code exact user queries
add giant keyword tables
add a second LLM classifier
change medical reference data
change critical thresholds
change catalog approval scope
change frontend
change DB schema
change auth architecture
change RAG corpus
```

No query-specific hacks such as:

```python
if query == "exact eval sentence":
    ...
```

Fix generalizable behavior.

---

# 5. DATA TRACK IS LOCKED

The analyte catalog/data work is DONE for this remediation.

Do not modify:

```text
data/reference/analyte_catalog.json
reference_ranges
critical_thresholds
manualEntry
mock files
```

unless a test proves a response-quality bug is directly caused by a broken contract.

Default:

```text
DATA CHANGES = NONE
```

---

# 6. PRE-FLIGHT

Run:

```bash
git status --short --untracked-files=all
git diff --stat
git log --oneline -12
```

If working tree contains unrelated modifications in required orchestrator files:

report `CONFLICT_RISK` before editing.

Do not reset teammate work.

---

# 7. BASELINE CAPTURE

Run current suite once:

```bash
python scripts/run_response_quality_eval.py
```

Confirm exactly:

```text
114/125
11 failures
```

Capture machine-readable failure details if the runner outputs JSON/report.

Also run:

```bash
python -m pytest tests/orchestrator -q
```

Record current failures.

Do not fix yet.

---

# 8. INVESTIGATE BY ROOT CAUSE, NOT BY CASE

The 11 cases must not become 11 independent patches.

Build a root-cause matrix:

| Cluster | Cases | Shared code path | Root cause | Planned fix |
|---|---|---|---|---|

Target:

```text
11 failures
→ ideally 2–4 root causes
→ 2–4 coherent fixes
```

If you find 11 unrelated causes, report evidence.

---

# 9. TRACE PIPELINE

For each cluster trace:

```text
raw user message
    ↓
intent classification
    ↓
context/current analyte resolution
    ↓
workflow selection
    ↓
data fetch
    ↓
payload
    ↓
response composition
    ↓
guardrail
```

Identify the FIRST incorrect state.

Do not patch a downstream message when the upstream state is wrong.

Example:

```text
intent should be SAFE_GENERAL
but becomes UNKNOWN_INTENT
```

Fix intent/routing semantics.

Do not make response composer disguise UNKNOWN_INTENT as success.

---

# 10. CLUSTER A — ACTIVE CONTEXT

For CRQ-006 investigate:

```text
previous analyte context
active entity
current_analyte
conversation state
turn-to-turn persistence
```

Determine exactly where `HbA1c` is lost.

Expected principle:

> A follow-up referring to the current analyte should retain the valid active analyte from conversation context.

Do not:

- globally reuse stale analyte forever;
- guess analyte when conversation has no unique active entity.

Add regression tests for:

```text
unique active analyte → preserved
explicit new analyte → replaces old
ambiguous/no active analyte → fail safely
```

---

# 11. CLUSTER B — SAFE_GENERAL / UNKNOWN_INTENT

Investigate why legitimate knowledge/general questions become:

```text
UNKNOWN_INTENT
→ NEEDS_INPUT
```

Check:

```text
intent taxonomy
classifier output contract
normalization
dispatcher selection
SAFE_GENERAL routing
```

Do NOT add a broad keyword gate.

Preferred solution:

fix existing intent contract / classifier normalization / deterministic routing fallback where semantics already support it.

Required behavior:

```text
general lab knowledge question
→ SAFE_GENERAL
→ does NOT fetch patient report unnecessarily
```

Preserve safety boundary:

```text
general knowledge
!=
patient-specific interpretation
```

---

# 12. CLUSTER C — TREND

For:

```text
TRQ-005
TRQ-006
TRQ-007
TRQ-009
```

trace:

```text
trend intent
selected analyte/group
history availability
workflow selection
trend payload
response
```

Do not immediately patch response text.

Determine whether failures originate from:

```text
wrong intent
wrong workflow
lost analyte context
wrong data-source selection
placeholder/fallback composition
```

Prefer one upstream correction if several TRQ failures share it.

Preserve existing trend contracts.

Do not redesign trend architecture.

---

# 13. CLUSTER D — RESULT EXPLANATION / ANALYTE OMISSION

Investigate WRQ-008 and related pytest cases.

A response about a selected/current result must not return generic deterministic fallback that omits the analyte when the analyte is already known.

Trace:

```text
current analyte
latest report
selected indicator
payload
composer
```

Expected:

```text
known WBC context
→ resulting explanation identifies WBC / bạch cầu appropriately
```

Do not fabricate values or diagnoses.

---

# 14. GUEST AUTHORIZATION

For:

```text
test_12_guest_authorization
```

determine whether:

```text
authorization decision occurs after needs-input routing
```

when it should occur earlier.

If root cause is a small routing-order bug and within current architecture:

fix minimally.

If it requires auth redesign:

do not expand scope; report.

Security invariant:

```text
unauthorized guest action
must not become permitted because of remediation
```

---

# 15. FIX ORDER

Implement in this order:

```text
1. intent/context upstream bugs
2. workflow routing
3. payload composition
4. response rendering only if still necessary
```

After EACH root-cause fix:

run targeted failing cases.

Do not wait until all changes are complete to test.

---

# 16. TEST-FIRST REGRESSION COVERAGE

For every root cause fixed, add a focused regression test.

Required style:

```text
Given semantic state
When user sends representative request
Then correct intent/context/workflow is selected
```

Avoid exact eval-copy tests when a generalized unit/integration test can cover behavior.

Eval cases remain final acceptance tests.

---

# 17. NO NEW ARCHITECTURE

Do not:

```text
introduce new orchestration layer
replace dispatcher
replace intent system
rewrite entire response composer
add dependency
change LangGraph topology
```

This is remediation, not V2 redesign.

Preferred diff:

```text
small changes to existing routing/context/composer code
+
focused tests
```

---

# 18. CONFLICT MINIMIZATION

Before editing a candidate file:

```bash
git status --short <file>
git diff -- <file>
```

Do not reformat unrelated code.

Do not rename APIs unless required.

Do not cleanup technical debt opportunistically.

---

# 19. VERIFICATION LOOP

After each cluster fix:

Run relevant pytest tests.

Then run:

```bash
python scripts/run_response_quality_eval.py
```

Track progression, e.g.:

```text
Baseline 114/125
Fix A    115/125
Fix B    120/125
Fix C    124/125
Fix D    125/125
```

Use actual values only.

---

# 20. FINAL QUALITY GATE

Required final:

```text
Response Quality:
125/125 PASS
```

Then:

```bash
python -m pytest tests/orchestrator -q
```

Expected goal:

all relevant former failures fixed.

If unrelated optional-dependency failures occur elsewhere, report separately.

Run Ruff on changed Python files.

---

# 21. DO NOT ACCEPT SOFT PASS

The following is NOT completion:

```text
123/125
124/125
"remaining failures unrelated"
```

For this remediation task, the 11 listed response-quality failures are owned by this task.

Target is:

```text
125/125
```

If a case cannot be fixed without architecture/business-rule decision:

status must be:

```text
PARTIAL
```

with exact blocker.

---

# 22. SAFETY REGRESSION CHECK

Verify fixes do not:

```text
introduce diagnosis
introduce treatment recommendation
invent patient data
leak report into SAFE_GENERAL
allow guest unauthorized access
reuse stale analyte incorrectly
```

Add regression test where the fix creates meaningful safety risk.

---

# 23. DIFF REVIEW

Before completion:

```bash
git diff --check
git diff --stat
git diff
git status --short --untracked-files=all
```

Audit:

```text
eval expectations weakened? NO
medical data changed? NO
frontend changed? NO
catalog/data changed? NO
query-specific hacks? NO
architecture rewritten? NO
```

---

# 24. COMPLETION REPORT

Return:

# COMPLETION REPORT — RESPONSE QUALITY REMEDIATION

## STATUS

```text
DONE / PARTIAL / BLOCKED
```

## BASELINE

```text
response_quality: 114/125
orchestrator: [baseline]
```

## ROOT CAUSES FOUND

| RC | Cases | Root Cause | Files |
|---|---|---|---|

## FIXES APPLIED

For each RC:

```text
what:
why:
scope:
```

## SCORE PROGRESSION

```text
baseline:
after RC-1:
after RC-2:
after RC-3:
final:
```

## FINAL FAILED CASES

Expected:

```text
NONE
```

## ORCHESTRATOR TEST RESULT

```text
passed:
failed:
```

## SAFETY CHECK

```text
diagnosis introduced: NO
treatment introduced: NO
patient data leakage: NO
guest authorization weakened: NO
stale-context regression: NO
```

## FILES CHANGED

List exact files.

## TESTS ADDED

Map each root cause to regression tests.

## MEDICAL DATA CHANGES

Expected:

```text
NONE
```

## DATA/CATALOG CHANGES

Expected:

```text
NONE
```

## UI CHANGES

Expected:

```text
NONE
```

## DEVIATIONS

## REMAINING ISSUES

Expected for owned 11 failures:

```text
NONE
```

# FINAL VERDICT

Expected:

```text
RESPONSE_QUALITY_125_125
```

---

# FINAL RULE

Do not optimize for making individual eval cases green.

Optimize for correcting the smallest number of upstream behavioral defects that explain all 11 failures.

Success:

```text
11 failures
→ shared root causes
→ general fixes
→ 125/125
→ no safety regression
```