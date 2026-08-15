# VMEC-05 G2 post-reconciliation live RAG sanity

This is a live filtered-retrieval sanity check, not a RAGAS score.

| Probe | Canonical ID | Chunks | Correct analyte text | Result |
|---|---|---:|---|---|
| WBC normal | `wbc` | 1 | Yes — `Chỉ số: WBC` | PASS |
| Potassium normal | `potassium` | 1 | Yes — `Chỉ số: Potassium` | PASS |
| Fasting plasma glucose low | `fasting_plasma_glucose` | 1 | Yes — `Chỉ số: Fasting plasma glucose` | PASS |

Collection `medical_kb_v1` contains 9 documents and uses OpenAI `text-embedding-3-small` embeddings with dimension 1536. Machine-readable text, metadata, sources, scores, and the correlated API probe are in `live_rag_sanity.json`.
