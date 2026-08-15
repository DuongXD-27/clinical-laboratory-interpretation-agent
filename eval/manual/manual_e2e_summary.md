# VMEC-05 G2 post-reconciliation manual E2E summary

Execution date: 2026-08-15 (ICT)  
Endpoint: `POST /api/v1/analyze`  
Authentication: real guest bearer session; token not stored

Exactly five target-only requests were executed after rebuilding `medical_kb_v1` with current canonical analyte IDs. The four supported cases each recorded successful live RAG and real LLM calls with no fallback. Generic `Glucose` is intentionally unresolved, so its correct fail-closed path does not require or attempt an LLM call.

| Test | Purpose | Actual deterministic result | RAG/LLM evidence | Verdict |
|---|---|---|---|---|
| TC-G2-01 | Potassium normal | `normal`, RI 3.5–5.0, no alert | `rag-call=success`; LLM success; no fallback | PASS |
| TC-G2-02 | Potassium high, non-critical | `high`, no alert | `rag-call=success`; LLM success; no fallback | PASS |
| TC-G2-03 | Potassium critical high | `critical_high`; one alert | `rag-call=success`; LLM success; no fallback | PASS |
| TC-G2-04 | FPG critical low | `critical_low`; one converted-threshold alert | `rag-call=success`; LLM success; no fallback | PASS |
| TC-G2-05 | Generic Glucose fail-closed | `unknown`, null bounds, no alert | No RAG/LLM call by design | PASS |

Result: **5/5 PASS**. The supported real-LLM flow is proven in 4/4 applicable cases; the fifth case proves the required Fix2 negative behavior.

Pre-fix artifacts remain immutable under `eval/manual/pre_rag_fix/`. Post-fix machine-readable evidence is under `eval/manual/post_rag_fix/`.
