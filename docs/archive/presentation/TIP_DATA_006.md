# VMEC-05 — TIP_DATA_006  
# 35/35 RUNTIME EXPANSION READINESS AUDIT

## ROLE

Bạn là AI Coding Agent / BUILDER.

Các TIP trước đã hoàn thành:

```text
TIP_DATA_001 ✅ Data consistency guardrails
TIP_DATA_002 ✅ Canonical analyte catalog
TIP_DATA_003 ✅ Backend/runtime catalog alignment
TIP_DATA_004 ✅ Frontend/mock alignment
TIP_DATA_005 ✅ Response quality remediation
```

Quality gate hiện tại:

```text
Response quality: 125/125 PASS
Orchestrator tests: 229/229 PASS
Targeted orchestrator: 50/50 PASS
Ruff targeted: PASS
```

Canonical catalog hiện có:

```text
data/reference/analyte_catalog.json
```

Runtime hiện tại:

```text
APPROVED: 9
HOLD: 1
UNSUPPORTED: 25
```

Approved exact set:

```text
WBC
RBC
HGB
Fasting plasma glucose
HbA1c
LDL-C
HDL-C
Creatinine
Potassium
```

Special status:

```text
Uric acid = HOLD
eGFR = UNSUPPORTED
```

---

# 1. OBJECTIVE

Mục tiêu duy nhất của TIP này:

> Audit toàn bộ 35 analyte trong scope chính của VMEC-05 để xác định analyte nào thực sự READY để mở rộng runtime support và analyte nào còn gap.

Không approve thêm analyte.

Không sửa medical data.

Không sửa runtime behavior.

Không sửa frontend.

Không sửa orchestrator.

Không redesign RAG.

Output cuối cùng phải giúp Contractor chia chính xác:

```text
TIP_DATA_007 — Expansion Batch 1
TIP_DATA_008 — Expansion Batch 2
...
```

mà không phải audit lại.

---

# 2. MODE

```text
READ-ONLY AUDIT
→ TRACE ARTIFACTS
→ CLASSIFY READINESS
→ BUILD EXPANSION PLAN
→ REPORT
```

Default:

```text
FILES CHANGED = NONE
```

Nếu cần tạo report artifact thì chỉ được tạo đúng một file audit/report riêng và không sửa runtime/data.

---

# 3. ABSOLUTE RULES

DO NOT:

```text
change analyte runtime_status
approve unsupported analyte
change HOLD status
change reference ranges
change critical thresholds
change clinical bands
change aliases
change unit conversion factors
change demographic rules
change explanation content
change question templates
change frontend
change mocks
change orchestrator
change RAG
change eval expectations
change database/schema
```

Không sửa lỗi phát hiện trong audit.

Chỉ report.

---

# 4. IMPORTANT DEFINITION

Phải phân biệt:

```text
CATALOG PRESENCE
!=
RUNTIME READINESS
!=
RUNTIME APPROVAL
```

Một analyte có mặt trong:

```text
explanations.json
critical_thresholds.json
question_templates.json
```

không có nghĩa analyte đã READY.

Một analyte chỉ READY khi đủ toàn bộ capability contract bắt buộc.

---

# 5. SCOPE — 35 ANALYTES

Audit đúng **35 analyte chính của project**.

Không tự thêm:

```text
eGFR
BASO
MPV
```

vào mẫu số 35 nếu chúng không thuộc locked 35 catalog scope hiện tại.

Nếu chúng xuất hiện trong mock/unit registry:

report riêng:

```text
OUT_OF_SCOPE / UNRESOLVED / MOCK_ONLY
```

Không đưa vào denominator 35.

---

# 6. PRE-FLIGHT

Run:

```bash
git status --short --untracked-files=all
git diff --stat
git log --oneline -12
```

Xác minh repository hiện chứa đúng các TIP dependency đã hoàn thành.

Nếu working tree có unrelated changes:

không overwrite.

Audit read-only vẫn có thể tiếp tục nếu không ảnh hưởng evidence.

Report:

```text
WORKTREE_RISK
```

nếu cần.

---

# 7. FILES / SOURCES TO AUDIT

Read minimum:

```text
data/reference/analyte_catalog.json
data/reference/reference_ranges.json
data/reference/critical_thresholds.json
data/reference/explanations.json
data/reference/question_templates.json
data/reference/units_metric.csv
data/reference/reference_checker_config.json
```

Also inspect:

```text
src/services/analyte_catalog.py
src/services/reference_repository.py
src/services/analyte_resolver.py
src/services/indicator_catalog_service.py
src/services/analyte_sections.py
```

And relevant tests:

```text
tests/test_data/**
tests/test_services/test_analyte_catalog.py
tests/test_services/test_runtime_catalog_alignment.py
tests/test_services/test_reference_repository.py
tests/test_agents/test_reference_range_checker_node.py
tests related to critical detector
tests related to question templates
```

Search actual consumers rather than assuming.

---

# 8. READINESS DIMENSIONS

For every one of the 35 analytes, audit all dimensions below.

---

## R1 — CANONICAL IDENTITY

Check:

```text
analyte_id
canonical_name
canonical_group
runtime_status
```

Required for READY:

```text
unique analyte_id
unique canonical_name
valid group
catalog entry exists
```

---

## R2 — ALIAS SAFETY

Check:

```text
aliases exist?
aliases normalize deterministically?
any alias collision?
common OCR/mock names resolvable?
```

READY requires:

```text
no ambiguous alias
no multi-canonical collision
```

Important:

An analyte does NOT need many aliases to be READY.

It needs safe identity resolution for supported runtime paths.

---

## R3 — REFERENCE RULE

Check:

```text
reference range exists?
reference type supported?
lower/upper/band semantics complete?
demographic selector required?
age/sex selector supported?
```

READY requires a deterministic runtime classification contract.

If reference rule is missing:

```text
NOT_READY_REFERENCE
```

---

## R4 — UNIT CONTRACT

Check:

```text
canonical unit
reference rule unit
accepted runtime input units
normalization
conversion path
```

Classify unit state:

```text
DIRECT
NORMALIZATION_ONLY
CONVERSION_SUPPORTED
GAP
```

READY requires:

```text
DIRECT
or NORMALIZATION_ONLY
or verified CONVERSION_SUPPORTED
```

No guessed conversion.

---

## R5 — DEMOGRAPHIC SAFETY

If analyte has demographic-specific rule:

verify:

```text
sex selector
age selector
adult/pediatric boundary if relevant
fallback behavior
```

If no demographic rule is needed:

```text
N/A
```

Do not invent demographic logic.

---

## R6 — EXPLANATION COVERAGE

Check:

```text
explanation entry exists?
normal/high/low notes as applicable?
limitations?
source metadata?
```

Do not judge prose quality subjectively.

Only audit runtime artifact completeness and traceability required by current system.

---

## R7 — QUESTION TEMPLATE COVERAGE

Check:

```text
question template exists?
analyte ID resolves?
template runtime-compatible?
```

READY requires current question path not to fail due missing template.

---

## R8 — CRITICAL POLICY

IMPORTANT:

READY does NOT require an active critical threshold.

For each analyte classify:

```text
ACTIVE_CRITICAL_RULE
INACTIVE_BY_POLICY
NO_AUTHORIZED_RULE
NOT_APPLICABLE
```

Critical detector must remain fail-closed.

Do NOT classify an analyte NOT_READY merely because ARUP/current declared authority does not define a critical threshold.

However:

if an active critical rule exists, verify:

```text
operator
threshold
unit
conversion
side activation
tests
```

---

## R9 — EXISTING TEST COVERAGE

Check whether analyte is already covered by:

```text
reference checker tests
boundary tests
unit tests
alias tests
demographic tests
critical tests if applicable
```

Classify:

```text
STRONG
PARTIAL
NONE
```

Do not equate generic framework tests with analyte-specific readiness without evidence.

---

## R10 — RUNTIME INTEGRATION RISK

Classify:

```text
LOW
MEDIUM
HIGH
```

Examples:

### LOW

```text
complete reference rule
direct unit
simple aliases
no demographic complexity
no special clinical bands
```

### MEDIUM

```text
unit conversion
multiple aliases
one-sided limit
demographic selector
```

### HIGH

```text
missing rule
ambiguous alias
missing conversion
complex demographic logic
inconsistent cross-file values
```

---

# 9. READINESS CLASSIFICATION

Each analyte must receive exactly one final status:

## READY

All mandatory runtime artifacts complete.

Could be moved to APPROVED in next TIP with mainly:

```text
status activation
tests
regression verification
```

---

## READY_WITH_TEST_GAP

Medical/runtime contract appears complete, but analyte-specific tests are insufficient.

Next TIP should add tests before or together with activation.

---

## NEEDS_ALIAS_FIX

Identity ambiguity / missing necessary alias.

---

## NEEDS_UNIT_FIX

Runtime input/reference unit contract incomplete.

---

## NEEDS_REFERENCE_RULE

Missing/incomplete deterministic reference contract.

---

## NEEDS_DEMOGRAPHIC_RULE

Required demographic selection incomplete.

---

## NEEDS_CONTENT_ARTIFACT

Missing explanation/question runtime artifact.

---

## HOLD

Explicit project/medical authority hold.

Example:

```text
Uric acid
```

---

## UNSUPPORTED_BY_SCOPE

Intentionally unsupported in current scope.

Use only if there is explicit evidence.

Do not classify merely because current `runtime_status` is UNSUPPORTED.

The audit is specifically trying to determine whether that status can change later.

---

# 10. IMPORTANT — DO NOT LET CURRENT STATUS BIAS READINESS

Most analytes currently say:

```text
runtime_status = UNSUPPORTED
```

That is current activation status, not evidence they are unready.

Audit the artifacts independently.

Example:

```text
runtime_status = UNSUPPORTED
reference = complete
unit = complete
aliases = complete
explanation = complete
questions = complete
tests = sufficient
```

Result may be:

```text
READY
```

Do NOT automatically return UNSUPPORTED.

---

# 11. REFERENCE TYPES

Detect actual reference-rule families used in repo.

Likely examples may include:

```text
STANDARD_RANGE
ONE_SIDED_LIMIT
BAND / DECISION_LIMIT
demographic-specific rules
```

Do not invent names if repository uses different terminology.

For each analyte record actual rule type.

This will be used for batch grouping.

---

# 12. BATCHING STRATEGY

After readiness audit, propose expansion batches.

Goal:

> maximize analyte count per batch while minimizing shared risk.

Prefer grouping analytes with similar deterministic behavior.

Example concept only:

```text
Batch A
simple standard-range analytes

Batch B
electrolytes / one-sided rules

Batch C
lipid/decision-band analytes

Batch D
demographic/special-unit cases
```

Do not use this example blindly.

Derive actual batches from repository evidence.

---

# 13. BATCH SIZE

Preferred:

```text
4–8 analytes per batch
```

unless evidence suggests otherwise.

Avoid:

```text
26 analytes in one activation PR
```

unless audit proves they are mechanically identical and safe, which must be explicitly justified.

---

# 14. ACTIVATION COST

For each READY analyte estimate activation effort:

```text
TRIVIAL
SMALL
MEDIUM
BLOCKED
```

Definition:

### TRIVIAL

```text
status activation + tests only
```

### SMALL

```text
minor alias/test/config alignment
```

### MEDIUM

```text
unit/demographic/test work
```

### BLOCKED

```text
missing medical/reference authority
```

No time estimates required.

---

# 15. REQUIRED 35-ROW MATRIX

Output exactly one row for every analyte:

| # | Analyte | Current Status | Group | Ref Rule | Unit | Alias | Explanation | Questions | Critical | Tests | Risk | Readiness |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

No omitted analytes.

No summary-only answer.

---

# 16. GAP DETAIL TABLE

For every non-READY analyte:

| Analyte | Blocking Gap | Evidence | Required Fix | Decision Needed? |
|---|---|---|---|---|

Be specific.

Bad:

```text
data incomplete
```

Good:

```text
HCT mock/manual unit = %, reference rule = L/L,
no existing %→L/L conversion contract
```

---

# 17. READY LIST

Return:

```text
READY_NOW:
- ...

READY_WITH_TEST_GAP:
- ...

BLOCKED:
- ...
```

And totals:

```text
CURRENT_APPROVED = 9/35
READY_NOT_APPROVED = X
BLOCKED_OR_HOLD = Y
POTENTIAL_POST_AUDIT_COVERAGE = Z/35
```

Where:

```text
Z =
current approved
+
READY
+
READY_WITH_TEST_GAP
```

Do not count blocked analytes.

---

# 18. 35/35 GAP

Explicitly answer:

```text
Can project reach 35/35 with existing medical artifacts?
YES / NO / PARTIALLY
```

Then:

```text
If NO:
which analytes prevent 35/35?
why?
```

This is one of the most important outputs.

---

# 19. URIC ACID

Audit fully but preserve:

```text
current status = HOLD
```

Report:

```text
what exactly is missing/blocking approval?
```

Do not add reference range/source.

---

# 20. eGFR / BASO / MPV

Report separately under:

```text
OUT-OF-SCOPE / AUXILIARY FINDINGS
```

For:

```text
eGFR
BASO (absolute)
BASO (percentage)
MPV
```

Do not include them in 35/35 readiness denominator unless repository evidence proves they are members of locked 35.

---

# 21. CRITICAL DETECTOR RULE

Repeat clearly in report:

```text
35/35 runtime support
DOES NOT REQUIRE
35/35 active critical thresholds
```

Audit must identify critical coverage but not treat inactive/no-authority critical rules as blocker to general runtime support.

Critical activation remains separately governed by declared critical authority.

---

# 22. OPTIONAL AUTOMATED AUDIT

You may write a temporary local script outside tracked repo or use existing tests to compute matrix.

Preferred:

```text
read-only Python script
```

Do not commit the script unless there is a strong reusable QA value.

If you propose committing a readiness checker:

STOP and report recommendation first.

This TIP is audit-only.

---

# 23. TEST EXECUTION

Run existing tests needed to validate conclusions.

Minimum:

```bash
python -m pytest tests/test_data -q
```

Relevant catalog/runtime/reference suites.

Relevant critical detector tests.

Relevant unit tests.

Do not modify tests to make readiness look better.

---

# 24. NO PASS-BY-PRESENCE

Bad readiness logic:

```text
exists in JSON → READY
```

Required logic:

```text
identity
+ deterministic rule
+ unit contract
+ runtime artifact coverage
+ safe aliasing
+ required tests
→ READY
```

---

# 25. EVIDENCE STANDARD

Every BLOCKED/HOLD determination needs evidence:

```text
file
field/rule
test or observed gap
```

Every READY determination should also point to major artifacts supporting it.

No medical knowledge inference from model memory.

Use repository as authority for this audit.

---

# 26. WORKTREE / DIFF RULE

At end:

```bash
git status --short
git diff --check
git diff --stat
```

Expected:

```text
implementation files changed: NONE
medical data changed: NONE
runtime changed: NONE
```

If eval/test runner changes generated artifacts:

restore only generated artifacts created by this audit.

Do not disturb pre-existing teammate changes.

---

# 27. ACCEPTANCE CRITERIA

## AC-01

Exactly 35 scoped analytes audited.

## AC-02

Every analyte gets a readiness classification.

## AC-03

Current APPROVED 9 remain unchanged.

## AC-04

No runtime/data/code changes.

## AC-05

Every non-ready analyte has an explicit blocking gap.

## AC-06

READY analytes have sufficient evidence, not merely file presence.

## AC-07

Critical inactive/no-authority status is not incorrectly treated as general runtime blocker.

## AC-08

A concrete batch activation plan is produced.

## AC-09

Project's real path to 35/35 is quantified.

---

# 28. COMPLETION REPORT

Return exactly:

# COMPLETION REPORT — TIP_DATA_006

## STATUS

```text
DONE / PARTIAL / BLOCKED
```

## EXECUTIVE SUMMARY

```text
current approved:
ready but not approved:
ready with test gap:
blocked:
hold:
potential coverage:
```

## 35/35 VERDICT

```text
CAN_REACH_35_35_WITH_EXISTING_ARTIFACTS:
YES / NO / PARTIALLY
```

Explain briefly.

## FULL READINESS MATRIX

35 rows exactly.

## READY NOW

List.

## READY WITH TEST GAP

List.

## BLOCKED / HOLD

List with reason.

## GAP DETAIL

Detailed table.

## REFERENCE RULE COVERAGE

```text
standard range:
one-sided:
decision/band:
demographic:
missing:
```

Use actual repo terminology.

## UNIT READINESS

```text
direct:
normalization:
conversion:
unit gaps:
```

## ALIAS READINESS

```text
safe:
needs fix:
ambiguous:
```

## CRITICAL COVERAGE

```text
active rules:
inactive/no-authority:
critical gaps that actually block runtime:
```

Remember general runtime readiness != critical-rule availability.

## TEST COVERAGE

```text
strong:
partial:
none:
```

## PROPOSED EXPANSION BATCHES

### TIP_DATA_007 — Batch 1

Analytes:

```text
...
```

Reason:

```text
...
```

Expected work:

```text
...
```

### TIP_DATA_008 — Batch 2

...

Continue only as many batches as evidence requires.

## FASTEST PATH TO 35/35

Give ordered sequence:

```text
1.
2.
3.
...
```

Prioritize highest analyte gain for lowest risk.

## OUT-OF-SCOPE / AUXILIARY FINDINGS

Cover:

```text
eGFR
BASO
MPV
```

if applicable.

## TEST RESULTS

List exact commands/results.

## FILES CHANGED

Expected:

```text
NONE
```

## MEDICAL DATA CHANGES

Expected:

```text
NONE
```

## RUNTIME CAPABILITY CHANGES

Expected:

```text
NONE
```

## CONFLICT RISK

## DECISIONS REQUIRED BEFORE ACTIVATION

Only include decisions that genuinely block subsequent batch activation.

---

# FINAL RULE

TIP_DATA_006 does not activate anything.

It answers one question rigorously:

> Of the 35 analytes in VMEC-05, which ones can be safely activated next, which ones cannot, and what is the fastest evidence-based path from 9/35 to 35/35?

Do not make medical or product decisions that are not already supported by repository evidence.