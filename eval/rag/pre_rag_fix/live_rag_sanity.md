# VMEC-05 G2 live RAG retrieval sanity

This is a live retrieval sanity check, not a RAGAS score.

`RAG_ENABLED = true`  
`CHROMA_COLLECTION_EXISTS = YES`  
`CHROMA_COLLECTION = medical_kb_v1`  
`CHROMA_DOCUMENT_COUNT = 9`  
`EMBEDDING_PROVIDER = openai`  
`EMBEDDING_MODEL = text-embedding-3-small`

| Probe | Current analyte ID | Chunks | Result |
|---|---|---:|---|
| WBC normal | `wbc` | 1 | Non-empty live retrieval |
| Potassium normal | `potassium` | 0 | Empty; collection stores legacy `kali` ID |
| Fasting plasma glucose low | `fasting_plasma_glucose` | 0 | Empty; collection stores legacy `glucose` ID |

The WBC chunk contained a safe excerpt beginning “Chỉ số: White Blood Cell Count (WBC - Số lượng bạch cầu)” with source metadata including MedlinePlus, Mayo Clinic, and Medlatec, and retrieval score `0.613823652267456`.

The correlated real API probe returned HTTP 200 (`request_id=05b8db25ea7349df80d43b37e69a0d9e`) and logged both `rag-call outcome=success` and `llm-explanation-call outcome=success` for `wbc`.

Current `AnalyzeResponse` does not expose internal `retrieved_contexts`, so chunk text/metadata were captured directly from the production `MedicalKnowledgeRetriever` using the same configured collection/provider. No `RAG_ENABLED=false` A/B API run was performed.

`LIVE_RAG_RETRIEVAL_VERIFIED = YES` for the populated collection and WBC path. This does not remove the Potassium/FPG ID-mismatch blocker.

Machine-readable evidence: `eval/rag/live_rag_sanity.json`.
