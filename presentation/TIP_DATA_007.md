# VMEC-05 — TIP_DATA_007
# FULL RUNTIME EXPANSION — 9/35 → MAXIMUM SAFE 34/35 OR 35/35

## ROLE

Bạn là AI Coding Agent / BUILDER.

Đây là **FULL EXPANSION TIP**.

Không chia thành nhiều TIP activation nhỏ nữa.

Mục tiêu:

> Mở rộng VMEC-05 từ 9/35 runtime-approved analytes lên số lượng tối đa có thể đạt được an toàn trong một lượt triển khai.

Target:

```text
9/35
↓
30/35 via READY_WITH_TEST_GAP activation
↓
up to 34/35 via unit remediation
↓
35/35 ONLY IF Uric acid passes hard medical-authority gate
```

---

# 0. TRUSTED BASELINE

Các TIP trước đã hoàn thành:

```text
TIP_DATA_001 ✅ consistency guardrails
TIP_DATA_002 ✅ canonical analyte catalog
TIP_DATA_003 ✅ backend/runtime catalog authority
TIP_DATA_004 ✅ frontend/mock alignment
TIP_DATA_005 ✅ response quality remediation
TIP_DATA_006 ✅ 35/35 readiness audit
```

Quality baseline:

```text
Response quality: 125/125 PASS
Orchestrator: 229/229 PASS
Data suite: green
Catalog/runtime tests: green
```

Current runtime:

```text
APPROVED = 9/35
```

Exact current approved set:

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

---

# 1. TIP_DATA_006 READINESS RESULT — AUTHORITATIVE INPUT

## READY_WITH_TEST_GAP — 21 ANALYTES

```text
MCV
MCH
MCHC
PLT
Neutrophils %
Neutrophils abs
Lymphocytes %
Lymphocytes abs
Monocytes %
Monocytes abs
Eosinophils %
Eosinophils abs
Sodium
Chloride
Urea
AST
ALT
GGT
Total bilirubin
Total protein
Albumin
```

These may be activated if activation-specific tests pass.

---

## NEEDS_UNIT_FIX — 4 ANALYTES

```text
HCT
RDW-CV
Total cholesterol
Triglyceride
```

Known gaps:

```text
HCT:
manual/input % vs canonical/reference L/L

RDW-CV:
%CV vs canonical %

Total cholesterol:
mg/dL input/mock vs mmol/L reference

Triglyceride:
mg/dL input/mock vs mmol/L reference
```

These require explicit runtime unit-contract resolution before activation.

---

## HARD HOLD — 1 ANALYTE

```text
Uric acid
```

Known state:

```text
runtime_status = HOLD
reference rule = MISSING
reason = NO_APPROVED_RI_AUTHORITY
```

This analyte is governed by the HARD SAFETY GATE defined later.

---

# 2. FINAL OBJECTIVE

Attempt to reach the maximum safe capability:

```text
MINIMUM SUCCESS:
30/35 APPROVED

TARGET SUCCESS:
34/35 APPROVED

FULL SUCCESS:
35/35 APPROVED
ONLY if Uric acid authority gate is legitimately satisfied
```

Important:

```text
34/35 with Uric acid HOLD
IS A VALID DONE RESULT.
```

Do NOT treat 34/35 as failure if the only remaining blocker is Uric acid medical authority.

---

# 3. ABSOLUTE SAFETY RULE

Never optimize for the number `35`.

Optimize for:

```text
evidence-backed runtime support
+
deterministic behavior
+
test coverage
+
no medical fabrication
```

Forbidden:

```text
inventing reference ranges
guessing medical units
adding arbitrary conversion factors
choosing a random hospital RI
using RAG text as numeric authority
activating unsupported analytes just because data exists
weakening tests
changing eval expected results
```

---

# 4. HARD SAFETY GATE — URIC ACID

This is the most important rule of the entire TIP.

## Uric acid may move:

```text
HOLD
→
APPROVED
```

ONLY IF the repository already contains or the human has explicitly supplied:

```text
an approved reference interval authority
+
exact reference rule
+
unit contract
+
demographic scope if applicable
+
traceable evidence
```

### NOT ACCEPTABLE

Do NOT:

```text
search the web and choose a range yourself
use Vinmec/Mayo/Long Chau/etc. merely because a range exists
infer range from explanation text
copy from another analyte
use LLM memory
invent lower/upper values
```

### If authority is absent

Required final state:

```text
Uric acid = HOLD
APPROVED = 34/35 maximum
```

Report:

```text
URIC_ACID_GATE = BLOCKED_BY_MEDICAL_AUTHORITY
```

This is a valid successful completion.

---

# 5. CRITICAL POLICY REMAINS SEPARATE

35/35 runtime support does NOT require 35/35 active critical rules.

Existing active critical policy remains governed by current authority.

Do not activate new critical rules merely because analyte runtime support becomes APPROVED.

Known active critical analytes from audit:

```text
Sodium
Potassium
Fasting plasma glucose
Total bilirubin
```

If repository current state differs, use actual code/data as authority.

Expected:

```text
NEW_UNAUTHORIZED_CRITICAL_RULES = 0
```

---

# 6. PRE-FLIGHT

Run:

```bash
git status --short --untracked-files=all
git diff --stat
git diff
git log --oneline -15
```

Identify unrelated existing changes.

Do NOT use:

```bash
git add .
git reset --hard
git clean -fd
git checkout .
git stash
```

Do not overwrite teammate work.

Before modifying each file:

```bash
git status --short <file>
git diff -- <file>
```

If required file has unrelated changes:

```text
CONFLICT_RISK
```

Preserve them.

---

# 7. PHASE A — ACTIVATE ALL 21 READY_WITH_TEST_GAP ANALYTES

Activate exactly:

```text
MCV
MCH
MCHC
PLT

Neutrophils %
Neutrophils abs
Lymphocytes %
Lymphocytes abs
Monocytes %
Monocytes abs
Eosinophils %
Eosinophils abs

Sodium
Chloride
Urea

AST
ALT
GGT
Total bilirubin
Total protein
Albumin
```

Do not activate the 4 unit-blocked analytes yet.

Do not activate Uric acid yet.

---

# 8. PHASE A — ACTIVATION AUTHORITY

Canonical runtime status authority:

```text
data/reference/analyte_catalog.json
```

For Phase A analytes:

```text
UNSUPPORTED
→
APPROVED
```

Synchronize legacy compatibility mirrors only where required by existing DATA-003 contract.

Do not make legacy config authoritative again.

---

# 9. PHASE A — ACTIVATION TEST MATRIX

For every newly approved analyte, verify applicable deterministic behavior.

For standard RI analytes:

```text
LOW
LOWER_BOUNDARY
NORMAL
UPPER_BOUNDARY
HIGH
```

For ONE_SIDED_LIMIT:

test actual supported boundary semantics.

For BAND/CDL:

test every existing defined clinical band required by current rule.

Do not force LOW/NORMAL/HIGH semantics onto rule types that do not use them.

---

# 10. DEMOGRAPHIC RULES

If analyte has:

```text
sex-specific
age-specific
demographic-specific
```

reference selection, activation-specific tests must cover those branches.

Do not assume all 21 are adult/all-sex.

Derive from actual reference artifact.

Required:

```text
correct demographic rule selected
+
wrong demographic rule not accidentally selected
+
fail-closed behavior preserved where demographic input insufficient
```

---

# 11. ALIAS COVERAGE

For every new analyte:

test canonical identity.

If aliases exist:

test representative existing aliases.

Do not invent new aliases solely for activation.

Alias mappings must remain deterministic:

```text
alias collisions = 0
```

---

# 12. UNIT COVERAGE — PHASE A

The 21 Phase-A analytes were audited as having valid unit contracts.

Verify that remains true.

Allowed:

```text
DIRECT
NORMALIZATION_ONLY
existing verified conversion
```

If an analyte unexpectedly needs new conversion:

remove that analyte from activation and classify:

```text
READINESS_AUDIT_MISMATCH
```

Do not improvise.

---

# 13. SODIUM

Sodium already has an active critical rule according to readiness audit.

When activating Sodium:

verify both:

```text
general reference classification
+
existing critical detector behavior
```

Do not modify critical thresholds.

Add regression coverage proving activation does not alter critical semantics.

---

# 14. TOTAL BILIRUBIN

Total bilirubin uses:

```text
ONE_SIDED_LIMIT
+
existing critical conversion path
```

Verify both:

```text
reference classification
critical detection
unit conversion
```

No threshold/conversion modifications unless current implementation is provably broken.

If current critical conversion passes existing tests, preserve it.

---

# 15. PHASE A CHECKPOINT

After 21 activation:

expected:

```text
APPROVED = 30/35
```

Run:

```text
catalog contract tests
runtime catalog tests
reference checker tests
critical detector tests
question generator tests
data tests
frontend metadata tests
```

Then:

```bash
python scripts/run_response_quality_eval.py
python -m pytest tests/orchestrator -q
```

Required:

```text
Response quality = 125/125
Orchestrator = all pass
```

If Phase A causes regression:

STOP further expansion.

Fix only activation-related regression.

Do not continue to Phase B while quality gate is red.

---

# 16. PHASE B — UNIT REMEDIATION

Only after Phase A is green.

Candidates:

```text
HCT
RDW-CV
Total cholesterol
Triglyceride
```

Goal:

```text
30/35
→
up to 34/35
```

Each analyte must pass its own unit gate independently.

Failure of one must not block safe activation of the others.

---

# 17. HCT UNIT GATE

Known:

```text
reference/canonical unit = L/L
manual/input unit = %
no runtime % → L/L conversion currently confirmed
```

Investigate existing repository only.

Acceptable solutions:

### Option A — Canonical input only

If product/runtime contract can safely require:

```text
L/L
```

for supported runtime input:

align manual/input metadata to canonical unit without changing numeric reference values.

### Option B — Existing deterministic conversion

If repository already contains a verified:

```text
% ↔ L/L
```

conversion contract:

wire it through existing conversion architecture with tests.

### NOT ALLOWED

Do not invent conversion behavior solely from general medical knowledge unless the conversion relationship is already explicitly approved/project-defined.

If no valid existing contract:

```text
HCT remains UNSUPPORTED
```

Report blocker.

---

# 18. RDW-CV UNIT GATE

Known:

```text
mock/common unit = %CV
canonical/reference unit = %
```

Determine whether `%CV` is:

```text
notation alias
```

or a genuinely unsupported unit.

If repository semantics demonstrate that `%CV` and `%` are equivalent notation for RDW-CV:

implement normalization as a unit-label normalization, not numeric conversion.

Required tests:

```text
%CV input
→ normalized canonical unit
→ numeric value unchanged
```

If evidence is insufficient:

```text
RDW-CV remains UNSUPPORTED
```

Do not guess.

---

# 19. LIPID UNIT GATE

Candidates:

```text
Total cholesterol
Triglyceride
```

Known:

```text
input/mock = mg/dL
reference = mmol/L
existing measurement conversion module contains lipid conversions
but ReferenceRepository did not accept them during audit
```

This is the strongest Phase-B remediation candidate.

Investigate:

```text
measurement_conversion.py
reference_repository.py
unit normalization/conversion flow
existing HDL-C/LDL-C behavior
```

Preferred architecture:

```text
input
→ existing measurement conversion service
→ canonical mmol/L
→ deterministic reference rule
```

Do NOT duplicate conversion formulas inside repository/checker.

Reuse existing conversion authority.

Add tests for:

```text
mg/dL → canonical mmol/L
boundary preservation
rounding precision
LOW/NORMAL/HIGH or BAND result
```

Do not alter medical band thresholds.

---

# 20. LIPID CROSS-CHECK

If HDL-C/LDL-C already have working mg/dL conversion behavior:

reuse exactly the same conversion architecture where appropriate.

Do not create a separate TC/TG-only conversion implementation.

If conversion factor differs by analyte, use existing analyte-specific conversion contract.

---

# 21. PHASE B ACTIVATION RULE

Each analyte moves:

```text
UNSUPPORTED
→
APPROVED
```

only AFTER:

```text
unit gate passes
+
reference behavior passes
+
alias passes
+
activation tests pass
+
prior regression remains green
```

Do not set status APPROVED first and then make tests fit.

---

# 22. PHASE B CHECKPOINT

After unit remediation:

report exact result:

```text
HCT: ACTIVATED / BLOCKED
RDW-CV: ACTIVATED / BLOCKED
Total cholesterol: ACTIVATED / BLOCKED
Triglyceride: ACTIVATED / BLOCKED
```

Possible safe outcomes include:

```text
31/35
32/35
33/35
34/35
```

Do not force 34 if evidence blocks one.

However based on TIP_DATA_006, expected target is:

```text
34/35
```

if existing unit evidence supports all four.

---

# 23. PHASE C — URIC ACID HARD GATE

After Phases A/B are fully green, inspect Uric acid.

Current:

```text
HOLD
no approved reference rule
NO_APPROVED_RI_AUTHORITY
```

Search repository only for already-approved project authority/evidence.

Check:

```text
reference source files
project medical decisions
existing curated authority manifests
approved human decision records
```

Do NOT perform an autonomous external medical-source selection.

---

# 24. URIC ACID DECISION

## CASE A — Approved authority already exists

Only if there is explicit project-approved evidence:

Implement the smallest required reference artifact.

Then test:

```text
reference rule
unit
boundary semantics
demographic selection
alias
question
explanation
fail-safe
```

Only then:

```text
HOLD → APPROVED
```

Result:

```text
35/35
```

---

## CASE B — No approved authority exists

Do nothing to its medical data.

Keep:

```text
Uric acid = HOLD
```

Final:

```text
34/35
```

Report:

```text
URIC_ACID_GATE:
BLOCKED_BY_MEDICAL_AUTHORITY
```

This counts as successful completion.

---

# 25. FRONTEND ALIGNMENT

Frontend adapter must reflect runtime status after each safe activation.

Do NOT redesign UI.

Do not change taxonomy.

Expected supported count follows runtime exact approved count.

For non-approved remaining analytes:

continue showing non-approved status.

Uric acid remains visibly HOLD if not activated.

---

# 26. QUESTION / EXPLANATION PATH

For every newly approved analyte verify:

```text
question template resolves
explanation lookup resolves
```

Do not rewrite medical prose.

No analyte may be APPROVED if basic runtime explanation/question path breaks due missing artifact.

---

# 27. CRITICAL DETECTOR REGRESSION

Run full critical suite.

Important:

New runtime approval must not imply new critical activation.

Expected:

```text
unauthorized critical-rule activations = 0
```

Existing critical analytes must behave identically.

---

# 28. EXISTING 9 MUST NOT REGRESS

The original approved baseline remains protected:

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

Run existing regression suites.

Do not modify their reference semantics as collateral work.

---

# 29. RESPONSE QUALITY GATE

After Phase A:

```text
125/125 required
```

After Phase B:

```text
125/125 required
```

After Phase C if Uric acid activated:

```text
125/125 required
```

Do not weaken evaluation.

If score decreases:

identify newly activated analyte/path causing regression.

Fix only the generalizable expansion regression.

---

# 30. ORCHESTRATOR GATE

Run:

```bash
python -m pytest tests/orchestrator -q
```

Required:

```text
0 failed
```

Do not treat previous historical failures as acceptable now because TIP_DATA_005 already brought suite to full pass.

---

# 31. DATA / SERVICE TEST GATE

Run at minimum:

```bash
python -m pytest tests/test_data -q
```

and relevant:

```text
analyte catalog
runtime catalog alignment
reference repository
reference checker
critical detector
question generator
indicator catalog
frontend/manual metadata tests
```

Run Ruff on changed Python files.

Frontend changes:

```bash
npm test
npm run lint
```

---

# 32. FULL APPROVED SET ASSERTION

Do not merely assert count.

At every checkpoint assert exact membership.

### After Phase A expected 30

Original 9 + 21 audit-ready analytes.

### After Phase B

Original 30 + only unit-remediated analytes that passed.

### After Phase C

Add Uric acid only if hard gate passes.

---

# 33. NO EXTRA ANALYTES

These remain out of denominator/scope unless explicit separate human decision exists:

```text
eGFR
BASO
MPV
```

Do not use them to claim >35 coverage.

Do not add them to locked 35.

---

# 34. CONFLICT MINIMIZATION

This is a larger TIP, so keep changes disciplined.

Do not perform:

```text
repository cleanup
JSON sorting
folder restructuring
renaming unrelated tests
frontend visual redesign
RAG refactor
orchestrator refactor
```

Use parameterized tests to limit churn.

Prefer extending existing activation test infrastructure rather than creating dozens of files.

---

# 35. EXPECTED FILE FAMILIES

Potentially allowed:

```text
data/reference/analyte_catalog.json
data/reference/reference_checker_config.json

src/services/analyte_catalog.py
src/services/reference_repository.py
existing measurement/unit conversion service if Phase B requires wiring

frontend/src/lib/manualEntry.mjs

focused data/service/frontend tests
```

Only modify files proven necessary.

---

# 36. DO NOT MODIFY

Unless directly necessary for a proven expansion regression:

```text
src/orchestrator/**
RAG/vector code
auth/history/trend architecture
database schema
critical threshold values
explanation content
question wording
```

---

# 37. INTERNAL CHECKPOINTS ARE MANDATORY

Do NOT implement all phases and test only at the end.

Required sequence:

```text
PHASE A implementation
→ targeted tests
→ full relevant regression
→ 125/125
→ orchestrator green

THEN

PHASE B implementation
→ targeted unit/reference tests
→ full regression
→ 125/125
→ orchestrator green

THEN

PHASE C Uric acid gate
→ activate only if authority passes
→ full regression
```

If a phase fails:

do not continue blindly.

---

# 38. ACCEPTANCE CRITERIA

## AC-01

All 21 `READY_WITH_TEST_GAP` analytes are evaluated for activation.

## AC-02

Any activated analyte has activation-specific deterministic tests.

## AC-03

Phase A target:

```text
30/35
```

unless audit mismatch is proven.

## AC-04

HCT/RDW-CV/TC/TG each receive an independent unit-gate decision.

## AC-05

No unit conversion is invented.

## AC-06

Existing conversion services are reused where applicable.

## AC-07

Uric acid cannot leave HOLD without approved reference authority.

## AC-08

34/35 with Uric acid HOLD is an acceptable DONE state.

## AC-09

35/35 is accepted only if Uric acid hard gate passes.

## AC-10

No unauthorized critical rules activated.

## AC-11

Original 9 analytes do not regress.

## AC-12

Response quality remains:

```text
125/125
```

## AC-13

Orchestrator remains fully green.

## AC-14

Medical numeric values remain unchanged except a Uric acid reference artifact ONLY if an already-approved authority explicitly permits it.

## AC-15

No eval expectations weakened.

---

# 39. STOP CONDITIONS

Stop the affected analyte/phase instead of fabricating if:

```text
missing reference authority
unknown conversion
ambiguous unit semantics
alias collision
demographic rule conflict
reference rule mismatch
new medical threshold required
critical authority absent
```

One blocked analyte does not necessarily block the other safe analytes.

Use per-analyte fail-safe.

---

# 40. COMPLETION REPORT

Return exactly:

# COMPLETION REPORT — TIP_DATA_007 FULL EXPANSION

## STATUS

```text
DONE / PARTIAL / BLOCKED
```

## CAPABILITY PROGRESSION

```text
START: 9/35

AFTER PHASE A:
__/35

AFTER PHASE B:
__/35

AFTER PHASE C:
__/35

FINAL:
__/35
```

---

## FINAL VERDICT

One of:

```text
FULL_35_35
```

or

```text
SAFE_34_35_URIC_ACID_HOLD
```

or

```text
PARTIAL_EXPANSION
```

---

## PHASE A — 21 ANALYTES

For each:

| Analyte | Before | After | Ref Rule | Unit | Activation Tests | Result |

---

## PHASE B — UNIT REMEDIATION

| Analyte | Original Gap | Evidence Used | Fix | Tests | Activated? |

Cover:

```text
HCT
RDW-CV
Total cholesterol
Triglyceride
```

---

## PHASE C — URIC ACID HARD GATE

Report:

```text
approved authority found:
exact authority:
reference artifact found:
new medical rule authored:
runtime status:
```

If no authority:

```text
approved authority found: NO
new medical rule authored: NO
runtime status: HOLD
gate result: BLOCKED_BY_MEDICAL_AUTHORITY
```

---

## APPROVED EXACT SET

List every final approved analyte.

Do not provide count only.

---

## REMAINING NON-APPROVED LOCKED-35 ANALYTES

List exact analytes + blocker.

Expected if 34/35:

```text
Uric acid — HOLD / NO_APPROVED_RI_AUTHORITY
```

---

## REFERENCE RULE COVERAGE

```text
total locked 35:
rules available:
missing:
```

---

## UNIT CONTRACT RESULT

```text
direct:
normalization:
conversion:
blocked:
```

---

## CRITICAL POLICY

```text
active critical analytes:
new authorized critical rules:
new unauthorized critical rules:
```

Expected last value:

```text
0
```

---

## TEST COVERAGE ADDED

Summarize:

```text
activation tests:
boundary tests:
unit tests:
alias tests:
demographic tests:
critical regressions:
```

---

## TEST RESULTS

```text
data:
catalog/runtime:
reference checker:
critical detector:
question generator:
frontend:
response quality:
orchestrator:
ruff:
git diff --check:
```

---

## RESPONSE QUALITY

Expected:

```text
125/125
```

---

## ORCHESTRATOR

Expected:

```text
0 failed
```

---

## MEDICAL DATA CHANGES

Normally:

```text
NONE
```

If Uric acid legitimately activated:

list only the explicitly authorized reference artifact change and its authority.

---

## UNIT CONVERSION CHANGES

List exact changes.

Must identify whether each was:

```text
existing conversion wired
unit-label normalization
none
```

No invented conversions.

---

## FRONTEND ALIGNMENT

```text
supported manual entries before:
supported manual entries after:
HOLD:
unsupported:
status mismatches:
```

---

## FILES CHANGED

Exact file + purpose.

---

## CONFLICT RISK

```text
CONFLICT_RISK_FILES:
UNRELATED_FILES_TOUCHED:
```

---

## DEVIATIONS

---

## ISSUES DISCOVERED

Do not fix unrelated issues.

---

## FINAL SAFETY STATEMENT

Explicitly state:

```text
No analyte was approved without deterministic reference evidence.
No critical rule was activated without authority.
No unit conversion was invented.
Uric acid remained HOLD unless its hard authority gate passed.
```

---

# FINAL RULE

The goal is maximum safe coverage, not an impressive number.

Preferred outcomes:

```text
35/35
if every gate legitimately passes
```

otherwise:

```text
34/35
with Uric acid HOLD
```

is the correct and successful safety-preserving result.

Never manufacture the 35th analyte just to report 35/35.