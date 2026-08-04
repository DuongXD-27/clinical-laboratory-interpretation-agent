# TIP-004A RAGAS SCAFFOLD REPORT

## Baseline
- Repository: F:\VIN_AI_PROJECT\P-056
- Branch: feature/TQT-reference-ragas
- Start commit: d8076a4e3ff93ff70b8144b9f5d0b449f209502c
- Working tree at initial preflight: clean
- Previous blocked state: requirements.txt contained the authorized ragas==0.4.3 pin after install attempt

## Dependency decision
- Approved dependency pin: ragas==0.4.3
- No ragas-experimental, GitHub development version, prerelease version, unpinned ragas, Vertex AI package, or Google Cloud package was added.
- requirements.txt was modified only by adding ragas==0.4.3.

## Dependency dry-run result
- Dry-run completed before installation.
- Proposed new packages included ragas, datasets, pyarrow, pandas, pillow, diskcache, appdirs, instructor, langchain-community, langchain-classic, and supporting packages.
- Resolver-selected indirect package changes: fsspec 2026.7.0 to 2026.6.0, jiter 0.16.0 to 0.14.0, rich 15.0.0 to 14.3.4.
- No FastAPI, Pydantic, LangGraph, or production package downgrade was proposed.
- No dependency conflict was reported by pip.

## Installed RAGAS version
- ragas: 0.4.3
- langchain: 1.3.14
- langchain-core: 1.5.1
- langchain-community: 0.4.2
- fsspec: 2026.6.0
- jiter: 0.14.0
- rich: 14.3.4

## Pip check
- Result: No broken requirements found.

## RAGAS API verified
- Direct unbootstrapped import result before compatibility: failed with ModuleNotFoundError for langchain_community.chat_models.vertexai.
- Root cause: ragas 0.4.3 imports optional legacy Vertex AI symbols during package initialization.
- Compatibility file: eval/ragas_compat.py
- Compatibility behavior: registers minimal inert placeholder classes for the missing legacy Vertex AI import path before importing RAGAS.
- Shim applied in this environment: true.
- SingleTurnSample: available through import_ragas_api().
- EvaluationDataset: available through import_ragas_api().
- Faithfulness: available through import_ragas_api().
- ContextPrecision: available through import_ragas_api().
- The shim is not Vertex AI support and raises a clear error if a placeholder is instantiated.

## Dataset scope
- Dataset: eval/datasets/ragas_v2_baseline.jsonl
- Metadata: eval/datasets/ragas_v2_baseline.meta.json
- Dataset version: v2-baseline-1
- Case count: 12
- Language: Vietnamese
- Scope: approved normal-reference analytes only
- Live evaluation status: not_run
- Contains real patient data: false

## Dataset case matrix
| Case | Analyte | Purpose |
|---|---|---|
| RAGAS-V2-001 | WBC | Normal, supported |
| RAGAS-V2-002 | WBC | High, supported |
| RAGAS-V2-003 | WBC | Unsupported harmless claim |
| RAGAS-V2-004 | RBC | Male-specific RI |
| RAGAS-V2-005 | RBC | Female-specific RI |
| RAGAS-V2-006 | RBC | Wrong-sex context before relevant context |
| RAGAS-V2-007 | Fasting plasma glucose | RI-only authority |
| RAGAS-V2-008 | Fasting plasma glucose | Relevant context first |
| RAGAS-V2-009 | Fasting plasma glucose | Irrelevant context first |
| RAGAS-V2-010 | Creatinine | Adult lower boundary |
| RAGAS-V2-011 | Creatinine | Adult upper boundary |
| RAGAS-V2-012 | WBC | Missing retrieved context |

## Approved analytes
- WBC
- RBC
- Fasting plasma glucose
- Creatinine

## Excluded analytes
- HGB: unit_data_conflict
- HDL-C: cdl_only
- HbA1c: md_not_approved
- LDL-C: md_not_approved
- Potassium: normal_reference_not_approved

## Retrieved-context origin
- Curated evaluation fixtures derived from existing project explanation and reference records.
- Contexts are not claimed as retrieved from the live graph.
- Runtime graph still does not expose retrieved context text.

## Validation command
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m eval.run_ragas --dataset eval/datasets/ragas_v2_baseline.jsonl --validate-only

## Validation result
- Dataset: v2-baseline-1
- Cases: 12
- Approved analytes: 4
- Pending analytes used: 0
- PII check: PASS
- RAGAS dataset construction: PASS
- Faithfulness API available: PASS
- ContextPrecision API available: PASS
- Live evaluation executed: NO

## Test commands
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_eval\test_ragas_compat.py -q -rxX -p no:cacheprovider
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_eval\test_ragas_v2_dataset.py -q -rxX -p no:cacheprovider
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_eval\test_ragas_runner.py -q -rxX -p no:cacheprovider
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_data\test_v2_analyte_manifest.py -q -rxX -p no:cacheprovider
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests -q -rxX -p no:cacheprovider --ignore=tests/test_embed.py
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m compileall -q src eval tests

## Test results
- Compatibility tests: 10 passed
- Dataset tests: 13 passed
- Runner tests: 14 passed
- Manifest tests: 13 passed
- Full safe suite: 183 passed, 1 warning
- Compile: passed
- pip check: No broken requirements found

## No-live-evaluation evidence
- eval/run_ragas.py supports --validate-only and --inspect only.
- --live returns exit code 3 and does not evaluate.
- Tests patch network entry points and API-key environment access for offline validation paths.
- No Faithfulness, Context Precision, hallucination, hallucination_proxy, or score fields are generated.

## Manifest update
- ragas_case_available set to true for WBC, RBC, Fasting plasma glucose, and Creatinine.
- ragas_case_available remains false for HGB, HDL-C, HbA1c, LDL-C, and Potassium.
- Manifest tests verify dataset coverage and manifest flags agree.

## Protected-file integrity
- No production src files changed.
- No data/reference files changed.
- No graph/state/analyzer/retriever/API/schema files changed.
- eval/results/report.md was not changed.
- .env and .env.example were not changed.

## Known limitations
- Direct unbootstrapped import ragas may still fail in this environment because ragas 0.4.3 imports a removed legacy Vertex AI path.
- The compatibility shim is intentionally narrow and only supports offline import compatibility.
- No live metric scores exist.
- Dataset contexts are curated fixtures, not live retrieved contexts.

## TIP-004B prerequisites
- Evaluator provider not yet selected.
- Evaluator model not yet selected.
- API budget not yet approved.
- Live metric scores do not exist.
- Runtime graph still does not expose retrieved contexts.
- Live baseline will evaluate curated fixtures unless Vu approves a graph/state contract change.
- Faithfulness and Context Precision are intended.
- hallucination_proxy will be custom and defined as 1 - faithfulness.
- No claim of production RAG quality may be made from TIP-004A.

## Shim removal criteria
- A future pinned RAGAS release no longer imports the removed legacy path.
- The four required RAGAS classes import without bootstrap.
- All eval tests pass after removing the shim.
- Dependency impact is reviewed in a separate TIP.

## Recommendation
- Continue to TIP-004B only after Contractor authorization and a manual live-evaluation gate.
