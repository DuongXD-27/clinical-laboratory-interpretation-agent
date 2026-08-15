# VMEC-05 — G2 RAG canonical-ID reconciliation evidence

Date: 2026-08-15 (ICT)  
Disposition: blocker remediated; G2 evaluation package ready

## 1. Scope

This change reconciles the local derived Chroma index with the current nine-analyte canonical catalog. It does not change authoritative medical data, clinical thresholds/operators, Reference Range or Critical Detector behavior, Fix2 generic-Glucose policy, API schema, frontend, database/history, or guardrails.

## 2. Known G2 blocker

Before remediation, the current runtime requested `potassium` and `fasting_plasma_glucose`, while `medical_kb_v1` stored `kali` and `glucose`. Exact Chroma metadata filters therefore returned zero chunks, preventing the explanation LLM call and causing supported manual cases to use fallback.

## 3. Confirmed RAG architecture

- Embeddings: external OpenAI Embeddings API through `src/services/embedding_provider.py`, model `text-embedding-3-small`, dimension 1536.
- Vector storage/search: local persistent ChromaDB at `./data/chroma`; similarity search is local over stored vectors.
- Generator: external OpenAI Chat API through `src/services/llm.py`, evaluated model `gpt-4o-mini`.
- RAGAS evaluator: external Google Gemini API through `eval/run_ragas.py`; retained results were not rerun.

The blocker was local index metadata alignment, not a local-model issue.

## 4. Root cause analysis

The populated collection reflected legacy analyte identifiers. The current catalog and ingestion slug generation resolve to current IDs, while retrieval applies an exact `where={"analyte_id": analyte_id}` filter. Four of nine stored IDs were stale: FPG, LDL-C, HDL-C, and Potassium. In-place upsert through the existing ingestion command would add current documents without deleting legacy orphans, increasing the count from 9 to 13, so it was unsafe for this reconciliation.

`ROOT_CAUSE_CONFIRMED = YES`  
`RAG_ID_MISMATCH_CONFIRMED = YES`

## 5. Before ID matrix

| Current canonical analyte | Runtime retrieval ID | Chroma stored ID before | Match? |
|---|---|---|---|
| WBC | `wbc` | `wbc` | Yes |
| RBC | `rbc` | `rbc` | Yes |
| HGB | `hgb` | `hgb` | Yes |
| Fasting plasma glucose | `fasting_plasma_glucose` | `glucose` | **No** |
| HbA1c | `hba1c` | `hba1c` | Yes |
| LDL-C | `ldl_c` | `ldl_cholesterol` | **No** |
| HDL-C | `hdl_c` | `hdl_cholesterol` | **No** |
| Creatinine | `creatinine` | `creatinine` | Yes |
| Potassium | `potassium` | `kali` | **No** |

## 6. Embedding/index audit

| Property | Before | Rebuild/current |
|---|---|---|
| Provider | `openai` | `openai` |
| Model | `text-embedding-3-small` | `text-embedding-3-small` |
| Dimension | 1536 (stored vector inspected) | 1536 |
| Collection | `medical_kb_v1` | `medical_kb_v1` |
| Documents | 9 | 9 |
| Source SHA256 | `1286D65...6854A` | unchanged |
| API key | Present, boolean check only | Present, never logged |
| Embedding items generated | N/A | 9 |
| Embedding failures | N/A | 0 |

The full collection was rebuilt consistently; old and new vectors were not mixed.

## 7. Chosen remediation

`FIX_METHOD = REBUILD_INDEX` (Option A). An evaluation-only rebuild utility constructed a complete temporary collection from unchanged `data/reference/explanations.json`, deriving IDs from the current catalog. It validated count, exact ID set, metadata, and embedding dimension before atomically swapping the collection name. A rollback collection was retained until all live/API/regression checks passed, then removed.

No runtime compatibility mapping was added and no human approval was required.

## 8. Files/artifacts changed

- Expected runtime mutation: derived Chroma collection under `data/chroma`.
- Evaluation tooling/evidence: `eval/g2_execute.py`, `eval/g2_live_rag.py`, `eval/rag/rebuild_canonical_index.py`, and versioned pre/post evidence directories.
- Evaluation conclusions: `eval/G2_EVALUATION_SUMMARY.md` and this handoff document.
- Production source/medical data changes: none.

## 9. Chroma before state

- Collection: `medical_kb_v1`
- Document count: 9
- IDs: `wbc`, `rbc`, `hgb`, `glucose`, `hba1c`, `ldl_cholesterol`, `hdl_cholesterol`, `creatinine`, `kali`
- Provider/model/dimension metadata: OpenAI / `text-embedding-3-small` / 1536
- Full IDs, metadata, sources, inspected dimension, and source checksum: `eval/rag/canonical_reconciliation_before.json`

## 10. Chroma after state

- Collection: `medical_kb_v1`
- Document count: 9
- IDs: `wbc`, `rbc`, `hgb`, `fasting_plasma_glucose`, `hba1c`, `ldl_c`, `hdl_c`, `creatinine`, `potassium`
- Embedding items/failures: 9 / 0
- Full IDs, metadata, sources, documents, dimension, and source checksum: `eval/rag/canonical_reconciliation_after.json`

| Canonical analyte | Runtime ID | Chroma ID before | Chroma ID after | Retrieval before | Retrieval after |
|---|---|---|---|---|---|
| WBC | `wbc` | `wbc` | `wbc` | 1 chunk | 1 chunk |
| RBC | `rbc` | `rbc` | `rbc` | Not directly probed | Not directly probed |
| HGB | `hgb` | `hgb` | `hgb` | Not directly probed | Not directly probed |
| Fasting plasma glucose | `fasting_plasma_glucose` | `glucose` | `fasting_plasma_glucose` | 0 chunks | 1 chunk |
| HbA1c | `hba1c` | `hba1c` | `hba1c` | Not directly probed | Not directly probed |
| LDL-C | `ldl_c` | `ldl_cholesterol` | `ldl_c` | Not directly probed | Not directly probed |
| HDL-C | `hdl_c` | `hdl_cholesterol` | `hdl_c` | Not directly probed | Not directly probed |
| Creatinine | `creatinine` | `creatinine` | `creatinine` | Not directly probed | Not directly probed |
| Potassium | `potassium` | `kali` | `potassium` | 0 chunks | 1 chunk |

## 11. Live retriever verification

| Probe | Runtime ID | Stored document/metadata ID | Chunks | Top excerpt identity | Score | Result |
|---|---|---|---:|---|---:|---|
| WBC | `wbc` | `wbc` / `wbc` | 1 | `Chỉ số: WBC` | ~0.655 | PASS |
| Potassium | `potassium` | `potassium` / `potassium` | 1 | `Chỉ số: Potassium` | ~0.614 | PASS |
| FPG | `fasting_plasma_glucose` | `fasting_plasma_glucose` / same | 1 | `Chỉ số: Fasting plasma glucose` | ~0.697 | PASS |

The artifact captures exact queries, current scores, source URLs, stored IDs/metadata, and sufficient text excerpts. Negative filters `glucose`, `kali`, and `unknown_analyte` each returned zero chunks, proving no accidental cross-analyte retrieval.

Evidence: `eval/rag/post_rag_fix/live_rag_sanity.json`.

## 12. Real API RAG/LLM retest

All requests used `RAG_ENABLED=true`, OpenAI embeddings, and the real configured OpenAI-compatible `gpt-4o-mini` generator.

| Case | HTTP | Final status | Critical | RAG | LLM | Fallback | Request ID |
|---|---:|---|---|---|---|---|---|
| Potassium 4.5 mmol/L | 200 | `normal` | No | success | success | false | `143a8d03236346c6965b4b0293b4d2f9` |
| Potassium 5.8 mmol/L | 200 | `high` | No | success | success | false | `27e1e90276b942c9b39bf5bc824136d6` |
| Potassium 6.5 mmol/L | 200 | `critical_high` | Yes, one alert | success | success | false | `604d94367caf492db2063483b67d718c` |
| FPG 3.05 mmol/L | 200 | `critical_low` | Yes, one alert | success | success | false | `f3887d0c51014050b14face0f29ffec4` |

FPG followed the unchanged production conversion: `3.05 × 18.01559 = 54.94754950 mg/dL`, which is strictly below 55 mg/dL. Per-request timing and LLM event evidence are embedded in the four post-fix JSON artifacts and correlated server log.

## 13. Generic Glucose Fix2 regression

- `ReferenceRepository.resolve_analyte("Glucose") = None`
- `ReferenceRepository.resolve_analyte("Đường huyết") = None`
- API case 5.2 mmol/L: `unknown`, null bounds, no critical escalation, no RAG/LLM call by design.
- Targeted Fix2 regression: **7 passed, 0 failed**.

Evidence: `eval/rag/post_rag_fix/fix2_negative.json`, `eval/manual/post_rag_fix/TC-G2-05.json`, and `eval/rag/post_rag_fix/fix2_regression_pytest.txt`.

## 14. Reference Range regression

The two relevant suites passed **101/101** after the rebuild. No Reference Range file or node changed.

Evidence: `eval/rag/post_rag_fix/reference_regression_pytest.txt`.

## 15. Critical Detector regression

The two relevant suites passed **102/102** after the rebuild. Potassium strict boundaries, FPG Decimal conversion boundaries, unsupported inputs, inactive rules, and upstream unknown preservation remain covered. The retained golden subset remains 18/18.

Evidence: `eval/rag/post_rag_fix/critical_regression_pytest.txt` and `eval/deterministic/critical_golden_cases.json`.

## 16. Protected-file proof

SHA256 before and after are identical for:

- `data/reference/reference_ranges.json`
- `data/reference/critical_thresholds.json`
- `data/reference/reference_checker_v2_config.json`
- `data/reference/explanations.json`
- `src/agents/nodes/reference_range_checker_node.py`
- `src/agents/nodes/critical_detector_node.py`
- `src/services/measurement_conversion.py`
- `src/scripts/ingest_kb.py`

Evidence: `eval/rag/protected_file_hashes.json` (`all_unchanged=true`).

## 17. Updated G2 manual results

Exactly five post-fix actual-output cases passed 5/5. The four supported cases prove real RAG plus real LLM without fallback; generic Glucose proves the intentional fail-closed path and is not falsely claimed as an LLM case. Pre-fix failed/fallback evidence remains separately preserved.

Evidence: `eval/manual/pre_rag_fix/`, `eval/manual/post_rag_fix/`, and `eval/manual/manual_e2e_summary.md`.

## 18. Known limitations

- API response schema does not expose internal retrieved contexts, so direct production-retriever evidence is correlated with API timing events.
- The live retrieval check covers WBC, Potassium, and FPG plus three negative filters; it is a sanity check, not a full relevance benchmark.
- Retained OCR, RAGAS, and 20-request latency results were intentionally not rerun because the derived-index rebuild did not invalidate them.
- Existing ingestion tooling generates current IDs for a new collection but an in-place upsert does not remove orphaned legacy IDs. Future canonical-catalog migrations should use a clean/versioned full rebuild.

## 19. Final disposition

The G2 blocker is removed using a full derived-index rebuild. All required live probes, supported real API RAG/LLM flows, deterministic medical regressions, Fix2 negatives, and protected-file checks pass. No compatibility mapping or medical-rule change was required.

`READY_FOR_G2_MANUAL_RETEST = YES`  
`G2_CORE_REAL_LLM_FLOW_PROVEN = YES`  
`G2_MANUAL_ACTUAL_OUTPUT_CASE_COUNT = 5`  
`G2_EVALUATION_PACKAGE_READY = YES`
