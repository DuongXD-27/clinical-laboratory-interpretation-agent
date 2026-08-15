# VMEC-05 G2 real-LLM latency evaluation

Configuration: 20 sequential calls to `POST /api/v1/analyze`, guest session, WBC `7.0 10^9/L`, OpenAI-compatible `ChatOpenAI`, model `gpt-4o-mini`. Each request has `llm-explanation-call outcome=success`; no request used the curated explanation fallback.

**RAG_ENABLED during latency run = true.** The currently configured Chroma collection was used, and every request recorded a `rag-call` component.

| Metric | N | Mean (ms) | P50/median (ms) | P95 nearest-rank (ms) | Min (ms) | Max (ms) |
|---|---:|---:|---:|---:|---:|---:|
| HTTP total | 20 | 1956.764 | 1953.976 | 2470.609 | 1452.120 | 2680.074 |
| LLM explanation call | 20 | 1581.658 | 1571.875 | 2021.770 | 1135.647 | 2276.888 |

- Successful requests: 20/20.
- `rag_call_ms`: available for 20/20 requests and preserved per request in the JSON artifact.
- `guardrail_rewrite_ms`: unavailable/not invoked for all 20 requests; no value was invented.
- Raw request-level evidence: `eval/performance/latency_20_requests.json`.
