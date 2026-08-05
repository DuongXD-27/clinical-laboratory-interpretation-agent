# P-056 RELEASE V2 — REFERENCE RANGE AND RAGAS IMPLEMENTATION SUMMARY

## 1. Executive summary

P-056 Release V2 adds a validated laboratory reference-range classification workflow and an initial RAGAS evaluation baseline to the existing AI analysis graph.

The delivery establishes:

- A deterministic pipeline that filters 80 source reference rows into 58 accepted and 22 quarantined rows
- A runtime normal-reference checker that classifies four approved analytes under strict unit, age, sex, and reference-type policies
- A Critical Detector node that independently handles critical thresholds, with Potassium/Kali as its primary example
- An initial RAGAS baseline (Faithfulness 0.909, Context Precision 0.955) run against 12 curated evaluation fixtures using Google Gemini 2.5 Flash
- Full automated test coverage: 224 tests, zero failures
- Independent TIP-006 verification: READY, 15/15 P0 requirements verified, 28/28 scenarios pass

**The delivery is ready for human review and PR opening.** Five analytes remain pending and production retrieved-context capture is unresolved follow-up work.

---

## 2. Original problem and delivery scope

**Problem:** The existing P-056 graph lacked a validated source of laboratory reference intervals. Reference data needed quality filtering, and the runtime lookup needed deterministic policies for units, age, sex, and reference type.

**Tuấn's scope:**

| Area | Included |
|---|---|
| Reference data filtering and quarantine | YES |
| Normal reference lookup (approved analytes) | YES |
| Data and checker automated tests | YES |
| RAGAS baseline evaluation | YES |
| Graph/state architecture | NO — unchanged |
| Analyzer/RAG architecture | NO — unchanged |
| Guardrail policy | NO — unchanged |
| Public API production schema | NO — unchanged |
| Critical threshold policy | NO — separate node |
| Authentication/deployment | NO — unchanged |

---

## 3. Completed workflow and commit map

| TIP | Description | Commit |
|---|---|---|
| TIP-001 | Reference whitelist and quarantine build | `1170e32369153e7ab8b60eabf3ab43731df35b97` |
| TIP-002A | Characterization tests — capture checker gaps | `54eeec4b467d8318488b443243fb794ffb9ba656` |
| TIP-002B | Validated repository lookup — fix five gaps | `6b012a4f5a04eff176555dbc157c50908d10c9de` |
| TIP-003 | Integration verification and nine-analyte manifest | `d8076a4e3ff93ff70b8144b9f5d0b449f209502c` |
| TIP-004A | Offline RAGAS scaffold, dataset, and compat shim | `01205af4aade3440b04f008762369d6d69873a77` |
| TIP-004B | Live RAGAS baseline with Google Gemini 2.5 Flash | `fd9aaec79aaada2487bfae997f26c76ea7860bf8` |
| TIP-005 | Handoff, delivery manifest, and PR package | `9991d6929d4011ffd0da9ef4d66c7686c7c4128d` |
| TIP-006 | Independent verification — decision: READY | `e40fe1a116518c7837abf6531a0819617f2e8b36` |

All eight hashes are verified resolvable in Git.

---

## 4. Reference-data expansion

**Source:** `adult_outpatient_laboratory_reference_map.csv` — 80 adult outpatient laboratory reference rows

**Build pipeline:**

```
adult_outpatient_laboratory_reference_map.csv
  → src/scripts/build_reference_config.py
  → data/reference/reference_ranges_v2.csv      (58 accepted rows)
  → data/reference/reference_ranges_v2.json      (58 accepted records)
  → data/reference/quarantine_v2.csv             (22 quarantined rows)
  → data/reference/reference_build_report.json   (build audit)
```

**Result counts:**

| Metric | Count |
|---|---:|
| Source rows | 80 |
| Strict-quality eligible / runtime accepted | 58 |
| Quarantined | 22 |
| Multiple-reason rows | 2 |

Quarantined rows are not silently deleted — they are preserved in `quarantine_v2.csv` for audit and future review. No quarantined row reaches the runtime lookup. One source row may carry multiple rejection reasons; the total rejection-reason count exceeds 22 because 2 rows have more than one reason.

---

## 5. Data-quality filtering and quarantine

Rows are rejected during the strict-quality filter when any of the following conditions apply:

| Rejection reason | Count | Meaning |
|---|---:|---|
| `range_flag_not_ok` | 22 | Range quality flag is not `OK` (e.g., `EST`, `MD`, `VFY`) |
| `confidence_not_high` | 2 | Source confidence is not `HIGH` |
| `unsupported_source_tier` | 2 | Source priority tier is not supported |

Accepted rows must pass all three criteria. Rows that fail on multiple criteria are counted in the rejection-reason totals for each criterion, but are counted once in the quarantine row total. This accounts for the 2 multiple-reason rows.

---

## 6. Nine-analyte delivery status

| Analyte | Normal RI status | Main blocker / status | RAGAS cases |
|---|---|---|---|
| WBC | **Approved** | Valid RI/unit/age; unit aliases applied | Yes |
| RBC | **Approved** | Valid sex-specific RI for M and F | Yes |
| HGB | Pending | `unit_data_conflict`: runtime `10^9/L` vs unit map `g/L` | No |
| Fasting plasma glucose | **Approved** | RI valid; CDL rows excluded from normal classification | Yes |
| HbA1c | Pending | `md_not_approved`: source rows are MD type | No |
| LDL-C | Pending | `md_not_approved`: source rows are MD/CDL type | No |
| HDL-C | Pending | `cdl_only`, `unit_policy_conflict`: CDL-only runtime rows | No |
| Creatinine | **Approved** | Valid RI/Adult/sex-specific for M and F | Yes |
| Potassium | Pending (normal RI) | `normal_reference_not_approved`; Critical Detector owns critical behavior | No |

**Four analytes are runtime-approved for normal RI lookup. Five remain pending.**

Critical-threshold availability (Potassium) does not imply normal-reference approval. These are independent policy domains.

---

## 7. Runtime reference lookup architecture

```
raw indicator (analyte, value, unit, age, sex)
  → reference_range_checker_node
      → ReferenceRepository
           ├─ reference_checker_v2_config.json  (approved analyte whitelist)
           ├─ reference_ranges_v2.json           (accepted RI rules)
           ├─ units_metric.csv                   (canonical unit map)
           └─ explanations.json                  (clinical source text)
      → classifies: normal / low / high / unknown
  → critical_detector_node
      → critical_thresholds.json
      → optionally adds: critical_low / critical_high
```

Safe failure behavior: when a rule cannot be applied (unknown analyte, age out of scope, ambiguous sex, wrong unit), the checker returns `unknown` rather than guessing or raising an exception.

---

## 8. Unit, age, sex and reference-type policies

### Unit policy

Approved textual aliases (no numeric conversion):

```
10^3/uL  →  10^9/L
10^3/µL  →  10^9/L
10^3/μL  →  10^9/L
```

The numeric value is unchanged because these representations are equivalent for count-per-volume.

Forbidden equalities (never aliased):

```
mg/dL  ≠  mmol/L
g/L    ≠  10^9/L
```

HGB remains pending because its runtime data uses `10^9/L` while `units_metric.csv` records `g/L`. These units are not equivalent.

### Age policy

- `Adult` maps to **18–60 inclusive**.
- Ages 17 and below, or 61 and above, return `unknown` (age scope not supported).
- No inference of age class from free-text.

### Sex policy

- Exact sex-specific rules (`M` / `F`) have priority over all-sex (`A`) fallback.
- The safe `A` fallback is used only when the rule is unambiguous for all sexes.
- Unknown or invalid sex input does not silently select an `A` rule — it returns `unknown`.
- Ambiguous rules (equal priority across sexes) return `unknown`.

### Reference-type policy

| Type | Runtime use |
|---|---|
| `RI` | Allowed for approved normal classification |
| `CDL` | Not a normal reference interval — excluded from normal checker |
| `MD` | Not automatically approved — excluded unless explicitly approved |
| Critical thresholds | Separate policy owned by `critical_detector_node` |

---

## 9. Critical Detector separation

`critical_detector_node` operates independently of the normal reference checker. A Potassium value can simultaneously be:

- **`unknown`** in the normal checker (normal RI not approved)
- **`critical_low` or `critical_high`** in the Critical Detector (when the value exceeds critical thresholds)

This separation is by design. The normal checker's `unknown` for Potassium is not a failure — it correctly reflects that Potassium normal RI classification has not been approved. Critical classification proceeds through its own node regardless.

---

## 10. File responsibility map — reference workflow

| File | Role | Lifecycle |
|---|---|---|
| `adult_outpatient_laboratory_reference_map.csv` | Authoritative source | Human-curated; do not edit generated outputs |
| `src/scripts/build_reference_config.py` | Build script — generates all reference artifacts | Run to rebuild from source |
| `data/reference/reference_ranges_v2.csv` | Generated — accepted rows | Rebuilt from source; do not hand-edit |
| `data/reference/reference_ranges_v2.json` | Generated — runtime lookup | Rebuilt from source; loaded by `ReferenceRepository` |
| `data/reference/quarantine_v2.csv` | Generated — audit trail for rejected rows | Rebuilt from source; not loaded at runtime |
| `data/reference/reference_build_report.json` | Generated — build audit metadata | Rebuilt from source; includes SHA-256, counts, rejection reasons |
| `data/reference/reference_checker_v2_config.json` | Generated — approved analyte whitelist and policies | Rebuilt from source; primary config for `ReferenceRepository` |
| `data/reference/units_metric.csv` | Authoritative — canonical unit definitions | Human-curated; defines which units are acceptable per analyte |
| `data/reference/explanations.json` | Authoritative — clinical source explanations | Human-curated; serialized in API response |
| `data/reference/critical_thresholds.json` | Authoritative — critical threshold rules | Owned by Critical Detector; separate policy domain |
| `src/services/reference_repository.py` | Runtime service — loads config, resolves rules, applies policies | Production code; do not modify without tests |
| `src/agents/nodes/reference_range_checker_node.py` | Runtime node — orchestrates checker per indicator | Production code; calls `ReferenceRepository` |
| `src/agents/nodes/critical_detector_node.py` | Runtime node — independent critical threshold evaluation | Production code; separate from normal checker |
| `docs/version-handoff/v2_analyte_manifest.json` | Handoff artifact — nine-analyte status with blockers | Updated when analyte policy changes |

**Do not edit generated JSON/CSV files directly.** Always rebuild from the authoritative source using `build_reference_config.py`.

---

## 11. Automated test coverage — reference workflow

| Test file | Tests | Purpose |
|---|---:|---|
| `tests/test_data/test_build_reference_config.py` | 10 | Build determinism: verifies counts, rejection reasons, and output consistency |
| `tests/test_services/test_reference_repository.py` | 53 | Repository policies: unit aliases, age boundaries, sex precedence, RI/CDL/MD separation, HGB conflict, pending analytes |
| `tests/test_agents/test_reference_range_checker_node.py` | 36 | Checker node: normal/low/high/unknown contracts, sex-specific rules, missing values, indicator order |
| `tests/test_agents/test_critical_detector_node.py` | 4 | Critical detection: Potassium critical classification independent of normal checker |
| `tests/test_integration/test_v2_reference_pipeline.py` | 17 | End-to-end pipeline: approved analytes, pending analytes, critical flow, API output contract |
| `tests/test_api/test_routes.py` | 9 | API contract: sources, disclaimer, unknown values, critical alerts; internal reasons hidden |
| `tests/test_data/test_v2_analyte_manifest.py` | 13 | Manifest: nine analytes, four approved, five pending, blockers, RAGAS flags |
| **Total** | **142** | All pass; 0 failed |

Full safe suite result: **224 passed, 0 failed, 2 warnings** (pre-existing deprecation warnings).

---

## 12. RAGAS objectives and design

**Objective:** Establish a first measurable evaluation baseline for the P-056 AI system's faithfulness and context precision, using an offline-reproducible dataset of curated test cases.

> **Important limitation:** This evaluates curated fixtures, not retrieved contexts captured from the production graph. Production graph context retrieval is a separate capability that does not yet expose contexts for direct RAGAS evaluation.

**Design decisions:**

- 12 curated cases covering the four approved analytes
- Cases include intentional contrast examples to verify metric sensitivity
- Case `RAGAS-V2-012` uses an empty `retrieved_contexts` field to verify graceful not-applicable handling
- Cases `RAGAS-V2-008` and `RAGAS-V2-009` use the same contexts in reversed order to verify ranking sensitivity
- Case `RAGAS-V2-003` contains an intentional unsupported claim to verify faithfulness detection
- No real patient data; language is Vietnamese (`vi`)

---

## 13. RAGAS dataset

| Field | Value |
|---|---|
| Dataset path | `eval/datasets/ragas_v2_baseline.jsonl` |
| Metadata | `eval/datasets/ragas_v2_baseline.meta.json` |
| Version | `v2-baseline-1` |
| SHA-256 (LF-normalized) | `3f1cb84cebde5a5a47fca5eafca0a0276ebe6c04665fd9bb0531fe92ea24da2f` |
| Total cases | 12 |
| Approved analytes represented | WBC, RBC, Fasting plasma glucose, Creatinine |
| Metric-eligible | 11 |
| Not applicable | 1 (`RAGAS-V2-012` — empty `retrieved_contexts`) |
| Real patient data | false |

**Important cases:**

| Case | Purpose |
|---|---|
| `RAGAS-V2-003` | Intentional unsupported claim — tests that Faithfulness < 1.0 when answer contradicts context |
| `RAGAS-V2-008` | Same contexts as RAGAS-V2-009, most-relevant context listed first |
| `RAGAS-V2-009` | Same contexts as RAGAS-V2-008, less-relevant context listed first — tests Context Precision ranking |
| `RAGAS-V2-012` | Empty `retrieved_contexts` — verified `not_applicable` result, no score fabrication |

Note on SHA-256: On Windows with `core.autocrlf = true`, `Get-FileHash` computes the CRLF-version hash. The LF-normalized hash above matches the value computed from the actual content. The git blob stores the LF content.

---

## 14. RAGAS runner and compatibility layer

### Runner: `eval/run_ragas.py`

Responsibilities:

1. Validate the JSONL dataset before any evaluation
2. Create `SingleTurnSample` and `EvaluationDataset` objects
3. Support offline `--validate-only` and `--inspect` modes (no API calls)
4. Guard live evaluation behind explicit `--live` flag and `--confirm-key-rotated` acknowledgment
5. Run metrics sequentially with concurrency=1 and retries=0
6. Validate all per-case scores (finite, in-range, proxy = 1 − faithfulness)
7. Aggregate results and write JSON, CSV, and Markdown outputs
8. Never automatically rerun a failed case

### Compatibility shim: `eval/ragas_compat.py`

`ragas==0.4.3` has a legacy Vertex AI import problem in this environment. The shim patches the import at runtime without modifying `.venv/site-packages`. It must remain until a reviewed RAGAS upgrade is performed.

### Transport configuration

| Field | Value |
|---|---|
| Logical provider | Google |
| Model | gemini-2.5-flash |
| Transport adapter | `google_openai_compatible` |
| Transport library | `openai-python` |
| Endpoint host | `generativelanguage.googleapis.com` |
| OpenAI service used | false |
| OPENAI_API_KEY used | false |
| Credential variable | `GOOGLE_API_KEY` |
| Concurrency | 1 |
| Automatic retries | 0 |

The OpenAI-compatible protocol is used as a transport layer to reach the Google endpoint — no OpenAI billing or service is involved.

### Reproduction commands

**Offline validate (no API call):**
```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m eval.run_ragas `
  --dataset eval/datasets/ragas_v2_baseline.jsonl `
  --validate-only
```

**Live baseline (requires `GOOGLE_API_KEY` in environment; key must not be embedded):**
```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m eval.run_ragas `
  --dataset eval/datasets/ragas_v2_baseline.jsonl `
  --live --provider google --model gemini-2.5-flash `
  --max-cases 12 --confirm-key-rotated `
  --skip-probe-after-confirmed `
  --output eval/results/ragas_v2_baseline.json
```

---

## 15. Live RAGAS baseline results

| Metric | Count | Mean | Median | Min | Max | Std dev | N/A |
|---|---:|---:|---:|---:|---:|---:|---:|
| Faithfulness | 11 | 0.909091 | 1.000000 | 0.500000 | 1.000000 | 0.192847 | 1 |
| Context Precision | 11 | 0.954545 | 1.000000 | 0.500000 | 1.000000 | 0.143740 | 1 |
| Custom hallucination proxy | 11 | 0.090909 | 0.000000 | 0.000000 | 0.500000 | 0.192847 | 1 |

Definitions:

- **Faithfulness:** fraction of the answer's claims that are supported by the retrieved contexts
- **Context Precision:** how well the relevant contexts are ranked above irrelevant ones
- **Custom hallucination proxy:** `1 - faithfulness` — a derived metric, not a separate LLM call

Additional facts:

- One full live pass; exactly 1 invocation of the complete 12-case baseline
- No score tuning or threshold optimization performed
- No dataset modification after seeing scores
- 0 failed full-baseline cases
- `RAGAS-V2-012`: `not_applicable` because `retrieved_contexts` is empty — no score fabricated
- Contrast checks: unsupported-claim (003) and reversed-context-order (008/009) both passed

> **Interpretation boundary:** This baseline measures evaluation plumbing and metric visibility against curated fixtures. It is not production RAG validation, not clinical validation, and not evidence that all analytes are approved for production use. Scores may vary across repeated evaluator runs.

---

## 16. File responsibility map — RAGAS

| File | Role | Lifecycle |
|---|---|---|
| `eval/datasets/ragas_v2_baseline.jsonl` | Dataset — 12 curated evaluation cases | Human-curated; add cases with new version tag |
| `eval/datasets/ragas_v2_baseline.meta.json` | Dataset metadata — version, analytes, scope, limitations | Update when dataset version changes |
| `eval/ragas_compat.py` | Compatibility shim — patches Vertex AI import in `ragas==0.4.3` | Remove only after reviewed RAGAS upgrade |
| `eval/run_ragas.py` | Evaluation runner — validation, live evaluation, aggregation, output | Production evaluation tool |
| `eval/results/ragas_v2_baseline.json` | Generated — full per-case and aggregate results | Do not edit; regenerate via live run |
| `eval/results/ragas_v2_baseline.csv` | Generated — per-case CSV summary | Do not edit; regenerate via live run |
| `eval/results/report.md` | Generated — human-readable baseline report | Do not edit; regenerate via live run |
| `tests/test_eval/test_ragas_compat.py` | Tests for compatibility shim | Update when shim is removed |
| `tests/test_eval/test_ragas_runner.py` | Offline runner tests — validation, inspect, dataset loading | Keep current |
| `tests/test_eval/test_ragas_v2_dataset.py` | Dataset integrity tests — structure, SHA-256, analyte policy | Update when dataset version changes |
| `tests/test_eval/test_ragas_live_runner.py` | Live runner behavior tests — guarding, output contracts | Keep current |
| `docs/version-handoff/TIP-004A_RAGAS_SCAFFOLD_REPORT.md` | Historical — TIP-004A scaffold decisions and offline validation | Retained for audit; not modified |

---

## 17. Security and credential handling

| Item | Status |
|---|---|
| `.env` file | Ignored by `.gitignore`; untracked; never committed |
| Exposed keys from prior session | Revoked and replaced by the human owner |
| `GOOGLE_API_KEY` | Used for live evaluation; loaded from local environment only |
| Key values committed | Never |
| `OPENAI_API_KEY` | Not read; OpenAI service not used |
| Credential scan of tracked files | 0 real credentials found |
| Credential scan of candidate commits | 0 real credentials found |
| TIP-006 external API calls | None |

The OpenAI-compatible transport protocol was used to reach the Google endpoint. No OpenAI billing or service account is involved.

---

## 18. Verification evidence

TIP-006 independent verification result: **READY**

| Check | Result |
|---|---|
| P0 requirements verified | 15 / 15 |
| P1 requirements verified | 5 / 5 |
| V-scenarios passed | 28 / 28 |
| Full safe suite | 224 passed, 0 failed |
| Compile | exit code 0 |
| pip check | No broken requirements found |
| Protected files changed | 0 |
| Real credentials found | 0 |
| TIP-006 commit | `e40fe1a116518c7837abf6531a0819617f2e8b36` |

Verify Report: `docs/version-handoff/VERIFY_REPORT_TUAN_V2.md`

---

## 19. Technical assessment

### Positive observations

1. **Clear source/runtime/quarantine separation** — rejected rows are auditable, not silently discarded
2. **Safe unknown behavior** — invalid unit, age, sex, or analyte returns `unknown` rather than a wrong classification
3. **Tested policies** — 53 repository tests cover unit aliases, age boundaries, sex precedence, RI/CDL/MD separation, and ambiguity cases
4. **Normal/critical separation** — Potassium demonstrates the pattern cleanly: `unknown` in normal checker, independently classified by Critical Detector
5. **Reproducible RAGAS artifacts** — JSON/CSV/Markdown results cross-verified; aggregates independently recalculated within 1e-6
6. **Security gates** — no credentials committed; `.env` properly ignored; key rotated after exposure incident
7. **Architecture ownership preserved** — `graph.py`, `state.py`, and API schema are unchanged; checker output is backward-compatible

### Cautions

1. **Normal-reference coverage is 4/9** — five analytes remain pending and are not classified at runtime
2. **Curated contexts do not prove production retrieval quality** — RAGAS scores are valid for the evaluation plumbing but do not represent real user session contexts
3. **Evaluator scores vary** — a single live pass is a starting point, not a stable threshold
4. **Compatibility shim is technical debt** — `eval/ragas_compat.py` must be maintained until a reviewed RAGAS upgrade is performed
5. **Medical and data owner review is required** — analyte approval decisions belong to domain experts, not the engineering workflow
6. **No clinical validation** — results have not been reviewed or validated by clinical professionals

---

## 20. Known limitations

1. **HGB pending** — source uses `10^9/L` at runtime, unit map records `g/L`; units are not equivalent and cannot be silently aliased
2. **HDL-C pending** — available runtime rules are CDL-only; CDL is not a normal reference interval; unit policy conflict also present
3. **HbA1c pending** — source rows are type MD; not approved as normal RI
4. **LDL-C pending** — source rows are type MD/CDL; not approved as normal RI
5. **Potassium normal RI pending** — Critical Detector owns critical classification; normal RI approval decision has not been made
6. **Production graph does not expose retrieved contexts** — RAGAS cannot evaluate production retrieval quality until context capture is implemented
7. **RAGAS uses curated fixtures** — evaluation contexts were manually written for test purposes and do not represent real user queries
8. **RAGAS import compatibility shim** — `eval/ragas_compat.py` patches `ragas==0.4.3` at runtime; must be removed after a reviewed upgrade
9. **langchain-community deprecation warning** — present in test suite; migration to standalone integration packages is needed
10. **Gemini/RAGAS score variability** — LLM-evaluated scores are non-deterministic; repeated runs may differ
11. **One smoke retry after HTTP 429** — DEV-004B-01: first smoke-test attempt failed with resource exhaustion; second attempt succeeded; full baseline was run exactly once
12. **No production or clinical validation** — this delivery is not validated for production deployment or clinical use

---

## 21. Recommended next steps

### P0 — Medical/data owner decisions (blockers for analyte approval)

1. **HGB** — Resolve the source-unit conflict: confirm whether the correct runtime unit for HGB is `10^9/L` (hematology count) or `g/L` (mass concentration); update `units_metric.csv` accordingly
2. **HDL-C** — Determine whether an approved RI source exists; if CDL rules can be promoted to RI with medical approval; update reference data if approved
3. **HbA1c** — Decide whether to approve as normal RI or maintain MD-only status
4. **LDL-C** — Decide whether to approve as normal RI or maintain MD/pending status
5. **Potassium** — Confirm whether Critical Detector sole ownership is final, or whether a normal RI approval is required; if normal RI is needed, provide approved source rows

### P1 — Production RAG evaluation

1. **Discuss with Vũ** — define the minimal approach for capturing `retrieved_contexts` from the production graph during evaluation sessions
2. **Build a production-trace dataset** — collect real user-session contexts for at least the four approved analytes
3. **Compare curated and production scores** — run RAGAS on the production-trace dataset and compare with the curated baseline to identify retrieval gaps

### P1 — Evaluation maturity

1. **Version future datasets** — use a new `version` tag and SHA-256 for every dataset change
2. **Record metadata with results** — always retain model, provider, transport, package version, and commit hash alongside RAGAS results
3. **Repeated comparisons before thresholds** — run at least three separate live passes before setting acceptance thresholds
4. **Medical-domain expert evaluation** — supplement automated RAGAS with expert review of answer quality for clinical content

### P2 — Dependencies and CI

1. **Review future RAGAS releases** — test the compat shim against each new version before removing it; do not remove until verified clean
2. **Migrate away from deprecated integrations** — address `langchain-community` sunset; migrate to standalone integration packages
3. **Run offline eval tests in CI** — `--validate-only` and dataset structure tests can run without API keys
4. **Keep live evaluation manually gated** — live RAGAS runs require human confirmation and key management; do not automate without a secrets management solution
5. **Keep future TIP instruction files outside maintained docs** — place new TIP specs in a temporary location (not `docs/guide/`) so cleanup is straightforward

---

## 22. Maintenance guide

### Add a new source reference row

1. Edit `adult_outpatient_laboratory_reference_map.csv` with the new row
2. Set `range_flag=OK`, `confidence=HIGH`, `source_priority_tier=T1` (or as appropriate)
3. Run `src/scripts/build_reference_config.py` — this regenerates all `data/reference/` artifacts
4. Run `tests/test_data/test_build_reference_config.py` to verify determinism
5. Update `docs/version-handoff/v2_analyte_manifest.json` if analyte status changes

### Approve a pending analyte

1. Resolve the blocker documented in `v2_analyte_manifest.json` (e.g., confirm unit, supply RI source)
2. Update the source CSV with approved RI rows
3. Rebuild reference artifacts
4. Update `v2_analyte_manifest.json`: set `approval_status=approved`, clear `blockers`
5. Update `data/reference/reference_checker_v2_config.json` to include the new analyte
6. Add RAGAS test cases for the newly approved analyte (new dataset version)
7. Run the full safe test suite

### Add a unit alias

1. Verify the units are genuinely equivalent (same quantity, same numeric scale)
2. Add the alias to `data/reference/units_metric.csv` under the canonical unit
3. Rebuild reference artifacts
4. Add a test case in `tests/test_services/test_reference_repository.py` mirroring the `test_u_wbc_*` pattern
5. Run the full safe test suite

### Add a RAGAS test case

1. Write the new case in JSONL format following the `RAGAS-V2-NNN` ID convention
2. Only use approved analytes; do not include real patient data
3. Increment the dataset version tag in `ragas_v2_baseline.meta.json`
4. Update the SHA-256 in `eval/datasets/ragas_v2_baseline.meta.json` and documentation
5. Add the corresponding test in `tests/test_eval/test_ragas_v2_dataset.py`
6. Run `--validate-only` to confirm structure before any live evaluation

### Upgrade RAGAS safely

1. Create a test branch
2. Upgrade `ragas` in `requirements.txt`
3. Run `F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m eval.run_ragas --validate-only` — if this passes without the shim, the shim can be removed
4. Run the full eval test suite: `tests/test_eval/`
5. Remove `eval/ragas_compat.py` and its import from `eval/run_ragas.py` only after confirmed clean
6. Run the full safe suite
7. Run a live RAGAS pass to confirm scores are stable before merging

**Do not edit `data/reference/reference_ranges_v2.json`, `reference_ranges_v2.csv`, or `reference_checker_v2_config.json` directly.** These are generated artifacts. Always rebuild from the authoritative source CSV using `build_reference_config.py`.

---

## 23. Conclusion

> The V2 workflow established a safe and auditable foundation for laboratory reference classification and RAG evaluation.
>
> The delivery is ready for human review and PR, while the five pending analytes and production retrieved-context capture remain explicit follow-up work.

Key achievements of this delivery:

- Deterministic and auditable reference-data pipeline with full quarantine traceability
- Four analytes approved under strict, tested policies (unit, age, sex, RI/CDL/MD)
- Clean Normal/Critical Detector separation — safe failures return `unknown`, never a wrong classification
- First measurable RAGAS baseline establishing evaluation infrastructure
- 224 automated tests, independently verified, zero failures
- No credentials committed; architecture ownership preserved

The remaining work — analyte approvals, production context capture, evaluation maturity — is explicitly documented and prioritized. No analyte has been silently approved, no production or clinical quality has been claimed.
