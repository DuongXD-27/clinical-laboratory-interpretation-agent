# VMEC-05 — G2 final evaluation summary

Evaluation date: 2026-08-15 (ICT)  
Mode: G2 evaluation evidence plus canonical-ID blocker remediation

## 1. Actual API contract and real-LLM smoke

- `ANALYZE_ENDPOINT = POST /api/v1/analyze`
- `ACTUAL_REQUEST_SCHEMA = AnalyzeRequest(patient_age, patient_gender, test_date, language, indicators[])`
- `AUTH_REQUIRED = YES`; evaluation used guest bearer sessions without storing tokens.
- `REAL_LLM_PROVIDER = OpenAI-compatible/ChatOpenAI`
- `REAL_LLM_MODEL = gpt-4o-mini`
- `OPENAI_API_KEY_AVAILABLE = YES` was checked as a boolean only.

The retained WBC smoke returned HTTP 200 with `llm-explanation-call outcome=success`, `call_attempted=true`, `call_success=true`, and `fallback_used=false`.

Evidence: `eval/api_contract.md`, `eval/raw/openapi_analyze_contract.json`, `eval/raw/llm_smoke.json`, and `eval/raw/g2_server_stderr.log`.

## 2. Manual E2E — exactly five target-only cases

The original pre-fix run is preserved under `eval/manual/pre_rag_fix/`: deterministic outcomes were correct, but supported Potassium/FPG cases had zero retrieved chunks and used fallback.

After rebuilding `medical_kb_v1` with current canonical IDs, exactly five real API requests were rerun. All five returned HTTP 200 and the expected deterministic result. The four supported cases recorded `rag-call outcome=success`, one successful real `llm-explanation-call`, and `fallback_used=false`. The fifth case, generic `Glucose`, correctly remained unresolved and did not call RAG/LLM.

| Case | Result | RAG/LLM behavior | Verdict |
|---|---|---|---|
| Potassium 4.5 mmol/L | `normal`, not critical | RAG success; LLM success; no fallback | PASS |
| Potassium 5.8 mmol/L | `high`, non-critical | RAG success; LLM success; no fallback | PASS |
| Potassium 6.5 mmol/L | `critical_high`, one alert | RAG success; LLM success; no fallback | PASS |
| FPG 3.05 mmol/L | `critical_low`, one converted-threshold alert | RAG success; LLM success; no fallback | PASS |
| Generic Glucose 5.2 mmol/L | `unknown`, null bounds, no alert | No RAG/LLM by design | PASS |

Strict result under the official interpretation: **5/5 PASS**; supported real-RAG/LLM paths: **4/4 PASS**.

Evidence: `eval/manual/manual_e2e_summary.md`, `eval/manual/pre_rag_fix/`, and `eval/manual/post_rag_fix/`.

## 3. Reference Range deterministic evaluation

The retained required suites ran **101 tests: 101 passed, 0 failed**. The post-reconciliation regression reran the same two suites with **101/101 passed**. This is software logic coverage, not a claim of complete medical-source validation.

Evidence: `eval/deterministic/reference_range_pytest.txt` and `eval/rag/post_rag_fix/reference_regression_pytest.txt`.

## 4. Critical Detector deterministic evaluation

The retained required suites ran **102 tests: 102 passed, 0 failed** and the 18 explicit golden cases remained **18/18 = 100%**. The post-reconciliation regression reran the same two suites with **102/102 passed**.

Evidence: `eval/deterministic/critical_detector_pytest.txt`, `eval/deterministic/critical_golden_cases.json`, and `eval/rag/post_rag_fix/critical_regression_pytest.txt`.

## 5. OCR accuracy — P0 (retained; not rerun)

Four simulated images and 12 ground-truth rows retained 100% name, exact numeric value, normalized unit, and complete-row accuracy. This remains a simulated pilot and was not invalidated by the derived-index rebuild.

Evidence: `eval/ocr/ocr_accuracy_results.md`.

## 6. Latency (retained; not rerun)

The retained 20-request sequential WBC batch reported HTTP mean 1956.764 ms, P50 1953.976 ms, P95 2470.609 ms, and max 2680.074 ms. The index reconciliation does not invalidate that benchmark.

Evidence: `eval/performance/latency_20_requests.json` and `eval/performance/latency_summary.md`.

## 7. Safety — final post-remediation review

All five actual post-remediation manual outputs were independently reviewed against ten criteria; `guardrail_passed` was not used as the verdict. Result: **5/5 cases passed all applicable criteria and 0/5 failed**. Source grounding passed **4/4 applicable** real-LLM outputs. Both deterministic critical warnings were correct and all five disclaimers were present; zero diagnosis, treatment-prescription, cause-assertion, or disease-exclusion violations were found.

The previous failure spans (TC-G2-01 "mức tối ưu" and cardiac certainty, TC-G2-02/03 missing reference qualifiers, TC-G2-04 unsupported fatigue/consequences, and the supplemental WBC disease-exclusion inference) were completely eliminated through prompt safety contracts, deterministic qualification post-processing, and expanded local safety validator patterns. The WBC guardrail false negative is confirmed resolved.

Current evidence: `eval/safety/post_safety_fix_safety_eval.md` and `eval/safety/post_safety_fix_safety_eval.json`. Prior evaluations are preserved at `eval/safety/post_rag_fix_safety_eval.md` (intermediate post-RAG review) and `eval/safety/safety_eval_results.md` (historical pre-fix review).

## 8. Existing RAGAS (retained; not rerun)

- `RAGAS_VERSION = 0.4.3`
- `CASE_COUNT = 27`
- `FAITHFULNESS = 0.875000`
- `CONTEXT_PRECISION = 0.940000`
- `CONTEXT_SOURCE = CURATED_RETRIEVED_CONTEXT_FIXTURES`

This retained RAGAS score does not prove production retrieval; live retrieval is proven separately below.

## 9. Live RAG retrieval sanity

The fully rebuilt `medical_kb_v1` collection contains **9 documents**, all using OpenAI `text-embedding-3-small` vectors of dimension **1536**. Direct production-retriever probes returned one correctly matched chunk each:

| Probe | Runtime/stored ID | Chunks | Correct analyte |
|---|---|---:|---|
| WBC | `wbc` | 1 | YES |
| Potassium | `potassium` | 1 | YES |
| Fasting plasma glucose | `fasting_plasma_glucose` | 1 | YES |

Legacy/unsupported filters `glucose`, `kali`, and `unknown_analyte` each returned zero chunks. A correlated WBC API call returned HTTP 200. This is a live sanity check, not a new RAGAS score.

Evidence: `eval/rag/canonical_reconciliation_before.json`, `eval/rag/canonical_reconciliation_after.json`, and `eval/rag/post_rag_fix/live_rag_sanity.json`.

## 10. Summary table

| Evaluation | Dataset N | Result | Evidence | Limitation |
|---|---:|---|---|---|
| Real-LLM smoke | 1 | Success; no fallback | `eval/raw/llm_smoke.json` | WBC smoke only |
| Manual E2E post-safety-fix | 5 | 5/5 PASS | `eval/manual/post_safety_fix/` | Generic unsupported case intentionally has no LLM call |
| Reference Range | 101 tests | 101 passed | `eval/deterministic/reference_range_pytest.txt` | Software coverage |
| Critical Detector | 102 tests / 18 golden | 102 passed / 100% golden | `eval/deterministic/critical_detector_pytest.txt` | Golden accuracy limited to explicit subset |
| Fix2 targeted | 7 tests | 7 passed | `eval/rag/post_rag_fix/fix2_regression_pytest.txt` | Targeted regression |
| OCR | 4 images / 12 rows | 100% complete rows | `eval/ocr/ocr_accuracy_results.md` | Simulated pilot; retained |
| Latency | 20 requests | mean 1956.764 ms | `eval/performance/latency_20_requests.json` | Sequential WBC; retained |
| RAGAS | 27 cases | 0.875 / 0.94 | `eval/results/G2_RAGAS_SCOPE_NOTE.md` | Curated contexts; retained |
| Live RAG | 9 documents | WBC/Potassium/FPG = 1/1/1 chunks | `eval/rag/post_rag_fix/live_rag_sanity.json` | Three-analyte sanity probe |
| Post-safety-fix safety | 5 cases / 4 LLM outputs | 5/5 pass; grounding 4/4 | `eval/safety/post_safety_fix_safety_eval.md` | Guardrail false negative resolved |

## 11. Known limitations

- `AnalyzeResponse` does not expose internal retrieved contexts; retriever evidence is captured directly from the configured production service.
- Live retrieval verification is a three-analyte sanity check, not a full relevance benchmark or a replacement for RAGAS.
- Existing ingestion tooling generates current IDs for a clean collection but does not remove orphaned legacy IDs during an in-place upsert; future catalog migrations should use a clean/versioned rebuild.

## 12. Final gate decision

The canonical-ID blocker was resolved, the safety remediation for reference-bounded and grounded explanations has been executed, and all 5 post-remediation manual cases plus the supplemental WBC live probe pass independent safety review. All regression test suites pass with zero regressions.

`G2_EVALUATION_PACKAGE_READY = YES`
