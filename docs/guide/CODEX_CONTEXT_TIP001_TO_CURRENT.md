# P-056 V2 — COMPACT AGENT CONTEXT

> Use this file as the compact context handoff for a new Builder agent such as Codex.
> Read this file first, then read `TIP-005_HANDOFF_PR_PACKAGE.md` before changing code.

## 1. Project and workflow

- **Project:** P-056 Release V2 — medical laboratory reference checking and AI-quality evaluation.
- **Repository:** `F:\VIN_AI_PROJECT\P-056`
- **Branch:** `feature/TQT-reference-ragas`
- **Human owner:** Tuấn — data and AI quality.
- **Method:** Vibecode Kit v6.0.
- **Contractor:** Chat agent designs TIPs, reviews Completion Reports, and controls scope.
- **Builder:** Codex/Claude Code implements only the active TIP and returns evidence.
- **Current active task:** **TIP-005 — close TIP-004B, create handoff, delivery manifest, and PR package.**
- **Next gate after TIP-005:** TIP-006 independent VERIFY.

## 2. Hard scope boundaries

Tuấn's delivered scope:

- Filter and quarantine reference data.
- Validated normal-reference lookup.
- Unit, age, sex, ambiguity, and RI/CDL policies.
- Checker and integration tests.
- Offline and live RAGAS baseline on curated fixtures.

Do not change ownership or behavior of:

- `src/agents/graph.py`
- `src/agents/state.py`
- Analyzer/RAG architecture.
- Guardrail policy.
- Public API production schema.
- Critical-threshold policy.
- Authentication or deployment.

Do not broaden analyte approval during handoff work.

## 3. Fixed analyte policy

### Approved for normal RI lookup

| Analyte | Status |
|---|---|
| WBC | approved |
| RBC | approved |
| Fasting plasma glucose | approved |
| Creatinine | approved |

### Pending for normal RI lookup

| Analyte | Reason |
|---|---|
| HGB | `unit_data_conflict`; runtime `10^9/L` conflicts with unit map `g/L` |
| HDL-C | CDL-only and unit-policy conflict |
| HbA1c | MD; not approved as normal RI |
| LDL-C | MD; not approved as normal RI |
| Potassium | normal RI not approved; Critical Detector owns critical behavior |

### Reference-type policy

- **RI:** allowed for normal checker.
- **CDL:** not a normal reference interval.
- **MD:** not automatically approved.
- **Critical thresholds:** separate policy owned by Critical Detector.

### Unit policy

Approved textual aliases:

```text
10^3/uL -> 10^9/L
10^3/µL -> 10^9/L
10^3/μL -> 10^9/L
```

Numeric value is unchanged because these units are equivalent for count-per-volume representation.

Never equate:

```text
mg/dL != mmol/L
g/L != 10^9/L
```

### Age and sex policy

- Project-local `Adult` mapping: **18–60 inclusive**.
- Exact sex rule has priority.
- Safe `A` fallback is allowed only when unambiguous.
- Unknown/invalid gender must fail safely rather than silently select an unsafe rule.

## 4. Completed TIP timeline

| TIP | Outcome | Commit | Main result |
|---|---|---|---|
| TIP-001 | ACCEPTED | `1170e32369153e7ab8b60eabf3ab43731df35b97` | Deterministic V2 whitelist/quarantine build: 58 accepted, 22 quarantined |
| TIP-002A | ACCEPTED | `54eeec4b467d8318488b443243fb794ffb9ba656` | Characterization tests captured five checker gaps |
| TIP-002B | ACCEPTED | `6b012a4f5a04eff176555dbc157c50908d10c9de` | Checker uses validated V2 config/repository; five gaps fixed |
| TIP-003 | ACCEPTED | `d8076a4e3ff93ff70b8144b9f5d0b449f209502c` | Nine-analyte manifest and checker→critical integration verification |
| TIP-004A | ACCEPTED | `01205af4aade3440b04f008762369d6d69873a77` | RAGAS 0.4.3 scaffold, 12 curated cases, offline runner and compatibility shim |
| TIP-004B | CONDITIONALLY ACCEPTED | not committed yet | Live Gemini RAGAS baseline generated; close-out verification and commit still required |
| TIP-005 | ACTIVE | not committed | Close TIP-004B, then create handoff/manifest/PR package |

Earlier scan commit for traceability:

```text
TIP-000 scan: e90f9563bff354e667ea5dbba928fb13604c4657
```

## 5. Reference-data build facts

Verify these against existing build artifacts before writing final handoff:

```text
Source file: adult_outpatient_laboratory_reference_map.csv
Source SHA-256: 721A07EA6EC8BC202DAD4F23808ECA34853A146E41E3EC3AE04EC66EABDA7D6B
Input rows: 80
Strict-quality eligible: 58
Runtime accepted: 58
Quarantined: 22
Multiple-reason rows: 2
Rejection counts:
  range_flag_not_ok: 22
  confidence_not_high: 2
  unsupported_source_tier: 2
```

Key generated artifacts:

```text
data/reference/reference_ranges_v2.csv
data/reference/reference_ranges_v2.json
data/reference/quarantine_v2.csv
data/reference/reference_build_report.json
data/reference/reference_checker_v2_config.json
docs/version-handoff/v2_analyte_manifest.json
```

## 6. TIP-004A RAGAS scaffold

Pinned dependency:

```text
ragas==0.4.3
```

RAGAS 0.4.3 has a legacy Vertex AI import problem in this environment. The approved workaround is project-local:

```text
eval/ragas_compat.py
```

Do not patch `.venv/site-packages`.

Dataset:

```text
eval/datasets/ragas_v2_baseline.jsonl
Version: v2-baseline-1
Cases: 12
Approved analytes only: WBC, RBC, Fasting plasma glucose, Creatinine
Dataset SHA-256: 3f1cb84cebde5a5a47fca5eafca0a0276ebe6c04665fd9bb0531fe92ea24da2f
```

The contexts are **curated evaluation fixtures**, not contexts captured from the production graph.

## 7. TIP-004B live baseline facts

Evaluator configuration:

```text
Logical provider: Google
Model: gemini-2.5-flash
Transport: Google OpenAI-compatible endpoint
Transport library: openai-python
Endpoint host: generativelanguage.googleapis.com
RAGAS version: 0.4.3
Credential variable: GOOGLE_API_KEY
OpenAI service used: NO
OPENAI_API_KEY used: NO
Concurrency: 1
Automatic retries: 0
```

Live baseline result:

| Metric | Count | Mean | Median | Min | Max | Std dev | N/A |
|---|---:|---:|---:|---:|---:|---:|---:|
| Faithfulness | 11 | 0.909091 | 1.000000 | 0.500000 | 1.000000 | 0.192847 | 1 |
| Context Precision | 11 | 0.954545 | 1.000000 | 0.500000 | 1.000000 | 0.143740 | 1 |
| Custom hallucination proxy | 11 | 0.090909 | 0.000000 | 0.000000 | 0.500000 | 0.192847 | 1 |

Additional facts:

- Total dataset cases: 12.
- Metric-eligible: 11.
- `RAGAS-V2-012`: `not_applicable` because contexts are empty.
- Failed full-baseline cases: 0.
- Unsupported-claim expected contrast: passed.
- Relevant-first context-order expected contrast: passed.
- Dataset/prompt tuning after seeing scores: NO.
- Full baseline invocation count: exactly 1.

Interpretation boundary:

> This is a curated-fixture baseline for evaluation plumbing and metric visibility. It is not production RAG validation, clinical validation, or evidence that all analytes are approved.

## 8. Security history and current policy

- API keys were accidentally visible in an earlier screenshot.
- Human confirmed exposed keys were revoked and replaced.
- `.env` is ignored and untracked.
- `GOOGLE_API_KEY` is present locally.
- Never print, hash, partially display, log, or commit key values.
- Candidate artifact secret scans returned zero matches.
- Do not call external APIs again during TIP-005.

## 9. Accepted deviation

Document this exactly in TIP-005 artifacts:

```text
DEV-004B-01
The one-case metric smoke command was executed twice.
Attempt 1 failed with HTTP 429 RESOURCE_EXHAUSTED because prepayment credits were depleted.
Attempt 2 succeeded.
The full 12-case baseline was executed exactly once.
No score tuning or credential leak occurred.
Contractor disposition: waived_and_documented.
```

This is a process deviation, not a metric-validity failure.

## 10. Current working tree before TIP-005 close-out

Observed candidate changes:

```text
 M eval/ragas_compat.py
 M eval/results/report.md
 M eval/run_ragas.py
 M tests/test_eval/test_ragas_runner.py
?? eval/results/ragas_v2_baseline.csv
?? eval/results/ragas_v2_baseline.json
?? tests/test_eval/test_ragas_live_runner.py
```

Expected result files exist:

```text
eval/results/ragas_v2_baseline.json
eval/results/ragas_v2_baseline.csv
eval/results/report.md
```

Do not discard these changes.

Forbidden commands during preservation:

```text
git reset
git restore
git checkout
git clean
git stash
```

## 11. Latest verified test evidence

Before the live run:

```text
Live runner tests: 26 passed, 1 warning
Eval suite: 63 passed, 1 warning
Full safe suite: 209 passed, 2 warnings
Compileall: passed
pip check: No broken requirements found
```

Warnings observed:

- `langchain-community` deprecation/sunset warning.
- Google GenAI aiohttp inheritance deprecation warning.

TIP-005 must run the mandatory **post-live** full safe suite again before committing TIP-004B.

## 12. Active task: TIP-005

Full detailed instruction file:

```text
TIP-005_HANDOFF_PR_PACKAGE.md
```

Execution order:

### Phase A — Close TIP-004B

1. Inspect authorized diff only.
2. Validate JSON/CSV/Markdown result consistency offline.
3. Recalculate metrics from per-case JSON; tolerance `<= 0.000001`.
4. Confirm case 012 is null/`not_applicable`.
5. Run post-live full safe tests, compileall, and pip check.
6. Re-run secret scan without displaying matches.
7. Confirm protected-file diffs are empty.
8. Commit TIP-004B:

```text
feat(eval): record Gemini RAGAS V2 baseline
```

No live API call is allowed.

### Phase B — Build TIP-005 handoff package

Create only:

```text
docs/version-handoff/v2_tuan_delivery_manifest.json
docs/version-handoff/version-2-tuan-handoff.md
docs/version-handoff/PULL_REQUEST_TUAN_V2.md
tests/test_docs/test_tuan_v2_handoff.py
```

Optional only when required:

```text
tests/test_docs/__init__.py
```

Required content:

- Commit map for TIP-000 through TIP-005.
- Reference-data source hash and 80/58/22 evidence.
- Four approved and five pending analytes.
- Unit, age, sex, RI/CDL/MD, ambiguity, and Critical Detector policies.
- Exact RAGAS metrics and dataset hash.
- Curated-context and non-clinical limitations.
- Security handling without secrets.
- `DEV-004B-01` visibility.
- Safe rollback using `git revert`, never hard reset/force push.
- Explicit review requests for Vũ and medical/data owner.
- Recommendation: `READY FOR TIP-006 VERIFY`, not `SHIP`.

Then run focused documentation tests and full safe regression.

Commit TIP-005:

```text
docs(handoff): document Tuan V2 delivery
```

Do not push unless the Human explicitly asks.

## 13. Protected files during TIP-005

No modifications allowed to:

```text
src/
data/reference/
adult_outpatient_laboratory_reference_map.csv
requirements.txt
.env
.env.example
.gitignore
docs/version-handoff/v2_analyte_manifest.json
```

After the TIP-004B commit, TIP-005 should be documentation/tests only.

## 14. Stop conditions

Return `BLOCKED` instead of self-deciding when:

- Result JSON, CSV, and report disagree.
- Recalculated aggregates differ beyond tolerance.
- Post-live regression fails.
- Secret-shaped values are detected.
- `.env` is tracked.
- Protected files changed.
- Candidate TIP-004B commit contains unauthorized files.
- Documentation implies all nine analytes are approved.
- RAGAS is presented as production or clinical validation.
- A referenced commit hash cannot be resolved.

Do not rerun live RAGAS to fix documentation or artifact inconsistencies.

## 15. Required Builder output

Return:

```text
COMPLETION REPORT — TIP-005
```

It must include:

- TIP-004B close-out evidence and commit hash.
- Post-live test counts.
- Artifact consistency results.
- Secret scan result.
- Files created.
- 20/20 AC status.
- TIP-005 commit hash.
- Final clean working tree.
- Recommendation: `CONTINUE TO TIP-006 VERIFY`.

---

## Quick start for Codex

```text
1. Read this file.
2. Read TIP-005_HANDOFF_PR_PACKAGE.md.
3. Inspect Git status; preserve all authorized TIP-004B changes.
4. Do not make any network/API call.
5. Close and commit TIP-004B.
6. Create and test TIP-005 handoff artifacts.
7. Commit TIP-005.
8. Return the full Completion Report; do not push.
```
