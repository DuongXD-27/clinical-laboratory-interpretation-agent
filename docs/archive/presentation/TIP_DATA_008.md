# VMEC-05 — TIP_DATA_008
# URIC ACID ACTIVATION + FINAL 35/35 E2E + RELEASE VERIFY + HANDOVER

## ROLE

Bạn là **BUILDER / AI Coding Agent** phụ trách TIP cuối của track mở rộng analyte VMEC-05.

Đây là task kết hợp:

1. Bổ sung deterministic reference rule cho **Uric acid** theo authority đã được con người chốt.
2. Chuyển runtime từ **34/35 → 35/35**.
3. Chạy **full E2E / release verification** cho toàn bộ 35 analyte.
4. Tạo **báo cáo bàn giao cuối** để trưởng nhóm có thể nghiệm thu và nhận hệ thống.

Không mở thêm feature mới.

---

# 0. TRUSTED PROJECT STATE

Các TIP trước đã hoàn thành:

```text
TIP_DATA_001 ✅ Data consistency guardrails
TIP_DATA_002 ✅ Canonical analyte catalog
TIP_DATA_003 ✅ Backend/runtime catalog alignment
TIP_DATA_004 ✅ Frontend/mock alignment
TIP_DATA_005 ✅ Response quality remediation — 125/125
TIP_DATA_006 ✅ 35/35 readiness audit
TIP_DATA_007 ✅ Full runtime expansion — 34/35
```

Current verified runtime:

```text
LOCKED_35 analytes: 35

APPROVED: 34
HOLD: 1 — Uric acid

Response quality: 125/125 PASS
Orchestrator: 229/229 PASS
Frontend tests: PASS
Frontend build: PASS
Medical numeric data changed during TIP_DATA_007: NONE
```

Current auxiliary analytes remain outside locked-35 denominator:

```text
eGFR = UNSUPPORTED
BASO = out-of-scope/unresolved
MPV = out-of-scope/unresolved
```

Do not add them to the 35-analyte production claim.

---

# 1. HUMAN-APPROVED URIC ACID AUTHORITY

The Human/Project Lead has approved the following source as the operational reference-interval authority for Uric acid in VMEC-05 V1:

```text
Organization:
Gloucestershire Hospitals NHS Foundation Trust

Document / Page:
Clinical Biochemistry — Uric Acid / Urate

Source:
https://www.gloshospitals.nhs.uk/our-services/services-we-offer/pathology/tests-and-investigations/uric-acid-urate/

Reference population:
Age 19 years and older

Female:
140–360 µmol/L

Male:
200–430 µmol/L

Reference type:
RI

Source priority:
T2

Confidence:
HIGH
```

This human decision authorizes ONLY the Uric acid **reference interval** above.

It does NOT authorize:

- any Uric acid critical threshold;
- any new diagnostic claim;
- any treatment rule;
- any pediatric extrapolation;
- any alternative unit range not deterministically converted through an existing approved unit contract.

---

# 2. HARD MEDICAL CONTRACT

The intended deterministic rules are:

## Female, age >= 19

```text
Analyte: Uric acid
Sex: F
Age scope: >=19
Canonical unit: umol/L
Display/source unit: µmol/L
Lower: 140
Upper: 360
Reference type: RI
```

Expected classification semantics must follow the repository's existing RI boundary contract.

Do NOT invent new inclusive/exclusive semantics.

---

## Male, age >= 19

```text
Analyte: Uric acid
Sex: M
Age scope: >=19
Canonical unit: umol/L
Display/source unit: µmol/L
Lower: 200
Upper: 430
Reference type: RI
```

Expected classification semantics must follow existing RI behavior.

---

# 3. AGE-SCOPE HARD GATE

The approved source states:

```text
19 years and older
```

Do NOT silently convert this to generic:

```text
Adult
```

unless the existing project age contract explicitly defines `Adult` as exactly compatible with `>=19`.

Before editing medical artifacts, inspect the existing age-scope selection implementation.

Determine:

```text
A. Runtime already supports an exact >=19 representation
B. Runtime has a reusable min-age representation
C. Runtime only supports broad labels such as Adult / 18–60
```

## If A or B

Use the existing deterministic representation.

Preferred outcome:

```text
min_age = 19
```

or repository-equivalent.

## If C

Implement the **smallest deterministic age-scope extension** necessary to represent `>=19`.

Requirements:

- do not redesign demographic architecture;
- do not change existing analyte age semantics;
- add regression tests proving existing age rules remain unchanged;
- Uric acid age 18 must NOT receive the >=19 reference rule;
- age 19 must receive the rule;
- older adult ages must receive the rule.

If an exact >=19 rule cannot be represented safely without a broad architecture change:

```text
STOP
STATUS = BLOCKED_BY_AGE_SCOPE_CONTRACT
```

Do not flatten the source to `Adult` merely to achieve 35/35.

---

# 4. UNIT CONTRACT

Approved source unit:

```text
µmol/L
```

Canonical project representation:

```text
umol/L
```

This must be handled as existing **unit-label normalization** if that behavior already exists.

Required:

```text
µmol/L
→ umol/L
```

with numeric value unchanged.

Do NOT add a conversion factor for this notation normalization.

If other Uric acid units such as `mg/dL` appear in mocks/OCR:

- do not automatically support them;
- only support them if an existing approved analyte-specific conversion contract is already present and reusable;
- otherwise fail closed / report unsupported unit.

This TIP does not require mg/dL support for Uric acid.

---

# 5. CRITICAL POLICY — ABSOLUTE

Activating Uric acid for LOW/NORMAL/HIGH does **NOT** authorize a critical alert.

Required final state:

```text
Uric acid runtime reference support: APPROVED
Uric acid critical rule: INACTIVE / NO_AUTHORIZED_RULE
```

Do NOT:

```text
create critical_low
create critical_high
copy a hospital critical value
derive critical values from explanation text
```

Existing declared critical policy remains unchanged.

Expected:

```text
NEW_URIC_ACID_CRITICAL_RULES = 0
NEW_UNAUTHORIZED_CRITICAL_RULES = 0
```

---

# 6. PRE-FLIGHT

Before modifying anything:

```bash
git status --short --untracked-files=all
git diff --stat
git diff
git log --oneline -15
```

Record:

```text
BASE_COMMIT:
WORKTREE_DIRTY:
CONFLICT_RISK_FILES:
```

Do NOT use:

```bash
git add .
git reset --hard
git clean -fd
git checkout .
git stash
```

There may still be unrelated frontend/presentation files from previous tasks.

Preserve them.

Before editing each required file:

```bash
git status --short <file>
git diff -- <file>
```

If a required file contains unrelated teammate work:

- preserve those changes;
- make the smallest non-destructive edit;
- report the risk.

---

# 7. FOCUSED SCAN BEFORE IMPLEMENTATION

Read actual current repository state.

Minimum:

```text
data/reference/analyte_catalog.json
data/reference/reference_ranges.json
data/reference/reference_checker_config.json
data/reference/critical_thresholds.json
data/reference/units_metric.csv
data/reference/explanations.json
data/reference/question_templates.json

src/services/analyte_catalog.py
src/services/reference_repository.py
src/agents/nodes/reference_range_checker_node.py

frontend/src/lib/manualEntry.mjs

tests/test_data/**
tests/test_services/test_runtime_catalog_alignment.py
tests/test_services/test_reference_repository.py
tests/test_agents/test_reference_range_checker_node.py
tests/test_agents/test_critical_detector_node.py
tests/orchestrator/**
```

Search:

```bash
rg -n "Uric acid|Uric Acid|uric_acid|urate" data src frontend tests
rg -n "age_scope|min_age|max_age|Adult|18–60" src tests data
rg -n "umol/L|µmol/L" src data tests
```

Confirm before implementation:

```text
Uric acid catalog entry exists
runtime_status = HOLD
alias identity is safe
explanation exists
question template exists
reference rule is absent
critical rule is inactive/non-authoritative
```

If these assumptions are false:

report before changing behavior.

---

# 8. REFERENCE RULE IMPLEMENTATION

Add the minimal deterministic Uric acid reference artifact using the repository's actual schema and build mechanism.

Do not hand-edit a generated artifact if the project uses an authoritative source + generator workflow.

First determine:

```text
AUTHORING_SOURCE:
GENERATED_ARTIFACT:
BUILD_SCRIPT:
```

Prefer:

```text
approved source artifact
→ build/generator
→ reference_ranges.json
```

over:

```text
manual edit generated JSON only
```

If the project intentionally treats `reference_ranges.json` as source-controlled authority, follow the existing project pattern.

Do not redesign the data pipeline in this TIP.

---

# 9. REQUIRED PROVENANCE

The Uric acid rule must preserve at least repository-equivalent fields for:

```text
analyte_canonical
specimen
sex
age scope
unit raw/display/canonical
range lower
range upper
reference type
source priority tier
source URL
confidence
section
```

Use existing chemistry conventions where applicable.

Do not invent a specimen statement beyond what the approved source/repository contract supports.

If the source specifies serum/plasma or equivalent, encode faithfully.

---

# 10. CATALOG ACTIVATION

Only AFTER reference rule + age + unit tests pass:

```text
Uric acid
HOLD
→
APPROVED
```

Canonical catalog is runtime authority.

Do not modify:

```text
analyte_id
canonical_name
group
aliases
canonical unit
```

unless a proven inconsistency blocks activation.

Expected locked-35 status after activation:

```text
APPROVED = 35
HOLD = 0
```

eGFR remains:

```text
UNSUPPORTED
```

outside locked 35.

---

# 11. LEGACY CONFIG SYNC

If `reference_checker_config.json` still mirrors:

```text
approved_analytes
aliases
hold_analytes
```

update only the compatibility fields required by the DATA-003 sync contract.

Expected:

```text
Uric acid removed from HOLD mirror
Uric acid included in approved mirror
```

Do not make the legacy config authoritative again.

Sync tests must remain strict.

---

# 12. FRONTEND ALIGNMENT

If `Uric acid` exists in manual entry:

change only runtime/support metadata necessary to reflect:

```text
runtimeStatus = APPROVED
```

Keep:

```text
group = renal
canonical identity unchanged
unit contract consistent with runtime
```

Do not redesign UI.

Do not change unrelated visual styling.

Expected manual supported count:

```text
34 → 35
```

for the locked-35 manual analyte set if all 35 are exposed there.

If manual entry intentionally omits an analyte, report the product contract instead of inventing UI.

---

# 13. URIC ACID ACTIVATION TESTS — REQUIRED

Add focused deterministic tests.

## UA-001 — Female LOW

```text
age >=19
sex = F
value below 140 umol/L
→ LOW
```

## UA-002 — Female lower boundary

```text
value exactly 140
→ follow existing RI boundary semantics
```

## UA-003 — Female NORMAL

```text
140 < value < 360
→ NORMAL
```

## UA-004 — Female upper boundary

```text
value exactly 360
→ existing RI boundary semantics
```

## UA-005 — Female HIGH

```text
value > 360
→ HIGH
```

---

## UA-006 — Male LOW

```text
age >=19
sex = M
value below 200
→ LOW
```

## UA-007 — Male lower boundary

```text
value exactly 200
→ existing RI boundary semantics
```

## UA-008 — Male NORMAL

```text
200 < value < 430
→ NORMAL
```

## UA-009 — Male upper boundary

```text
value exactly 430
→ existing RI boundary semantics
```

## UA-010 — Male HIGH

```text
value > 430
→ HIGH
```

---

# 14. AGE TESTS — REQUIRED

## UA-011 — Age 18 fail-safe

```text
age = 18
→ must NOT apply >=19 Uric acid RI
```

Behavior must follow current repository fail-closed contract:

```text
unknown/reference_not_applicable/etc.
```

Use actual runtime contract.

Do not invent a pediatric range.

---

## UA-012 — Age 19

```text
age = 19
→ rule applies
```

## UA-013 — Older adult

```text
age > 19
→ same >=19 rule applies
```

## UA-014 — Missing age

If age is required by the selector:

```text
missing age
→ fail closed
```

Do not assume an adult default unless project contract explicitly does so.

---

# 15. SEX SELECTION TESTS

Verify:

```text
F → female RI only
M → male RI only
```

Unknown/unsupported sex must follow existing deterministic selector policy.

Do not silently choose one sex-specific range.

---

# 16. UNIT TESTS

Required:

## UA-UNIT-001

```text
unit = umol/L
→ accepted
```

## UA-UNIT-002

```text
unit = µmol/L
→ normalize to umol/L
→ value unchanged
→ same classification
```

## UA-UNIT-003

Unsupported unit:

```text
→ fail closed
```

unless an existing verified conversion path explicitly supports it.

No new arbitrary conversion.

---

# 17. ALIAS TESTS

Test:

```text
Uric acid
```

plus existing catalog aliases if present, for example only those actually declared in repository.

Do not add aliases merely because they are common.

Expected:

```text
alias → Uric acid
```

with no collision.

---

# 18. EXPLANATION + QUESTION PATH

Verify existing artifacts resolve after activation:

```text
Uric acid
→ explanation lookup succeeds

Uric acid
→ question template lookup succeeds
```

Do not rewrite explanation or questions unless activation reveals an actual broken ID mapping.

Medical prose changes are out of scope.

---

# 19. CRITICAL FAIL-CLOSED TEST

Explicitly test:

```text
very low/high Uric acid
```

does NOT create an unauthorized critical alert.

Expected:

```text
reference status may be LOW/HIGH
critical status remains inactive/not triggered
```

This test is mandatory.

---

# 20. FINAL LOCKED-35 CATALOG TEST

Assert exact 35 approved analytes.

Do NOT assert only:

```python
len(approved) == 35
```

Assert exact membership of the locked-35 set.

Also assert:

```text
Uric acid = APPROVED
eGFR = UNSUPPORTED
BASO not silently added
MPV not silently added
```

---

# 21. FINAL 35/35 PER-ANALYTE E2E MATRIX

This is the release gate.

For all 35 locked analytes, run a parameterized E2E or closest existing integration path validating at minimum:

```text
canonical identity resolves
runtime status = APPROVED
reference rule resolves
supported canonical unit accepted
deterministic classification executes
explanation artifact resolves
question artifact resolves
```

For analytes with demographic rules:

```text
correct demographic branch selected
```

For BAND/CDL/ONE_SIDED rules:

validate the actual rule family rather than forcing RI semantics.

For critical-enabled analytes:

validate critical behavior separately.

---

# 22. REQUIRED 35-ROW RELEASE MATRIX

Completion report must contain exactly 35 rows:

| # | Analyte | Approved | Ref Rule | Unit | Demographic | Classification E2E | Explanation | Questions | Critical Policy | Result |
|---:|---|---|---|---|---|---|---|---|---|---|

Every row must be:

```text
PASS
```

for release approval.

Do not hide failures in aggregate counts.

---

# 23. BOUNDARY COVERAGE

Final verification must prove boundary semantics for every rule family used by the locked 35.

At minimum cover representatives and all newly risky paths for:

```text
RI
ONE_SIDED_LIMIT
BAND
CDL
```

Uric acid specifically must have both sex-specific boundaries tested.

---

# 24. UNIT / CONVERSION RELEASE REGRESSION

Audit all unit behavior introduced during TIP_DATA_007.

Mandatory regression targets:

```text
HCT
RDW-CV
Total cholesterol
Triglyceride
Uric acid
```

Verify:

## HCT

No silent incorrect percentage/fraction behavior.

## RDW-CV

`%CV -> %` remains label normalization only if implemented that way.

Numeric value unchanged.

## Total cholesterol

mg/dL conversion uses existing conversion authority.

## Triglyceride

mg/dL conversion uses existing conversion authority.

## Uric acid

µmol/L -> umol/L is notation normalization only.

---

# 25. RAW VS COMPARISON VALUE INVARIANT

TIP_DATA_007 introduced/used converted comparison values.

Verify invariant:

```text
raw_value/raw_unit
→ preserved for output/audit

comparison_value/comparison_unit
→ used for deterministic classification
```

No conversion may overwrite the raw patient input invisibly.

Add/retain regression tests for converted lipid paths.

---

# 26. CRITICAL RELEASE VERIFY

Run full critical-detector suite.

Required final policy:

```text
general 35/35 runtime support
!=
35/35 critical support
```

Assert exact authorized active critical analytes according to current project authority.

Do not infer the set from memory.

Read actual current critical-policy data/tests.

Expected:

```text
unauthorized critical rule activations = 0
Uric acid critical rule = inactive
```

---

# 27. RESPONSE QUALITY RELEASE GATE

Run:

```bash
python scripts/run_response_quality_eval.py
```

Required:

```text
125/125 passed
0 failed
```

No eval expectation changes.

No skip/xpass.

No golden-output weakening.

If any regression appears after Uric acid activation:

investigate before release.

---

# 28. ORCHESTRATOR RELEASE GATE

Run:

```bash
python -m pytest tests/orchestrator -q
```

Required:

```text
0 failed
```

Baseline before this TIP:

```text
229 passed
```

If test count increases legitimately because of new tests, report the new total.

---

# 29. DATA RELEASE GATE

Run:

```bash
python -m pytest tests/test_data -q
```

Required:

```text
0 failed
```

Ensure:

```text
reference artifact count reflects 35 analytes
catalog consistency passes
runtime catalog sync passes
frontend/mock catalog alignment passes
```

---

# 30. REFERENCE / SERVICE RELEASE GATE

Run all relevant suites covering:

```text
analyte catalog
reference repository
reference checker
runtime catalog alignment
indicator catalog
analyte sections
unit normalization/conversion
question generator
critical detector
```

Required:

```text
0 task-related failures
```

Optional dependency failures must be clearly separated and proven unrelated if any exist.

---

# 31. FRONTEND RELEASE GATE

Run from frontend:

```bash
npm test
npm run lint
npm run build
```

Required:

```text
tests: PASS
lint: 0 errors
build: PASS
```

Existing non-blocking warnings may be reported but not hidden.

Verify Uric acid appears with supported status where appropriate.

Do not perform visual redesign.

---

# 32. STATIC QUALITY

Run Ruff on all changed Python files:

```bash
python -m ruff check <changed-python-files>
```

Required:

```text
All checks passed
```

Also:

```bash
git diff --check
```

Required:

```text
PASS
```

---

# 33. NO MEDICAL REGRESSION

Compare before/after medical deterministic artifacts.

Expected change:

```text
ONLY:
Uric acid approved reference interval rules authorized in this TIP
```

Not allowed:

```text
unrelated range value changes
critical threshold changes
clinical band changes
existing demographic rule changes
existing unit-conversion factor changes
```

Completion report must list any numeric medical diff explicitly.

---

# 34. SOURCE TRACEABILITY VERIFY

For Uric acid, report exact provenance:

```text
organization
document/page
URL
population
sex
age scope
unit
lower
upper
source tier
confidence
repository rule IDs
```

The source URL alone is not sufficient.

---

# 35. RELEASE CLAIM

Only if every mandatory gate passes may the project claim:

```text
VMEC-05 supports 35/35 locked analytes at runtime.
```

This claim means:

```text
35/35 canonical analytes resolve
35/35 have deterministic reference behavior
35/35 runtime-approved
35/35 explanation/question paths resolve
unit/demographic contracts verified
critical policy remains fail-closed
full release gates pass
```

It does NOT mean:

```text
35/35 have active critical thresholds
35/35 cover every possible hospital unit
35/35 cover pediatric populations
```

Do not overclaim.

---

# 36. STOP CONDITIONS

Do NOT release if any of these occur:

```text
Uric acid exact >=19 age scope cannot be represented safely
Uric acid source/rule mismatch
Uric acid female/male selector ambiguity
unit normalization changes numeric value
unauthorized critical alert appears
any locked-35 analyte no longer resolves
response quality <125/125
orchestrator has task-related failure
frontend build fails
data consistency fails
medical diff affects unrelated analytes
```

Status must be:

```text
PARTIAL / BLOCKED
```

with exact blocker.

Do not force `RELEASE_READY`.

---

# 37. GIT / COMMIT DISCIPLINE

There are known unrelated dirty/presentation changes from prior work.

Do NOT:

```bash
git add .
```

At the end, list exact TIP_DATA_008 files.

Stage only files owned by this TIP if asked to prepare commit.

Before commit:

```bash
git diff --check
git diff --stat
git diff

git diff --cached --check
git diff --cached --stat
git diff --cached
```

Unrelated files must not enter the release commit.

---

# 38. EXPECTED FILE FAMILIES

Potentially expected:

```text
authoritative reference source / reference_ranges artifact
data/reference/analyte_catalog.json
data/reference/reference_checker_config.json

frontend/src/lib/manualEntry.mjs

age-scope selector code ONLY if exact >=19 support is required
focused data/service/agent/frontend tests
```

Do not assume every file must change.

Only modify what the actual implementation requires.

---

# 39. HANDOVER PACKAGE

At completion, prepare a handover report suitable for the Project Lead.

Do not merely write:

```text
35/35 PASS
```

The handover must provide enough evidence for independent review.

Required sections follow below.

---

# 40. COMPLETION / HANDOVER REPORT FORMAT

Return exactly:

# COMPLETION REPORT — TIP_DATA_008 FINAL 35/35 RELEASE VERIFY

## STATUS

One of:

```text
DONE
PARTIAL
BLOCKED
```

---

## FINAL RELEASE VERDICT

One of:

```text
RELEASE_READY_35_35
NOT_RELEASE_READY
```

---

## CAPABILITY PROGRESSION

```text
BEFORE TIP_DATA_008:
34/35 APPROVED

AFTER URIC ACID ACTIVATION:
__/35 APPROVED

FINAL VERIFIED:
__/35
```

Expected success:

```text
35/35
```

---

## URIC ACID AUTHORITY

```text
Organization:
Document/Page:
URL:
Reviewed/effective date if available:
Reference type:
Population:
Unit:
Female RI:
Male RI:
Source tier:
Confidence:
```

---

## URIC ACID IMPLEMENTED RULES

| Rule ID | Sex | Age Scope | Lower | Upper | Unit | Type |
|---|---|---|---:|---:|---|---|

---

## AGE-SCOPE IMPLEMENTATION

```text
source requirement:
runtime representation:
age 18 behavior:
age 19 behavior:
older adult behavior:
missing age behavior:
existing analytes affected:
```

---

## URIC ACID TEST RESULTS

```text
female low:
female lower boundary:
female normal:
female upper boundary:
female high:

male low:
male lower boundary:
male normal:
male upper boundary:
male high:

age 18:
age 19:
missing age:

umol/L:
µmol/L:
unsupported unit:

alias:
explanation:
questions:
critical fail-closed:
```

All expected:

```text
PASS
```

---

## APPROVED EXACT SET

List all 35 locked analytes explicitly.

Do not provide count only.

---

## 35-ANALYTE E2E RELEASE MATRIX

Exactly 35 rows:

| # | Analyte | Approved | Ref Rule | Unit | Demographic | Classification E2E | Explanation | Questions | Critical Policy | Result |
|---:|---|---|---|---|---|---|---|---|---|---|

Expected:

```text
35 PASS
0 FAIL
```

---

## RULE-FAMILY COVERAGE

```text
RI:
ONE_SIDED_LIMIT:
BAND:
CDL:
missing:
```

Expected:

```text
missing = 0
```

for locked 35.

---

## UNIT / CONVERSION RELEASE AUDIT

| Analyte | Input Unit | Comparison Unit | Mechanism | Raw Preserved | Result |
|---|---|---|---|---|---|

Must include:

```text
HCT
RDW-CV
Total cholesterol
Triglyceride
Uric acid
```

---

## CRITICAL POLICY VERIFY

```text
authorized active critical analytes:
new Uric acid critical rule:
unauthorized critical activations:
critical suite result:
```

Expected:

```text
new Uric acid critical rule = NO
unauthorized critical activations = 0
```

---

## RESPONSE QUALITY

```text
command:
result:
```

Expected:

```text
125/125 passed
0 failed
```

---

## ORCHESTRATOR

```text
command:
passed:
failed:
```

Expected:

```text
failed = 0
```

---

## DATA TESTS

```text
command:
passed:
failed:
```

Expected:

```text
failed = 0
```

---

## REFERENCE / SERVICE / AGENT TESTS

List commands and exact totals.

Expected:

```text
0 task-related failures
```

---

## FRONTEND

```text
npm test:
npm run lint:
npm run build:
```

Expected:

```text
PASS
0 lint errors
PASS
```

---

## STATIC QUALITY

```text
ruff:
git diff --check:
```

Expected:

```text
PASS
PASS
```

---

## MEDICAL DATA CHANGES

List exact authorized change.

Expected semantic summary:

```text
Added only Uric acid reference interval rules from the approved Gloucestershire Hospitals NHS authority.

No unrelated reference ranges changed.
No critical thresholds changed.
No clinical bands changed.
No diagnosis/treatment rules changed.
```

---

## RUNTIME CAPABILITY CHANGES

Expected:

```text
Uric acid: HOLD → APPROVED
34/35 → 35/35
No other capability expansion.
```

---

## FILES CHANGED

For every file:

```text
path
purpose
```

---

## CONFLICT RISK

```text
CONFLICT_RISK_FILES:
UNRELATED_DIRTY_FILES:
UNRELATED_FILES_INCLUDED_IN_TIP_DIFF:
```

Expected last field:

```text
NONE
```

---

## KNOWN WARNINGS / NON-BLOCKING ISSUES

List honestly.

Do not mix them with release blockers.

---

## DEVIATIONS

Expected:

```text
NONE
```

or exact justified deviations.

---

## REMAINING OUT-OF-SCOPE ITEMS

Explicitly state:

```text
eGFR = UNSUPPORTED / outside locked 35
BASO = outside locked 35
MPV = outside locked 35
```

Include other real deferred items if any.

---

## RELEASE CLAIM

If and only if all gates pass, state exactly:

```text
VMEC-05 is verified RELEASE_READY for all 35/35 locked analytes under the currently declared V1 contracts, populations, units, reference authorities, and critical-value policy.
```

Do not claim broader coverage than verified.

---

## FINAL SAFETY STATEMENT

Explicitly state:

```text
No analyte was approved without deterministic reference evidence.
Uric acid uses only the human-approved reference authority.
No pediatric Uric acid range was invented.
No unauthorized critical rule was activated.
No unit conversion was invented.
Raw patient values remain traceable where comparison-value conversion is used.
Response quality remains 125/125.
All release-gate failures are zero, or the build is marked NOT_RELEASE_READY.
```

---

# 41. FINAL RULE

This TIP is complete only when one of two outcomes is honestly produced.

## Success

```text
RELEASE_READY_35_35
```

with full evidence.

## Failure / blocker

```text
NOT_RELEASE_READY
```

with exact evidence and no attempt to bypass the blocker.

The objective is not merely to make `runtime_status = APPROVED`.

The objective is to prove that **35/35 analytes are safe, deterministic, traceable, regression-tested, and ready for handover**.
