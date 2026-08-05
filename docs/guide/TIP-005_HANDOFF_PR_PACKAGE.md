# VIBECODE KIT V6.0 — TIP-005

## ROLE

You are the **BUILDER / THỢ THI CÔNG**.

TIP-004B has been conditionally accepted by the Contractor.

You are authorized to execute only:

**TIP-005 — Close TIP-004B, Create V2 Handoff, Delivery Manifest, and PR Package**

This is primarily a verification and documentation TIP.

Do not modify production behavior.

Do not rerun the live RAGAS baseline.

Do not call any external API.

---

# TIP-005: V2 HANDOFF AND PR PACKAGE

## HEADER

- **TIP-ID:** TIP-005
- **Project:** P-056 Release V2
- **Owner scope:** Tuấn — Data & AI Quality
- **Module:** Handoff / Pull Request Package
- **Depends on:**
  - TIP-001 ACCEPTED
  - TIP-002A ACCEPTED
  - TIP-002B ACCEPTED
  - TIP-003 ACCEPTED
  - TIP-004A ACCEPTED
  - TIP-004B CONDITIONALLY ACCEPTED
- **Priority:** P0
- **Repository:** `F:\VIN_AI_PROJECT\P-056`
- **Branch:** `feature/TQT-reference-ragas`
- **Current HEAD expected before TIP-004B commit:**
  `01205af4aade3440b04f008762369d6d69873a77`
- **Mode:**
  - TIP-004B close-out
  - documentation
  - delivery evidence
- **Live API calls allowed:** NO

---

## CONTRACTOR DECISION

TIP-004B output is accepted subject to a mandatory close-out verification.

The following deviation is accepted and must be documented:

```text
DEV-004B-01:
The one-case metric smoke command was run twice.
The first attempt failed with HTTP 429 RESOURCE_EXHAUSTED.
The second succeeded.
The full 12-case baseline was run exactly once.
No score tuning or credential leak occurred.
```

Do not hide or rewrite this deviation.

Do not rerun:

- provider probe;
- smoke metric;
- full baseline;
- any RAGAS live metric;
- any paid API request.

---

# PHASE 0 — CLOSE TIP-004B

This phase must finish before writing TIP-005 handoff documents.

## 0.1 Inspect working tree

Run:

```powershell
cd F:\VIN_AI_PROJECT\P-056

git status --short
git diff --name-only
git diff --check
git branch --show-current
git rev-parse HEAD
```

Expected authorized TIP-004B candidate files:

```text
eval/ragas_compat.py
eval/run_ragas.py
tests/test_eval/test_ragas_runner.py
tests/test_eval/test_ragas_live_runner.py
eval/results/ragas_v2_baseline.json
eval/results/ragas_v2_baseline.csv
eval/results/report.md
```

The scaffold report may also appear only if it received the previously authorized baseline status/link:

```text
docs/version-handoff/TIP-004A_RAGAS_SCAFFOLD_REPORT.md
```

If any unrelated file appears, return `BLOCKED`.

Do not use:

```text
git reset
git restore
git checkout
git clean
git stash
```

---

## 0.2 Validate result artifacts offline

Run a deterministic Python validation script against:

```text
eval/results/ragas_v2_baseline.json
eval/results/ragas_v2_baseline.csv
eval/results/report.md
```

Verify at minimum:

```text
run_id = RAGAS-V2-BASELINE-001
provider = google
model = gemini-2.5-flash
transport_adapter = google_openai_compatible
ragas_version = 0.4.3
dataset sha256 =
3f1cb84cebde5a5a47fca5eafca0a0276ebe6c04665fd9bb0531fe92ea24da2f
total cases = 12
numeric metric cases = 11
not applicable cases = 1
failed cases = 0
```

Verify every numeric metric:

```text
finite
0.0 <= score <= 1.0
```

Verify:

```text
custom_hallucination_proxy = 1 - faithfulness
```

for every numeric Faithfulness value.

Verify case:

```text
RAGAS-V2-012
```

has null metric values and:

```text
metric_status = not_applicable
```

Do not alter scores.

---

## 0.3 Recalculate aggregate consistency

Recalculate aggregates from per-case JSON and compare them with the stored summary/report.

Expected report values:

```text
Faithfulness:
  count = 11
  mean = 0.909091
  median = 1.000000
  min = 0.500000
  max = 1.000000
  std dev = 0.192847

Context Precision:
  count = 11
  mean = 0.954545
  median = 1.000000
  min = 0.500000
  max = 1.000000
  std dev = 0.143740

Custom hallucination proxy:
  count = 11
  mean = 0.090909
  median = 0.000000
  min = 0.000000
  max = 0.500000
  std dev = 0.192847
```

Allow normal formatting tolerance, for example:

```text
absolute difference <= 0.000001
```

If stored aggregates do not match recalculation, return `BLOCKED`.

Do not rerun RAGAS.

---

## 0.4 Mandatory post-live regression

Run:

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest `
  tests `
  -q -rxX -p no:cacheprovider `
  --ignore=tests/test_embed.py
```

Run:

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m compileall -q src eval tests
```

Run:

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -m pip check
```

Required:

```text
failed = 0
xfailed = 0
xpassed = 0
compile exit code = 0
pip check = No broken requirements found
```

Record exact pass count and warnings.

If the post-live test suite fails:

- do not commit;
- do not begin handoff documentation;
- return `BLOCKED`.

---

## 0.5 Credential and environment integrity

Scan candidate artifacts without displaying matched content.

Check patterns:

```text
AIza[0-9A-Za-z_-]{20,}
sk-[0-9A-Za-z_-]{20,}
Authorization\s*:
Bearer\s+[0-9A-Za-z._-]{10,}
```

Candidate files:

```text
eval/ragas_compat.py
eval/run_ragas.py
tests/test_eval/test_ragas_runner.py
tests/test_eval/test_ragas_live_runner.py
eval/results/ragas_v2_baseline.json
eval/results/ragas_v2_baseline.csv
eval/results/report.md
```

Required:

```text
credential-like matches = 0
authorization-header matches = 0
```

Verify:

```powershell
git check-ignore .env
git ls-files .env
git status --short
```

Required:

```text
.env ignored = YES
.env tracked = NO
.env absent from git status
```

---

## 0.6 Protected-file integrity

Run:

```powershell
git diff -- src
git diff -- data/reference
git diff -- adult_outpatient_laboratory_reference_map.csv
git diff -- requirements.txt
git diff -- docs/version-handoff/v2_analyte_manifest.json
git diff -- .env
git diff -- .env.example
git diff -- .gitignore
```

All output must be empty.

Do not proceed if a protected file changed.

---

## 0.7 Commit TIP-004B

After all Phase 0 gates pass, stage only authorized files:

```powershell
git add `
  eval/ragas_compat.py `
  eval/run_ragas.py `
  tests/test_eval/test_ragas_runner.py `
  tests/test_eval/test_ragas_live_runner.py `
  eval/results/ragas_v2_baseline.json `
  eval/results/ragas_v2_baseline.csv `
  eval/results/report.md
```

Add the scaffold report only if it contains a legitimate, previously authorized documentation-only update:

```powershell
git add docs/version-handoff/TIP-004A_RAGAS_SCAFFOLD_REPORT.md
```

Commit:

```text
feat(eval): record Gemini RAGAS V2 baseline
```

Then run:

```powershell
git status --short
git show --stat --oneline HEAD
git rev-parse HEAD
```

Required:

- working tree clean;
- commit contains only authorized TIP-004B files.

Record this hash as:

```text
TIP-004B final commit
```

---

# PHASE 1 — CREATE DELIVERY MANIFEST

Create:

```text
docs/version-handoff/v2_tuan_delivery_manifest.json
```

Required top-level structure:

```json
{
  "project": "P-056",
  "release": "V2",
  "owner_scope": "Tuan - Data and AI Quality",
  "branch": "feature/TQT-reference-ragas",
  "baseline_commit": "8fb263ea3043476a92aecc41b9c40e4ea7828239",
  "final_commit_before_handoff": "",
  "generated_at": "",
  "delivery_status": "ready_for_verify",
  "reference_data": {},
  "analytes": [],
  "reference_checker": {},
  "critical_detector": {},
  "ragas": {},
  "tests": {},
  "protected_files": {},
  "known_limitations": [],
  "deviations": []
}
```

Do not use Vietnamese diacritics in JSON keys.

Do not include secrets, local `.env` contents, API key values or credential hashes.

---

## Reference data section

Must include:

```json
{
  "source_file": "adult_outpatient_laboratory_reference_map.csv",
  "source_sha256": "721A07EA6EC8BC202DAD4F23808ECA34853A146E41E3EC3AE04EC66EABDA7D6B",
  "input_rows": 80,
  "strict_quality_eligible_rows": 58,
  "runtime_accepted_rows": 58,
  "quarantined_rows": 22,
  "multiple_reason_rows": 2,
  "rejection_reason_counts": {
    "range_flag_not_ok": 22,
    "confidence_not_high": 2,
    "unsupported_source_tier": 2
  }
}
```

Read these values from existing build artifacts and verify them.

Do not merely hardcode them without checking.

---

## Analyte records

Exactly nine records:

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

For each record include:

```json
{
  "analyte": "WBC",
  "normal_reference_status": "approved",
  "normal_reference_supported": true,
  "pending_reason": null,
  "critical_rule_available": false,
  "ragas_case_available": true
}
```

Current policy:

### Approved

```text
WBC
RBC
Fasting plasma glucose
Creatinine
```

### Pending

```text
HGB:
  unit_data_conflict

HDL-C:
  cdl_only
  unit_policy_conflict

HbA1c:
  md_not_approved

LDL-C:
  md_not_approved

Potassium:
  normal_reference_not_approved
  critical_detector_owned
```

Read evidence from the current manifest/config instead of duplicating policy blindly.

---

## RAGAS section

Include:

```json
{
  "dataset_path": "eval/datasets/ragas_v2_baseline.jsonl",
  "dataset_version": "v2-baseline-1",
  "dataset_sha256": "3f1cb84cebde5a5a47fca5eafca0a0276ebe6c04665fd9bb0531fe92ea24da2f",
  "total_cases": 12,
  "metric_eligible_cases": 11,
  "not_applicable_cases": 1,
  "provider": "google",
  "model": "gemini-2.5-flash",
  "transport_adapter": "google_openai_compatible",
  "ragas_version": "0.4.3",
  "live_full_baseline_invocations": 1,
  "faithfulness_mean": 0.909091,
  "context_precision_mean": 0.954545,
  "custom_hallucination_proxy_mean": 0.090909,
  "curated_fixture_baseline": true,
  "production_contexts_captured": false,
  "clinical_validation": false
}
```

Values must be loaded from result JSON/report and cross-validated.

---

## Deviations section

Include:

```json
[
  {
    "id": "DEV-004B-01",
    "description": "The metric smoke command was executed twice after the first attempt received HTTP 429 RESOURCE_EXHAUSTED.",
    "impact": "process_only",
    "full_baseline_rerun": false,
    "score_tuning_performed": false,
    "contractor_disposition": "waived_and_documented"
  }
]
```

---

# PHASE 2 — CREATE HANDOFF DOCUMENT

Create:

```text
docs/version-handoff/version-2-tuan-handoff.md
```

Use this exact structure:

```markdown
# P-056 RELEASE V2 — TUAN HANDOFF

## 1. Handoff metadata
## 2. Scope and ownership
## 3. Delivery summary
## 4. Commit map
## 5. Reference-data build
## 6. Runtime and quarantine artifacts
## 7. Nine-analyte status
## 8. Reference Repository and Checker
## 9. Unit policy
## 10. Age and sex policy
## 11. Critical Detector separation
## 12. API and output-contract compatibility
## 13. Automated-test evidence
## 14. RAGAS dataset and runner
## 15. RAGAS live baseline
## 16. Security and credential handling
## 17. Reproduction commands
## 18. Protected-file integrity
## 19. Known limitations
## 20. Pending decisions
## 21. Rollback procedure
## 22. Reviewer checklist
## 23. Readiness recommendation
```

---

## Mandatory handoff content

### Scope

State that Tuấn owns:

```text
reference data filtering
normal reference lookup
data/checker tests
RAGAS baseline
```

State that Tuấn did not change ownership of:

```text
graph architecture
shared state contract
analyzer/RAG architecture
guardrail policy
API production schema
critical threshold policy
authentication/deployment
```

### Commit map

Record the actual commit hashes for:

```text
TIP-000 scan
TIP-001 builder/data
TIP-002A tests
TIP-002B checker
TIP-003 integration
TIP-004A scaffold
TIP-004B live baseline
TIP-005 handoff
```

Expected known commits:

```text
TIP-000: e90f9563bff354e667ea5dbba928fb13604c4657
TIP-001: 1170e32369153e7ab8b60eabf3ab43731df35b97
TIP-002A: 54eeec4b467d8318488b443243fb794ffb9ba656
TIP-002B: 6b012a4f5a04eff176555dbc157c50908d10c9de
TIP-003: d8076a4e3ff93ff70b8144b9f5d0b449f209502c
TIP-004A: 01205af4aade3440b04f008762369d6d69873a77
TIP-004B: resolve from Git after Phase 0
```

Verify hashes through Git.

### Data build

Record:

```text
source rows = 80
strict eligible = 58
runtime accepted = 58
quarantine = 22
multiple-reason rows = 2
```

Include source SHA-256 and output artifact paths.

### Nine-analyte table

Columns:

```text
Analyte
Normal RI status
Unit status
Age status
Critical rule
RAGAS case
Blocker
```

Do not claim all nine are runtime approved.

### Unit policy

Document:

```text
10^3/uL -> 10^9/L
10^3/µL -> 10^9/L
10^3/μL -> 10^9/L
```

No numeric value conversion.

Document that:

```text
mg/dL != mmol/L
g/L != 10^9/L
```

HGB remains pending.

### Reference types

Document:

```text
RI = allowed for normal checker
CDL = not normal RI
MD = not automatically approved
critical thresholds = separate policy
```

### RAGAS

Record exact baseline metrics.

State prominently:

```text
This evaluates curated fixtures, not retrieved contexts captured from
the production graph.
```

Document:

```text
11 metric-eligible
1 not applicable
0 failed full-baseline cases
```

Do not claim score optimization, production readiness or clinical validation.

### Security

Document:

- exposed keys were rotated by Human;
- `.env` is ignored and untracked;
- key values were never committed;
- live evaluation used `GOOGLE_API_KEY`;
- OpenAI service and `OPENAI_API_KEY` were not used;
- OpenAI-compatible protocol targeted Google endpoint;
- credential scan result was zero.

Do not document the key value.

### Known limitations

At minimum:

```text
HGB remains pending due unit conflict
HDL-C remains pending because available rules are CDL-only
HbA1c and LDL-C remain MD/pending
Potassium normal RI remains pending
RAGAS contexts are curated fixtures
production graph does not expose retrieved contexts
direct unbootstrapped RAGAS import has compatibility issue
langchain-community deprecation warning exists
RAGAS baseline may vary by evaluator run
```

### Rollback

Provide commands based on commit IDs, but do not execute them.

Recommended safe options:

```text
git revert <TIP-004B-commit>
git revert <TIP-004A-commit>
git revert <TIP-003-commit>
```

Do not recommend hard reset or force push.

### Readiness recommendation

Use:

```text
READY FOR TIP-006 VERIFY
```

Do not write:

```text
SHIP
PRODUCTION READY
CLINICALLY VALIDATED
```

---

# PHASE 3 — CREATE PR PACKAGE

Create:

```text
docs/version-handoff/PULL_REQUEST_TUAN_V2.md
```

Required structure:

```markdown
# PR TITLE

## Summary
## Scope
## What changed
## Reference-data evidence
## Checker behavior
## Approved and pending analytes
## Test evidence
## RAGAS baseline
## Security
## Architecture-protection declaration
## Known limitations
## Review requests
## Reproduction commands
## Checklist
```

Recommended title:

```text
feat(v2): add validated reference lookup and initial RAGAS baseline
```

---

## Review requests

Explicitly ask Vũ to review:

```text
No graph.py changes
No state.py changes
No analyzer architecture changes
Checker output contract compatibility
Curated-context limitation for RAGAS
Future approach for runtime retrieved-context capture
```

Ask the data/medical owner to review:

```text
HGB source-unit conflict
HDL-C CDL-only policy
HbA1c MD status
LDL-C MD status
Potassium normal-reference approval
```

Do not resolve those pending decisions in TIP-005.

---

# PHASE 4 — DOCUMENT VALIDATION TESTS

Create:

```text
tests/test_docs/test_tuan_v2_handoff.py
```

Creating `tests/test_docs/__init__.py` is allowed only if required.

Required tests:

## H-01 — Required artifacts exist

Verify:

```text
version-2-tuan-handoff.md
PULL_REQUEST_TUAN_V2.md
v2_tuan_delivery_manifest.json
```

## H-02 — Delivery manifest schema

All required top-level keys exist.

## H-03 — Exact analyte inventory

Exactly nine analytes exist.

## H-04 — Approved list

Exactly:

```text
WBC
RBC
Fasting plasma glucose
Creatinine
```

are approved for normal RI.

## H-05 — Pending list

Exactly five analytes remain pending.

## H-06 — Data counts

Verify:

```text
80 = 58 + 22
```

## H-07 — RAGAS values

Manifest RAGAS values agree with:

```text
eval/results/ragas_v2_baseline.json
```

## H-08 — No production claim

Docs must not contain unsupported statements such as:

```text
production ready
clinically validated
all nine analytes supported
all analytes approved
```

Allow those phrases only when explicitly negated.

## H-09 — Curated-context limitation

Both handoff and PR package state that RAGAS uses curated contexts.

## H-10 — Pending analytes visible

HGB, HDL-C, HbA1c, LDL-C and Potassium must appear in the limitations or pending sections.

## H-11 — Protected architecture declaration

Handoff and PR state no graph/state production changes.

## H-12 — Security safety

No secret-shaped value appears in the new documentation/JSON.

## H-13 — Commit references

Each completed TIP has a real commit hash resolvable by Git.

## H-14 — Reproduction commands

Handoff contains commands for:

```text
reference builder
focused checker tests
full safe tests
RAGAS validate-only
RAGAS live baseline
```

The live command must not embed a key.

## H-15 — Deviation visibility

`DEV-004B-01` appears in the delivery manifest and handoff.

---

# ACCEPTANCE CRITERIA

## AC-005-01 — TIP-004B closed

Given the live baseline artifacts  
When close-out verification runs  
Then aggregates, case counts and hashes are internally consistent.

## AC-005-02 — Post-live regression

Given the final TIP-004B working tree  
When the safe suite runs  
Then zero failures, xfails and xpasses occur.

## AC-005-03 — Security close-out

Given result and code artifacts  
When scanned  
Then no credential or authorization value is found.

## AC-005-04 — Protected integrity

Given TIP-004B changes  
When inspected  
Then production, reference, dependency, manifest and environment files remain unchanged.

## AC-005-05 — TIP-004B commit

Given all close-out gates pass  
When committed  
Then only authorized eval/test/result files are included.

## AC-005-06 — Delivery manifest

Given all accepted TIP outputs  
When manifest is created  
Then counts, hashes, commits, analytes, tests and RAGAS evidence are recorded.

## AC-005-07 — Nine-analyte truthfulness

Given the intended analyte list  
When handoff is read  
Then four approved and five pending analytes are clearly distinguished.

## AC-005-08 — Reference-data traceability

Given source and generated outputs  
When handoff is read  
Then source hash, 80/58/22 counts and rejection reasons are present.

## AC-005-09 — Checker policy documentation

Given current implementation  
When handoff is read  
Then analyte, unit, age, sex, ambiguity and RI/CDL policies are explained.

## AC-005-10 — Critical separation documentation

Given Potassium critical handling  
When handoff is read  
Then normal checker and Critical Detector ownership remain distinct.

## AC-005-11 — RAGAS reproducibility

Given the live baseline  
When handoff is read  
Then dataset hash, model, provider, adapter, package version, case count and commands are recorded.

## AC-005-12 — RAGAS interpretation limits

Given curated fixtures  
When documentation is read  
Then no production or clinical-quality claim is made.

## AC-005-13 — Security documentation

Given the live evaluation  
When handoff is read  
Then credential handling is documented without disclosing secrets.

## AC-005-14 — Architecture declaration

Given shared ownership boundaries  
When PR package is read  
Then graph/state/analyzer/schema protection is explicit.

## AC-005-15 — Pending decisions

Given unresolved analytes and runtime-context capture  
When handoff is read  
Then owner decisions are listed rather than silently resolved.

## AC-005-16 — Rollback documentation

Given accepted commits  
When rollback section is read  
Then safe revert commands are provided without hard reset or force push.

## AC-005-17 — Documentation tests

Given handoff artifacts  
When focused doc tests run  
Then all pass.

## AC-005-18 — Full regression

Given documentation changes  
When the safe project suite runs  
Then no regression occurs.

## AC-005-19 — Documentation-only scope

Given TIP-005 implementation  
When Git diff is inspected  
Then no production or data file is changed.

## AC-005-20 — Verify readiness

Given TIP-005 completion  
When the Completion Report concludes  
Then recommendation is `CONTINUE TO TIP-006 VERIFY`, not `SHIP`.

---

# REQUIRED COMMANDS

## Focused handoff tests

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest `
  tests\test_docs\test_tuan_v2_handoff.py `
  -q -rxX -p no:cacheprovider
```

## Existing doc/manifest tests

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest `
  tests\test_data\test_v2_analyte_manifest.py `
  -q -rxX -p no:cacheprovider
```

## Full safe suite

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest `
  tests `
  -q -rxX -p no:cacheprovider `
  --ignore=tests/test_embed.py
```

## Compile

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m compileall -q src eval tests
```

## Dependency health

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -m pip check
```

Required:

```text
0 failed
0 xfailed
0 xpassed
compile exit code 0
pip check clean
```

---

# INTEGRITY CHECK

Run:

```powershell
git status --short
git diff --check
git diff --name-only

git diff -- src
git diff -- data/reference
git diff -- adult_outpatient_laboratory_reference_map.csv
git diff -- requirements.txt
git diff -- .env
git diff -- .env.example
git diff -- .gitignore
```

After the TIP-004B commit, TIP-005 changes may include only:

```text
docs/version-handoff/v2_tuan_delivery_manifest.json
docs/version-handoff/version-2-tuan-handoff.md
docs/version-handoff/PULL_REQUEST_TUAN_V2.md
tests/test_docs/test_tuan_v2_handoff.py
```

Optional package marker:

```text
tests/test_docs/__init__.py
```

---

# COMMIT TIP-005

After every AC passes:

```powershell
git add `
  docs/version-handoff/v2_tuan_delivery_manifest.json `
  docs/version-handoff/version-2-tuan-handoff.md `
  docs/version-handoff/PULL_REQUEST_TUAN_V2.md `
  tests/test_docs/test_tuan_v2_handoff.py
```

Add package marker only if present and needed.

Commit:

```text
docs(handoff): document Tuan V2 delivery
```

Do not amend previous commits.

Do not push unless instructed.

After commit:

```powershell
git status --short
git log --oneline -10
git show --stat --oneline HEAD
```

Working tree must be clean.

---

# FAILURE RULES

Return `BLOCKED` if:

- post-live safe regression fails;
- result JSON, CSV and Markdown disagree;
- aggregate metrics cannot be reproduced;
- a credential-like value is found;
- `.env` is tracked;
- protected files changed;
- TIP-004B candidate commit contains unauthorized files;
- the handoff claims all nine analytes are approved;
- RAGAS is described as production or clinical validation;
- real commit hashes cannot be resolved;
- documentation tests or full suite fail.

Do not rerun live RAGAS to repair a documentation inconsistency.

Do not change scores manually.

---

# COMPLETION REPORT FORMAT

Return exactly:

```markdown
# COMPLETION REPORT — TIP-005

## STATUS
DONE / PARTIAL / BLOCKED

## TIP-004B CLOSE-OUT
- Result artifact validation:
- Aggregate recalculation:
- Post-live full suite:
- Compile:
- Pip check:
- Credential scan:
- Protected-file check:
- TIP-004B commit:
- Working tree after TIP-004B commit:

## BASELINE
- Repository:
- Branch:
- TIP-005 start commit:
- TIP-005 end commit:
- Working tree before:
- Working tree after:

## FILES CHANGED

### Created
- path — purpose

### Modified
- None / list

### Deleted
- None

## DELIVERY SUMMARY
- Source rows:
- Runtime accepted:
- Quarantined:
- Approved analytes:
- Pending analytes:
- RAGAS cases:
- Metric-eligible:
- RAGAS Faithfulness mean:
- RAGAS Context Precision mean:
- Custom hallucination proxy mean:
- Final safe-test count:

## ACCEPTANCE CRITERIA
| AC | Status | Evidence |
|---|---|---|
| AC-005-01 | PASS/FAIL | |
| AC-005-02 | PASS/FAIL | |
| AC-005-03 | PASS/FAIL | |
| AC-005-04 | PASS/FAIL | |
| AC-005-05 | PASS/FAIL | |
| AC-005-06 | PASS/FAIL | |
| AC-005-07 | PASS/FAIL | |
| AC-005-08 | PASS/FAIL | |
| AC-005-09 | PASS/FAIL | |
| AC-005-10 | PASS/FAIL | |
| AC-005-11 | PASS/FAIL | |
| AC-005-12 | PASS/FAIL | |
| AC-005-13 | PASS/FAIL | |
| AC-005-14 | PASS/FAIL | |
| AC-005-15 | PASS/FAIL | |
| AC-005-16 | PASS/FAIL | |
| AC-005-17 | PASS/FAIL | |
| AC-005-18 | PASS/FAIL | |
| AC-005-19 | PASS/FAIL | |
| AC-005-20 | PASS/FAIL | |

## TEST RESULTS
- Handoff tests:
- Manifest tests:
- Full safe suite:
- Compile:
- Pip check:
- Failed:
- Xfailed:
- Xpassed:
- Skipped:

## DOCUMENTATION EVIDENCE
- Delivery manifest:
- Handoff:
- PR body:
- Commit map complete:
- Reproduction commands complete:
- Pending decisions visible:
- Deviation visible:
- Secret scan:

## PROTECTED FILE CHECK
- Production source changed: YES / NO
- Reference data changed: YES / NO
- Graph/state changed: YES / NO
- Critical policy changed: YES / NO
- API/schema changed: YES / NO
- Dependencies changed: YES / NO
- Environment files changed: YES / NO

## ISSUES DISCOVERED
- Severity:
- Evidence:
- Impact:
- Recommendation:

## DEVIATIONS FROM SPEC
- DEV-004B-01:
- Other:

## DECISIONS REQUIRED
- None / list

## RECOMMENDATION
CONTINUE TO TIP-006 VERIFY / FIX TIP-005 / ESCALATE

## NEXT TIP READINESS
READY / NOT READY

Reason:
```

---

# FINAL INSTRUCTION

Close and commit TIP-004B first.

Then create the handoff and PR package.

Do not run live APIs.

Do not modify production code or reference data.

Do not push.

Return the full `COMPLETION REPORT — TIP-005`.
