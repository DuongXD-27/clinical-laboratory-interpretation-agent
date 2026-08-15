# VMEC-05 G2 RAGAS scope note

This note reuses the existing completed baseline; no RAGAS job was rerun.

`RAGAS_VERSION = 0.4.3`  
`CASE_COUNT = 27`  
`FAITHFULNESS = 0.875000`  
`CONTEXT_PRECISION = 0.940000`  
`CONTEXT_SOURCE = CURATED_RETRIEVED_CONTEXT_FIXTURES`  
`LIVE_PRODUCTION_RETRIEVAL_VALIDATED = NO`

| Item | Existing result |
|---|---|
| Run ID | `RAGAS-V2-BASELINE-001` |
| Run date | `2026-08-09T04:58:18.295593+00:00` |
| RAGAS version | 0.4.3 |
| Dataset cases | 27 |
| Metrics | Faithfulness; Context Precision; custom hallucination proxy |
| Faithfulness | 0.875000 mean (20 scored; 6 failed; 1 N/A) |
| Context Precision | 0.940000 mean (25 scored; 1 failed; 1 N/A) |
| Evaluator | Google `gemini-2.5-flash` |

The existing RAGAS evaluation measures grounded generation quality against curated retrieved-context fixtures. It does not by itself validate live production retrieval.

`EXISTING_RAGAS_CONTEXT_SOURCE = CURATED_FIXTURES`  
`PRODUCTION_RETRIEVAL_VALIDATED_BY_THIS_RUN = NO`

Source evidence: `eval/results/report.md`, `eval/results/ragas_v2_baseline.json`, and `eval/results/ragas_v2_baseline.csv`.
