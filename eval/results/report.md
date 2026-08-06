# P-056 RAGAS V2 Baseline Report

## Run metadata
- Run ID: RAGAS-V2-BASELINE-001
- Generated at: 2026-08-05T02:49:11.567920+00:00
- Git commit: 01205af4aade3440b04f008762369d6d69873a77
- Live passes: 1

## Security and credential handling
- Credential variable: GOOGLE_API_KEY
- Key value logged: NO
- Authorization headers stored: NO
- OpenAI service used: NO

## Dataset scope
- Dataset: eval/datasets/ragas_v2_baseline.jsonl
- Dataset SHA-256: 3f1cb84cebde5a5a47fca5eafca0a0276ebe6c04665fd9bb0531fe92ea24da2f
- This evaluates curated fixtures, not retrieved contexts captured from the production graph.
- Approved analytes only: WBC, RBC, Fasting plasma glucose, Creatinine.
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
| Faithfulness | 11 | 0.909091 | 1.000000 | 0.500000 | 1.000000 | 0.192847 | 0 | 1 |
| Context Precision | 11 | 0.954545 | 1.000000 | 0.500000 | 1.000000 | 0.143740 | 0 | 1 |
| Custom hallucination proxy | 11 | 0.090909 | 0.000000 | 0.000000 | 0.500000 | 0.192847 | 0 | 1 |

## Per-case results
| Case | Analyte | Faithfulness | Context Precision | Hallucination proxy | Status |
|---|---|---:|---:|---:|---|
| RAGAS-V2-001 | WBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-002 | WBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-003 | WBC | 0.500000 | 1.000000 | 0.500000 | success |
| RAGAS-V2-004 | RBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-005 | RBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-006 | RBC | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-007 | Fasting plasma glucose | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-008 | Fasting plasma glucose | 0.500000 | 1.000000 | 0.500000 | success |
| RAGAS-V2-009 | Fasting plasma glucose | 1.000000 | 0.500000 | 0.000000 | success |
| RAGAS-V2-010 | Creatinine | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-011 | Creatinine | 1.000000 | 1.000000 | 0.000000 | success |
| RAGAS-V2-012 | WBC |  |  |  | not_applicable |

## Expected-pattern checks
- Unsupported-claim contrast: True
- Relevant-first context contrast: True
- Warnings: []
- Dataset or prompt tuning performed: NO

## Failures and not-applicable cases
- Partial cases: 0
- Failed cases: 0
- Not applicable cases: 1
- RAGAS-V2-012 is not applicable because retrieved_contexts is empty.

## Limitations
- Results are not clinical validation.
- Results are not production RAG validation.
- One live pass was executed; scores may vary across repeated evaluator runs.
- No threshold optimization was performed.

## Reproduction command
`python -B -m eval.run_ragas --dataset eval/datasets/ragas_v2_baseline.jsonl --live --provider google --model gemini-2.5-flash --max-cases 12 --confirm-key-rotated --skip-probe-after-confirmed --output eval/results/ragas_v2_baseline.json`

## Interpretation boundaries
- This is a curated-fixture baseline for eval plumbing and metric visibility.
- Do not use these scores as a clinical accuracy claim.

## Recommendation
- Use this baseline as the first live RAGAS reference point for later Contractor-approved comparison.
