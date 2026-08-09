# P-056 RAGAS V2 Baseline Report

## Run metadata
- Run ID: RAGAS-V2-BASELINE-001
- Generated at: 2026-08-09T04:58:18.295593+00:00
- Git commit: 02ae58b579a48f852635b576627aa2e6b06d1863
- Live passes: 1

## Security and credential handling
- Credential variable: GOOGLE_API_KEY
- Key value logged: NO
- Authorization headers stored: NO
- OpenAI service used: NO

## Dataset scope
- Dataset: eval/datasets/ragas_v2_baseline.jsonl
- Dataset SHA-256: fea4662074a740025260ccaf4146cc797124af973613c90df0d869a8b2444a0c
- This evaluates curated fixtures, not retrieved contexts captured from the production graph.
- Approved analytes: WBC, RBC, Fasting plasma glucose, Creatinine, HGB, HbA1c, LDL-C, HDL-C, Potassium.
- Pending analytes are excluded.

## Evaluator configuration
- Provider: google
- Model: gemini-2.5-flash
- Transport adapter: google_openai_compatible
- Transport library: openai-python
- API endpoint host: generativelanguage.googleapis.com
- RAGAS version: 0.4.3
- Compatibility shim applied: True
- Concurrency: 1
- Automatic retries: 0

## Metrics
- Faithfulness
- Context Precision
- custom_hallucination_proxy = 1 - faithfulness

## Aggregate results
| Metric | Count | Mean | Median | Min | Max | Std dev | Failed | N/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Faithfulness | 20 | 0.875000 | 1.000000 | 0.333333 | 1.000000 | 0.222829 | 6 | 1 |
| Context Precision | 25 | 0.940000 | 1.000000 | 0.000000 | 1.000000 | 0.215407 | 1 | 1 |
| Custom hallucination proxy | 20 | 0.125000 | 0.000000 | 0.000000 | 0.666667 | 0.222829 | 6 | 1 |

## Per-case results
| Case | Analyte | Faithfulness | Context Precision | Hallucination proxy | Status |
|---|---|---:|---:|---:|---|
| RAGAS-V2-001 | WBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-002 | WBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-003 | WBC | 0.500000 | 1.000000 | 0.500000 | success |
| RAGAS-V2-004 | RBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-005 | RBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-006 | RBC |  |  |  | failed |
| RAGAS-V2-007 | Fasting plasma glucose | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-008 | Fasting plasma glucose | 0.333333 | 1.000000 | 0.666667 | success |
| RAGAS-V2-009 | Fasting plasma glucose | 1.000000 | 0.500000 | 0.000000 | success |
| RAGAS-V2-010 | Creatinine | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-011 | Creatinine | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-012 | WBC |  |  |  | not_applicable |
| RAGAS-V2-013 | HGB | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-014 | HGB |  | 1.000000 |  | partial_failure |
| RAGAS-V2-015 | HGB | 0.500000 | 1.000000 | 0.500000 | success |
| RAGAS-V2-016 | HbA1c | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-017 | HbA1c | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-018 | HbA1c | 0.500000 | 1.000000 | 0.500000 | success |
| RAGAS-V2-019 | LDL-C | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-020 | LDL-C |  | 1.000000 |  | partial_failure |
| RAGAS-V2-021 | LDL-C | 0.666667 | 0.000000 | 0.333333 | success |
| RAGAS-V2-022 | HDL-C | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-023 | HDL-C |  | 1.000000 |  | partial_failure |
| RAGAS-V2-024 | HDL-C |  | 1.000000 |  | partial_failure |
| RAGAS-V2-025 | Potassium | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-026 | Potassium |  | 1.000000 |  | partial_failure |
| RAGAS-V2-027 | Potassium | 1.000000 | 1.000000 | 0.000000 | success |

## Expected-pattern checks
- Unsupported-claim contrast: True
- Relevant-first context contrast: True
- Warnings: []
- Dataset or prompt tuning performed: NO

## Failures and not-applicable cases
- Partial cases: 5
- Failed cases: 1
- Not applicable cases: 1
- RAGAS-V2-012 is not applicable because retrieved_contexts is empty.

## Limitations
- Results are not clinical validation.
- Results are not production RAG validation.
- One live pass was executed; scores may vary across repeated evaluator runs.
- No threshold optimization was performed.

## Reproduction command
`python -B -m eval.run_ragas --dataset eval/datasets/ragas_v2_baseline.jsonl --live --provider google --model gemini-2.5-flash --max-cases 27 --confirm-key-rotated --skip-probe-after-confirmed --output eval/results/ragas_v2_baseline.json`

## Interpretation boundaries
- This is a curated-fixture baseline for eval plumbing and metric visibility.
- Do not use these scores as a clinical accuracy claim.

## Recommendation
- Use this baseline as the first live RAGAS reference point for later Contractor-approved comparison.
