# VMEC-05 G2 post-reconciliation live RAG sanity

This is a live filtered-retrieval sanity check, not a RAGAS score.

`RAG_ENABLED = true`  
`CHROMA_COLLECTION = medical_kb_v1`  
`CHROMA_DOCUMENT_COUNT = 9`  
`EMBEDDING_PROVIDER = openai`  
`EMBEDDING_MODEL = text-embedding-3-small`  
`EMBEDDING_DIMENSION = 1536`

| Probe | Canonical ID | Chunks | Correct analyte text | Result |
|---|---|---:|---|---|
| WBC normal | `wbc` | 1 | Yes — `Chỉ số: WBC` | PASS |
| Potassium normal | `potassium` | 1 | Yes — `Chỉ số: Potassium` | PASS |
| Fasting plasma glucose low | `fasting_plasma_glucose` | 1 | Yes — `Chỉ số: Fasting plasma glucose` | PASS |

The configured production retriever used live OpenAI embeddings and exact `analyte_id` filters. A correlated WBC API probe also returned HTTP 200 and successful RAG/LLM events. `AnalyzeResponse` does not expose internal retrieved contexts, so text, metadata, source URLs, and scores are captured directly in the machine-readable artifact.

Pre-fix evidence is preserved under `eval/rag/pre_rag_fix/`; post-fix evidence is under `eval/rag/post_rag_fix/`.

`LIVE_RAG_RETRIEVAL_VERIFIED = YES`

Machine-readable evidence: `eval/rag/live_rag_sanity.json`.
