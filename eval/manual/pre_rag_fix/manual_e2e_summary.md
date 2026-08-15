# VMEC-05 G2 final manual E2E summary

Execution date: 2026-08-15 (ICT)  
Endpoint: `POST /api/v1/analyze`  
Schema: `AnalyzeRequest.indicators`  
Authentication: real guest bearer session; token not stored

Exactly five target-only API requests were executed. Production RI expectations were resolved before execution and recorded in `verified_reference_rules.json`. A separate WBC smoke request proved the configured OpenAI-compatible `gpt-4o-mini` LLM can succeed without fallback. The five required target cases themselves did not emit `llm-explanation-call`; their explanations are the curated safety fallback, so none is marked as a REAL-LLM case.

| Test | Purpose | Expected | Actual | Real LLM proven? | PASS/FAIL | Evidence |
|---|---|---|---|---|---|---|
| TC-G2-01 | Normal | Potassium normal; not critical | `normal`, RI 3.5–5.0, no alert | NO — no call attempted; fallback used | FAIL | `TC-G2-01.json` |
| TC-G2-02 | High, non-critical | Potassium high and `5.8 <= 6.1` | `high`, no alert | NO — no call attempted; fallback used | FAIL | `TC-G2-02.json` |
| TC-G2-03 | Critical high | Potassium `critical_high`; warning | `critical_high`; `6.5 > 6.1 mmol/L` alert | NO — no call attempted; fallback used | FAIL | `TC-G2-03.json` |
| TC-G2-04 | Critical low FPG | FPG `critical_low` through production conversion | `critical_low`; `54.9475495 < 55 mg/dL` alert | NO — no call attempted; fallback used | FAIL | `TC-G2-04.json` |
| TC-G2-05 | Generic Glucose fail-closed | unknown, null bounds, no escalation | `unknown`, null bounds, no alert | NO — no call attempted; fallback used | FAIL | `TC-G2-05.json` |

Target RI/critical outcomes matched expectations in 5/5, but the strict E2E verdict is **0/5 PASS** because “real LLM explanation” is mandatory for each case.

Observed blocker: `rag-call outcome=success` for current IDs `potassium` and `fasting_plasma_glucose` returned zero chunks because the populated collection contains legacy IDs (`kali`, `glucose`). Generic `Glucose` is intentionally unresolved and therefore has no analyte context. Product code/data were not changed to bypass this condition.
