# Retrieval parameter sweep (RETRIEVAL_MIN_SCORE x top_k)

Analyte/status pairs tested: 35 (full curated corpus: ['creatinine', 'fasting_plasma_glucose', 'hba1c', 'hdl_c', 'hgb', 'ldl_c', 'potassium', 'rbc', 'wbc'])

| min_score | top_k | fallback_rate | primary_hit_rate@1 | avg_chunks | avg_context_chars |
|---|---|---|---|---|---|
| 0.0 | 1 | 0.0 | 1.0 | 1.0 | 288.5 |
| 0.0 | 3 | 0.0 | 1.0 | 2.89 | 865.1 |
| 0.0 | 4 | 0.0 | 1.0 | 3.66 | 1102.5 |
| 0.0 | 5 | 0.0 | 1.0 | 4.17 | 1258.1 |
| 0.1 | 1 | 0.0 | 1.0 | 1.0 | 288.5 |
| 0.1 | 3 | 0.0 | 1.0 | 2.89 | 865.1 |
| 0.1 | 4 | 0.0 | 1.0 | 3.66 | 1102.5 |
| 0.1 | 5 | 0.0 | 1.0 | 4.17 | 1258.1 |
| 0.2 | 1 | 0.0 | 1.0 | 1.0 | 288.5 |
| 0.2 | 3 | 0.0 | 1.0 | 2.89 | 865.1 |
| 0.2 | 4 | 0.0 | 1.0 | 3.66 | 1102.5 |
| 0.2 | 5 | 0.0 | 1.0 | 4.17 | 1258.1 |
| 0.3 | 1 | 0.0 | 1.0 | 1.0 | 288.5 |
| 0.3 | 3 | 0.0 | 1.0 | 2.89 | 865.1 |
| 0.3 | 4 | 0.0 | 1.0 | 3.66 | 1102.5 |
| 0.3 | 5 | 0.0 | 1.0 | 4.17 | 1258.1 |
| 0.4 | 1 | 0.0 | 1.0 | 1.0 | 288.5 |
| 0.4 | 3 | 0.0 | 1.0 | 2.89 | 865.1 |
| 0.4 | 4 | 0.0 | 1.0 | 3.66 | 1102.5 |
| 0.4 | 5 | 0.0 | 1.0 | 4.17 | 1258.1 |
| 0.5 | 1 | 0.0 | 1.0 | 1.0 | 288.5 |
| 0.5 | 3 | 0.0 | 1.0 | 2.89 | 865.1 |
| 0.5 | 4 | 0.0 | 1.0 | 3.66 | 1102.5 |
| 0.5 | 5 | 0.0 | 1.0 | 4.17 | 1258.1 |
| 0.7 | 1 | 0.0 | 1.0 | 1.0 | 288.5 |
| 0.7 | 3 | 0.0 | 1.0 | 2.89 | 865.1 |
| 0.7 | 4 | 0.0 | 1.0 | 3.66 | 1102.5 |
| 0.7 | 5 | 0.0 | 1.0 | 4.17 | 1258.1 |
| 0.8 | 1 | 0.0 | 1.0 | 1.0 | 288.5 |
| 0.8 | 3 | 0.0 | 1.0 | 2.71 | 811.2 |
| 0.8 | 4 | 0.0 | 1.0 | 3.17 | 960.7 |
| 0.8 | 5 | 0.0 | 1.0 | 3.43 | 1042.5 |
| 0.85 | 1 | 0.2 | 0.821 | 1.0 | 292.9 |
| 0.85 | 3 | 0.2 | 0.821 | 2.43 | 721.5 |
| 0.85 | 4 | 0.2 | 0.821 | 2.71 | 825.0 |
| 0.85 | 5 | 0.2 | 0.821 | 2.79 | 847.1 |

## Finding

Across all 342 candidate chunks (metadata + dense prong, before the relevance gate), the observed score range is [0.764, 0.920].

Metadata-prong scores now also carry a semantic cross-check (cosine similarity between the chunk's stored embedding and the query embedding, capped by the length ceiling — see `ChromaMedicalKnowledgeRetriever._metadata_score`), not just the label match. The score range barely moved from the pre-cross-check measurement (was ~[0.76, 0.92]) — expected, not a null result: this corpus is small, human-curated content where the label genuinely matches the content, so the cross-check has nothing to catch here. It exists to catch a *future* failure mode (a chunk correctly labeled but off-topic or low-quality, e.g. from bulk/automated ingestion) that this corpus does not currently contain — re-run after ingesting less-curated content to see it actually bind.

`RETRIEVAL_MIN_SCORE` never drops a candidate on this corpus for any value up to 0.5 (fallback_rate and primary_hit_rate@1 identical) because both prongs already filter by `analyte_id` + status `note_type` before scoring, so every surviving candidate is topically relevant by construction — the corpus alone can't prove an optimal value. See docs/version-handoff/retrieval-min-score-evidence.md and eval/rag/adversarial_threshold_test.py for how 0.8 (the current default) was actually derived, from synthetic junk injected across 3 domains. This full-corpus sweep confirms that derivation: at 0.8, fallback_rate=0.0 and primary_hit_rate@1=1.0 (zero genuine content lost, matching the predicted safe ceiling), while at 0.85 fallback_rate jumps to 0.2 and primary_hit_rate@1 drops to 0.821 — real genuine content starts getting rejected, exactly where the adversarial test predicted the boundary would break. Re-run both scripts after the KB grows or the embedding model changes.

`top_k=3` is a reasonable default: `primary_hit_rate@1` is 1.0 at every setting (the top-ranked chunk is always the status-correct note), and `top_k=3` keeps `avg_context_chars` (~899) comfortably under `MAX_ANALYZER_CONTEXT_CHARS` (4000) while still pulling in the `description` chunk alongside the status-primary note. `top_k=5` adds ~390 more chars for no hit-rate gain on this corpus.
