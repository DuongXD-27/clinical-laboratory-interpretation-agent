# feat(v2): add validated reference lookup and initial RAGAS baseline

## Summary

- Builds a deterministic V2 reference data pipeline: 80 source rows → 58 accepted, 22 quarantined
- Implements a validated normal-reference checker with unit, age, sex, and RI/CDL/MD policies
- Delivers an initial RAGAS baseline (Faithfulness 0.909, Context Precision 0.955) using curated fixtures and Google Gemini evaluator

---

## Scope

**Owner:** Tuấn — Data and AI Quality

This PR covers:

- Reference data filtering and quarantine
- Normal reference lookup (four approved analytes)
- Data and checker automated tests
- RAGAS baseline evaluation pipeline

---

## What changed

| Module | Change |
|---|---|
| `src/data/build_reference_v2.py` | V2 reference builder with strict quality filter |
| `src/services/reference_checker_v2.py` | Normal-range checker using validated config |
| `data/reference/` | Generated V2 CSV, JSON, quarantine, build report, checker config |
| `docs/version-handoff/v2_analyte_manifest.json` | Nine-analyte status manifest |
| `eval/run_ragas.py` | RAGAS runner with Google OpenAI-compatible transport |
| `eval/ragas_compat.py` | Project-local Vertex AI import shim for `ragas==0.4.3` |
| `eval/datasets/ragas_v2_baseline.jsonl` | 12-case curated evaluation dataset |
| `eval/results/` | Live baseline JSON, CSV, and report |
| `tests/` | Unit, integration, characterization, RAGAS runner tests |

---

## Reference-data evidence

- Source file: `adult_outpatient_laboratory_reference_map.csv`
- Source SHA-256: `721A07EA6EC8BC202DAD4F23808ECA34853A146E41E3EC3AE04EC66EABDA7D6B`
- Input rows: **80**
- Strict-quality eligible: **58**
- Runtime accepted: **58**
- Quarantined: **22**
- Rejection reasons: `range_flag_not_ok` (22), `confidence_not_high` (2), `unsupported_source_tier` (2)

---

## Checker behavior

The V2 normal-reference checker:

- Loads only approved RI rules from `data/reference/reference_checker_v2_config.json`
- Applies unit aliases: `10^3/uL`, `10^3/µL`, `10^3/μL` → `10^9/L` (no numeric conversion)
- Never equates `mg/dL` with `mmol/L` or `g/L` with `10^9/L`
- Uses Adult mapping: 18–60 inclusive
- Gives priority to exact sex-specific rules; uses unambiguous `A` fallback only
- Fails safely for unknown or invalid gender — never silently selects an incorrect rule
- Does not own critical threshold classification (owned by Critical Detector)
- Does not process CDL or MD rows for normal classification

---

## Approved and pending analytes

### Approved for normal RI lookup (4)

| Analyte | Notes |
|---|---|
| WBC | Unit aliases applied; no numeric conversion |
| RBC | Sex-specific rules (M and F) |
| Fasting plasma glucose | RI rules only; CDL ignored for normal classification |
| Creatinine | Sex-specific rules (M and F) |

### Pending — not yet approved (5)

| Analyte | Blocker |
|---|---|
| HGB | `unit_data_conflict`: runtime `10^9/L` vs unit map `g/L` |
| HDL-C | `cdl_only`, `unit_policy_conflict` |
| HbA1c | `md_not_approved` |
| LDL-C | `md_not_approved` |
| Potassium | `normal_reference_not_approved`; Critical Detector owns critical behavior |

---

## Test evidence

| Suite | Result |
|---|---|
| Full safe suite (post-live) | **209 passed**, 0 failed, 0 xfailed, 0 xpassed |
| `compileall src eval tests` | exit code 0 |
| `pip check` | No broken requirements found |

---

## RAGAS baseline

Dataset: `eval/datasets/ragas_v2_baseline.jsonl` (version `v2-baseline-1`)  
SHA-256: `3f1cb84cebde5a5a47fca5eafca0a0276ebe6c04665fd9bb0531fe92ea24da2f`

**This evaluates curated fixtures, not retrieved contexts captured from the production graph.**

| Metric | N | Mean | Median | Min | Max |
|---|---:|---:|---:|---:|---:|
| Faithfulness | 11 | 0.909091 | 1.000000 | 0.500000 | 1.000000 |
| Context Precision | 11 | 0.954545 | 1.000000 | 0.500000 | 1.000000 |
| Custom hallucination proxy | 11 | 0.090909 | 0.000000 | 0.000000 | 0.500000 |

- Metric-eligible: 11 / 12
- `RAGAS-V2-012`: `not_applicable` — empty retrieved_contexts
- Failed cases: 0
- Full baseline invocations: exactly 1
- Evaluator: Google Gemini 2.5 Flash via OpenAI-compatible transport

> These scores are for evaluation plumbing visibility only. They are not production RAG validation and not clinical validation.

---

## Security

- API keys exposed in an earlier screenshot were revoked and replaced by the human. Keys were never committed.
- `.env` is git-ignored and untracked.
- Credential scan of all candidate artifacts returned zero matches.
- Live evaluation used `GOOGLE_API_KEY` from local environment only.
- OpenAI service and `OPENAI_API_KEY` were not used.

---

## Architecture-protection declaration

This PR makes **no changes** to:

- `src/agents/graph.py`
- `src/agents/state.py`
- Analyzer or RAG architecture
- Guardrail policy
- Public API production schema
- Critical threshold policy
- Authentication or deployment

The checker output contract is backward-compatible with the existing API.

---

## Known limitations

1. HGB pending — `unit_data_conflict` must be resolved before approval
2. HDL-C pending — CDL-only rules and unit_policy_conflict
3. HbA1c pending — MD status
4. LDL-C pending — MD status
5. Potassium normal RI pending — Critical Detector owns critical classification
6. RAGAS contexts are curated fixtures; production graph does not expose retrieved contexts
7. `langchain-community` deprecation warning present in test suite
8. RAGAS baseline may vary across evaluator runs

---

## Review requests

### Vũ — please review

- [ ] Confirm no changes to `graph.py` or `state.py`
- [ ] Confirm no changes to analyzer architecture
- [ ] Confirm checker output contract compatibility
- [ ] Assess the curated-context limitation for RAGAS
- [ ] Provide direction on future approach for runtime retrieved-context capture

### Data/medical owner — please review

- [ ] HGB source-unit conflict: runtime `10^9/L` vs unit map `g/L` — decision required before HGB can be approved
- [ ] HDL-C CDL-only policy — determine if RI source is available
- [ ] HbA1c MD status — approve or reject for normal RI
- [ ] LDL-C MD status — approve or reject for normal RI
- [ ] Potassium normal-reference approval — confirm whether Critical Detector sole ownership is final

---

## Reproduction commands

### Build reference data

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m src.data.build_reference_v2
```

### Full safe test suite

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest `
  tests -q -rxX -p no:cacheprovider `
  --ignore=tests/test_embed.py
```

### RAGAS validate-only (offline)

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m eval.run_ragas `
  --dataset eval/datasets/ragas_v2_baseline.jsonl --validate-only
```

### RAGAS live baseline (requires GOOGLE_API_KEY in environment)

```powershell
F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m eval.run_ragas `
  --dataset eval/datasets/ragas_v2_baseline.jsonl `
  --live --provider google --model gemini-2.5-flash `
  --max-cases 12 --confirm-key-rotated --skip-probe-after-confirmed `
  --output eval/results/ragas_v2_baseline.json
```

---

## Checklist

- [x] Reference data build is deterministic and reproducible
- [x] All approved analytes pass unit, age, and sex policy
- [x] Pending analytes are clearly identified and not silently approved
- [x] Critical Detector separation documented and respected
- [x] RAGAS baseline is curated-fixture only — not production or clinical validation
- [x] No credential values committed
- [x] `.env` ignored and untracked
- [x] Protected files (`src/`, `data/reference/`, `requirements.txt`, `graph.py`, `state.py`) unchanged
- [x] Full safe test suite passes (209 passed, 0 failed)
- [x] Rollback procedure documented (git revert, no hard reset)
- [x] Pending decisions listed for owner resolution
- [x] DEV-004B-01 deviation documented
