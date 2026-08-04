# SCAN REPORT — TUAN V2

## 1. Scan metadata
- Date/time: 2026-08-04 21:17:53 +07:00
- Repository: `F:\VIN_AI_PROJECT\P-056` (`git rev-parse --show-toplevel` -> `F:/VIN_AI_PROJECT/P-056`)
- Branch: `feature/TQT-reference-ragas`
- Baseline commit: `8fb263ea3043476a92aecc41b9c40e4ea7828239`
- Working tree status: clean at scan start (`git status --short` returned no entries). Existing dirty state before TIP-000: NO.
- Active Python environment: PATH `python` is unavailable; project parent virtualenv used for inspection: `F:\VIN_AI_PROJECT\.venv\Scripts\python.exe`, Python `3.12.3`.

Git evidence:
- Latest commits:
  - `8fb263e Merge pull request #13 from AI20K-Build-Phase-Cohort-3/feature/start-v2.0`
  - `17aaf8c docs(kickoff): kickoff for v2.0`
  - `76dedf6 Merge pull request #12 from AI20K-Build-Phase-Cohort-3/bugfix/state`
  - `304b5f3 fix: add category field and fix guardrail docstring`
  - `c07c259 Merge pull request #11 from AI20K-Build-Phase-Cohort-3/docs/adr`
- Start status: no modified, staged, or untracked files reported by `git status --short`.
- Note: baseline API tests touched ignored runtime vector-store data under `data/chroma/` (`git status --short --ignored data/chroma` -> `!! data/chroma/`). It is ignored by `.gitignore` and not tracked by `git ls-files data/chroma`.

## 2. Tech stack
- Language: Python 3.11+ documented in `README.md`; active virtualenv is Python 3.12.3. `ruff.toml` targets `py311`.
- Framework: FastAPI app in `src/main.py`; installed `fastapi 0.140.0`, `uvicorn 0.51.0`.
- Data/schema libraries: Pydantic `2.13.4`, pydantic-settings `2.14.2`.
- Agent framework: LangGraph `1.2.9`; graph defined in `src/agents/graph.py`.
- Test framework: pytest `9.1.1`, pytest-asyncio `1.4.0`, httpx `0.28.1`.
- RAGAS version: `not installed in the active environment`; `requirements.txt` does not list `ragas`.
- Other relevant dependencies: LangChain `1.3.14`, langchain-google-genai `4.3.2`, langchain-openai `1.4.1`, langchain-huggingface `1.2.2`, ChromaDB `1.5.9`, Ruff `0.16.0`.
- RAG framework: custom ChromaDB wrapper in `src/services/vector_store.py` using `HuggingFaceEmbeddings(model_name="BAAI/bge-m3")`; analyzer uses LangChain messages and Gemini chat model.
- Main application entry point: `src/main.py` (`app = FastAPI(...)`).
- Local run command: `uvicorn src.main:app --reload` from `README.md`; `make run` uses `uvicorn src.main:app --reload --host 0.0.0.0 --port 8000`.
- Test commands documented: `pytest tests/ -v` in `Makefile`; `python -m pytest tests/test_embed.py -v -s` documented inside `tests/test_embed.py`.
- Required environment variable names observed: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_KEY`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `CHROMA_PERSIST_DIR`, `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT`, `APP_ENV`, `APP_PORT`, `APP_HOST`, `CORS_ORIGINS`, `CRITICAL_THRESHOLDS_PATH`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_TRACING_V2`, `LOG_LEVEL`, `AI_LOG_SERVER`, `AI_LOG_API_KEY`, `AI_LOG_DIR`, `NEXT_PUBLIC_API_URL`. Values were not recorded.
- Manifest evidence: no `pyproject.toml`, no `requirements-dev.txt`, and no backend lockfile found at repository root. Frontend has `frontend/package-lock.json`.

## 3. Relevant directory tree

```text
F:\VIN_AI_PROJECT\P-056
|-- adult_outpatient_laboratory_reference_map.csv
|-- requirements.txt
|-- ruff.toml
|-- Makefile
|-- README.md
|-- src/
|   |-- config.py
|   |-- main.py
|   |-- agents/
|   |   |-- graph.py
|   |   |-- state.py
|   |   |-- nodes/
|   |   |   |-- analyzer_node.py
|   |   |   |-- critical_detector_node.py
|   |   |   |-- guardrail_node.py
|   |   |   `-- reference_range_checker_node.py
|   |   `-- tools/
|   |       `-- example_tool.py
|   |-- api/
|   |   `-- routes.py
|   |-- models/
|   |   `-- schemas.py
|   |-- scripts/
|   |   |-- ingest_kb.py
|   |   `-- test_analyze.py
|   `-- services/
|       |-- llm.py
|       `-- vector_store.py
|-- tests/
|   |-- conftest.py
|   |-- test_embed.py
|   |-- test_agents/
|   |   |-- test_critical_detector_node.py
|   |   |-- test_graph.py
|   |   `-- test_guardrail_node.py
|   `-- test_api/
|       `-- test_routes.py
|-- data/
|   |-- data.md
|   |-- chroma/                  # ignored runtime ChromaDB data
|   |-- reference/
|   |   |-- critical_thresholds.json
|   |   |-- explanations.json
|   |   |-- metrics_range.csv
|   |   |-- metrics_range.json
|   |   `-- units_metric.csv
|   `-- mock/
|       |-- generated/
|       `-- templates/
|-- eval/
|   `-- results/
|       `-- report.md
|-- docs/
|   |-- architecture/
|   |-- architecture-decision-record/
|   |-- guide/
|   |-- version-handoff/
|   `-- version-kickoff/
`-- scripts/
```

Generated/noisy directories such as `.git`, `.venv`, `__pycache__`, `.pytest_cache`, frontend build output, and node modules were excluded from conclusions.

## 4. Existing modules
### Reference Range Checker
- File: `src/agents/nodes/reference_range_checker_node.py`.
- Entry point: `async def reference_range_checker_node(state: AgentState) -> dict` at line 27.
- Data source: `data/reference/explanations.json` loaded by `load_explanations()` lines 8-16 and cached as `EXPLANATIONS_DB` line 17.
- Consumes `raw_indicators` and `patient_gender` from state at lines 29-30.
- Produces `indicators` list at return lines 104-106.
- It is config-file backed by `explanations.json`, but not by the richer `metrics_range.*` source. Range logic is embedded in the node.

### Critical Detector
- File: `src/agents/nodes/critical_detector_node.py`.
- Entry point: `async def detect_critical_values_node(state: AgentState) -> dict` at line 20.
- Threshold source: `settings.critical_thresholds_path`, default `./data/reference/critical_thresholds.json` from `src/config.py:38`; loaded at `critical_detector_node.py:8-18`.
- Produces `indicators`, `critical_alerts`, and `has_critical_values` at lines 92-95.
- ADR evidence: `docs/architecture-decision-record/adr-003-critical-value-detection.md` requires rule-based critical thresholds in a separate file.

### Schemas
- API schemas: `src/models/schemas.py`.
- Graph state contracts: `src/agents/state.py`.
- `IndicatorAssessment` is a `TypedDict(total=False)` at `state.py:16`; Pydantic response model is `IndicatorResultSchema` at `schemas.py:34`.

### Graph and State contracts
- Graph file: `src/agents/graph.py`.
- Current node order: `reference_range_checker -> critical_detector -> analyzer -> guardrail -> END` (`graph.py:14-24`).
- State file: `src/agents/state.py`; `AgentState` is `TypedDict(total=False)` at line 65.
- No graph/state modifications were made.

### API
- Main app: `src/main.py`; includes router under `/api/v1`.
- Analyze route: `src/api/routes.py:9`, response model `AnalyzeResponse`.
- Route maps request fields into `initial_state` at `routes.py:16-22`, invokes graph at `routes.py:25`, and serializes indicators through `IndicatorResultSchema` at `routes.py:28-30`.

### RAG and Guardrail
- RAG generation path is inside `src/agents/nodes/analyzer_node.py`.
- Analyzer uses `get_vector_store()` and `vector_store.search(query=name, k=1)` at `analyzer_node.py:43` and `68`.
- Vector store uses ChromaDB PersistentClient and BAAI/bge-m3 embeddings at `src/services/vector_store.py:30-41`.
- LLM integration uses `ChatGoogleGenerativeAI` in `src/services/llm.py:1-11`.
- Guardrail node: `src/agents/nodes/guardrail_node.py`; it scans generated explanations and summary for restricted phrases and supplies a default disclaimer.

### Evaluation
- Existing evaluation artifact: `eval/results/report.md`, a placeholder report with empty metrics.
- No production RAGAS code found.
- RAGAS is mentioned in guide/kickoff docs but absent from dependencies and active environment.

## 5. Existing patterns
- Config loading: `pydantic-settings` `BaseSettings` in `src/config.py`; `.env` file configured via `SettingsConfigDict`.
- Schema validation: FastAPI + Pydantic for API request/response; graph state uses `TypedDict(total=False)`.
- Error handling: analyzer catches LLM/vector-store setup and call failures, logs errors, and falls back to `"Hệ thống đang bận, vui lòng thử lại."`; route intentionally does not catch exceptions (`src/api/routes.py:10-13`).
- Testing: pytest with `pytest.mark.asyncio`; fixtures in `tests/conftest.py`; no parameterized tests found.
- Source attribution: `explanations.json` contains `sources`; `src/scripts/ingest_kb.py:48-49` stores sources metadata into Chroma; analyzer asks structured LLM output to return `sources` and writes them back to indicators at `analyzer_node.py:128` and `142-148`.

## 6. Reference input inventory

| File | Type | Rows | SHA-256 | Role |
|---|---|---:|---|---|
| `adult_outpatient_laboratory_reference_map.csv` | CSV | 80 | `721A07EA6EC8BC202DAD4F23808ECA34853A146E41E3EC3AE04EC66EABDA7D6B` | Primary V2 source candidate; rich source map with `range_flag`, confidence, source tier, URL, type, age/sex/unit metadata |
| `data/reference/metrics_range.csv` | CSV | 80 | `D7D8E960E004CB98DC5B4794ECDEF08CFE4A78835A430E83335B81EAD629DFE1` | Existing generated/reference runtime-style range table; no `range_flag` or `confidence` |
| `data/reference/units_metric.csv` | CSV | 38 | `30E83F1123E5F094042C44136DC7927B7FFE73BF6096EAF1CD11D65FB84494F4` | Existing unit reference list; no range/source metadata |
| `data/reference/metrics_range.json` | JSON list | 80 | `B8BF5BF7457142875F7A517FBAF4DABA9C3B5941F80C18A35E5625CA7B341676` | JSON equivalent of `metrics_range.csv`; likely generated runtime/reference artifact |
| `data/reference/explanations.json` | JSON list | 9 | `8C0C29CF6F3B489B0467FCA58980542EC1958A10D6685C001FBBAB6E18929A4E` | Current checker and RAG KB source; includes explanations, reference ranges, source lists |
| `data/reference/critical_thresholds.json` | JSON object | 5 top-level keys | `8E419CFAD0A8522F6A1DEFBA6A36161D470622CE67A2788852B29ABB668AF53D` | Protected critical threshold policy |

Primary source header:
`section, analyte_canonical, specimen, fasting_required, sex, age_scope, pregnancy_scope, method_or_formula, unit_machine, unit_display_vn, unit_alt_ifcc, value_type, range_lower, range_upper, reference_type, source_priority_tier, source_type, source_url, evidence_location, population_note, instrument_note, conversion_formula, conversion_formula_source, biological_variation_note, cv_or_uncertainty, comorbidity_caveat, normalization_note, vn_unit_verified, confidence, range_flag, range_notes`.

Duplicate analyte counts:
- `adult_outpatient_laboratory_reference_map.csv`: 25 analyte names have multiple rows. Top duplicates: `eGFR:6`, `HDL-C:5`, `LDL-C:5`, `Triglyceride:4`, `Fasting plasma glucose:3`, `HbA1c:3`, `Total cholesterol:3`, `RBC:2`, `HGB:2`, `HCT:2`.
- `data/reference/metrics_range.csv`: 25 metric names have multiple rows. Top duplicates: `eGFR:6`, `HDL-Cholesterol:5`, `LDL-Cholesterol:5`, `Triglycerides:4`, `Fasting Blood Glucose:3`, `HbA1c:3`, `Total Cholesterol:3`, `RBC:2`, `HGB:2`, `HCT:2`.

Field presence:
- Primary source has `range_flag`, `confidence`, `source_priority_tier`, `reference_type`, `source_url`.
- Existing `metrics_range.csv/json` have `source_priority_tier` and `source_url`, but not `range_flag`, `confidence`, or `reference_type`.
- `units_metric.csv` has only `test_name` and `standardized_unit`.

## 7. Strict-filter dry-run
- Primary input: `adult_outpatient_laboratory_reference_map.csv`
- Input rows: 80
- Accepted rows: 58
- Quarantined rows: 22
- Multiple-reason rows: 2
- Rejection reason counts:
  - `range_flag != OK`: 22
  - `confidence != HIGH`: 2
  - `source_priority_tier not in {T1,T2}`: 2
- MD analytes: `Basophils %`, `Basophils abs`, `Direct bilirubin`, `HbA1c`, `LDL-C`, `MPV`, `Potassium`
- HbA1c status: `MD`
- LDL-C status: `MD`
- Potassium status: `MD`

Evidence lines:
- Primary CSV header at `adult_outpatient_laboratory_reference_map.csv:1`.
- Potassium MD at `adult_outpatient_laboratory_reference_map.csv:38`.
- HbA1c MD rows at `adult_outpatient_laboratory_reference_map.csv:62-64`.
- LDL-C MD rows at `adult_outpatient_laboratory_reference_map.csv:77-81`.

## 8. Current checker behavior
- Supported analytes: `WBC`, `RBC`, `HGB`, `Glucose`, `HbA1c`, `LDL-Cholesterol`, `HDL-Cholesterol`, `Creatinine`, `Kali` from `data/reference/explanations.json` (9 entries).
- Hardcoded/config-driven: ranges are loaded from `data/reference/explanations.json`, but the matching/classification rules and "normal-like" group allowlist are hardcoded in `reference_range_checker_node.py:64-82`.
- Lookup dimensions: analyte name and patient gender only. Age is present in state/API but not used by the checker. Unit is copied through but not validated or used.
- Boundary behavior: inclusive bounds. The code classifies a range match when `(low is None or val >= low) and (high is None or val <= high)` at `reference_range_checker_node.py:82`. Dry-run probes confirmed WBC lower bound `4.0` and upper bound `10.0` are `normal`.
- Unsupported behavior: unsupported analyte remains `status="unknown"`, `reference_low=None`, `reference_high=None`, `is_abnormal=False`.
- Unit behavior: wrong unit is still classified if analyte/value match. Probe: `WBC 10.0 WRONG` returned `normal`; `Glucose 5.5 mg/dL` returned `normal` against mmol/L ranges.
- Missing value: if `value is None`, the checker skips lookup and leaves `unknown`.
- Missing range: if analyte absent from `EXPLANATIONS_DB`, remains `unknown`.
- Sex behavior: `get_gender_code()` maps `male/nam/m` -> `M`, `female/nữ/f` -> `F`, else `A` (`reference_range_checker_node.py:19-24`); range loop skips nonmatching sex-specific rows.
- Age behavior: no use of `patient_age` despite API/state carrying it.
- LLM dependency: none in the checker.
- Direct tests: none found for `reference_range_checker_node.py`.
- Contract risks:
  - Replacing with lookup by `(analyte, unit, sex, age_scope)` will require either using existing state fields carefully or requesting approval before changing `AgentState`/API response schema.
  - Current output lacks `source_url`, `reference_type`, confidence, source tier, and age scope; adding those to API output is a contract change.
  - Unit mismatch can silently classify values under the wrong unit today.
  - Current graph expects checker output under `indicators`; changing key names or statuses affects downstream critical/analyzer/guardrail.

## 9. Critical detector behavior
- Potassium behavior: thresholds are configured for both `Potassium` and `Kali`; keys are lowercased at load (`critical_detector_node.py:15`). `val <= low` produces `critical_low`; `val >= high` produces `critical_high` (`critical_detector_node.py:62-76`).
- Threshold source: `data/reference/critical_thresholds.json`; Potassium and Kali both use low `2.5`, high `6.5`, unit `mmol/L`.
- Supported analytes: `Potassium`, `Kali`, `Glucose`, `Fasting plasma glucose`, `LDL-C`.
- Hardcoded/config-driven: thresholds are config-driven from JSON, but critical comparison behavior and alert message format are hardcoded.
- Relationship to Reference Range Checker: graph runs checker first and critical detector second (`graph.py:20-22`). Critical detector can also initialize indicators from `raw_indicators` if checker has not produced them (`critical_detector_node.py:24-38`). It overwrites status only when critical thresholds are crossed.
- Tests: `tests/test_agents/test_critical_detector_node.py` covers Kali critical low, Glucose critical high, LDL-C noncritical, WBC unsupported, and alert count/order.
- Protection risks:
  - Do not merge normal reference ranges into `critical_thresholds.json`.
  - Do not let normal range checker produce `critical_*` statuses except through approved critical detector behavior.
  - Do not change `data/reference/critical_thresholds.json`, `src/agents/nodes/critical_detector_node.py`, or graph node order without owner approval.

## 10. Current schema and contract
- Input fields:
  - API `IndicatorInputSchema`: `name` required string, `value` required float, `unit` required string (`schemas.py:9-14`).
  - API `AnalyzeRequest`: `patient_age` required int 0-120, `patient_gender` required literal `male|female|other`, `test_date` required date, `language` default `vi`, `indicators` required nonempty list (`schemas.py:17-30`).
  - Graph `IndicatorInput`: `name`, `value`, `unit` optional by `TypedDict(total=False)` (`state.py:8-13`).
  - Graph `AgentState`: `patient_age`, `patient_gender`, `test_date`, `language`, `raw_indicators` (`state.py:83-87`).
- Output fields:
  - `IndicatorAssessment`: `name`, `value`, `unit`, `reference_low`, `reference_high`, `status`, `category`, `is_abnormal`, `is_critical` (`state.py:16-32`).
  - `CriticalAlert`: `indicator_name`, `value`, `unit`, `message` (`state.py:56-62`).
  - API `AnalyzeResponse`: `indicators`, `critical_alerts`, `has_critical_values`, `questions_for_doctor`, `summary`, `disclaimer`, `guardrail_passed`, `out_of_scope_indicators`, `error`, `is_placeholder` (`schemas.py:56-76`).
- Source support: `IndicatorResultSchema.sources: list[str]` exists, and analyzer writes sources into indicators. No structured source metadata field exists.
- Reference metadata support: no API/state fields for `reference_type`, `source_url` per range, `source_priority_tier`, `confidence`, `age_scope`, `range_flag`, or selected reference row id.
- Critical status support: `status` can carry `critical_low`/`critical_high` in state literal; API uses unconstrained `IndicatorStatus = str`.
- Disclaimer support: API response has default disclaimer; guardrail supplies default when missing.
- Aliases/serialization: Pydantic models do not define aliases. `config.py` uses aliases for environment variables. Route serializes `request.test_date.isoformat()` and `i.model_dump()`.
- Where schema objects are created: request validation in FastAPI/Pydantic; `IndicatorResultSchema(**ind)` in `routes.py:28-30`; checker creates assessment dicts at `reference_range_checker_node.py:40-51`; critical detector creates fallback assessment dicts at `critical_detector_node.py:26-38`.
- Required approval points: adding source/reference metadata to API response or `AgentState`, changing graph node order, changing status vocabulary, or changing required request fields requires Vũ/architecture approval.

## 11. Test inventory
| Test area | Path | Current coverage | Gaps |
|---|---|---|---|
| Reference Range Checker | none found | Indirectly exercised by graph/API tests | No direct boundary, unit mismatch, sex-specific, age-scope, unsupported analyte, missing value, or source metadata tests |
| Critical detector | `tests/test_agents/test_critical_detector_node.py` | Kali critical low, Glucose critical high, LDL-C normal/noncritical, WBC unsupported, alert count/order | No boundary equality tests at 2.5/6.5, wrong-unit tests, duplicate-alert rerun tests, Potassium English-name test |
| Guardrail | `tests/test_agents/test_guardrail_node.py` | Safe text, diagnosis keyword fallback, disclaimer fallback | No tests for questions-for-doctor scanning despite state doc saying guardrail should inspect questions |
| Graph | `tests/test_agents/test_graph.py` | Empty indicator graph flow and state shape | No nonempty graph tests with mocked LLM/vector dependencies; no node contract regression tests |
| API routes | `tests/test_api/test_routes.py` | Health, valid analyze, empty indicators 422, invalid date 422 | Valid analyze uses `WBC` unit `10^3/uL` and `Glucose` unit `mg/dL`, exposing current silent unit issue; no critical response assertion |
| RAG/retrieval | `tests/test_embed.py` | Real Chroma + BAAI/bge-m3 smoke test | Not mocked; may require external model/cache; no analyzer source extraction tests |
| Schemas | `tests/test_api/test_routes.py` indirectly | Request validation via FastAPI | No direct Pydantic model tests for optional/default fields |
| Reference data | none found | Data docs only | No automated strict filter, schema, duplicate, MD/quarantine tests |
| RAGAS/evaluation | none found | `eval/results/report.md` placeholder | No dataset, runner, metrics, baseline report, or RAGAS dependency |

## 12. Baseline test results
| Command | Exit code | Passed | Failed | Skipped | Notes |
|---|---:|---:|---:|---:|---|
| `F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_agents\test_critical_detector_node.py -q -p no:cacheprovider` | 0 | 1 | 0 | 0 | `1 passed in 0.04s`; existed before TIP-000 report creation |
| `F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_agents -q -p no:cacheprovider` | 0 | 5 | 0 | 0 | `5 passed in 0.09s`; existed before TIP-000 report creation |
| `F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_api -q -p no:cacheprovider` | 0 | 4 | 0 | 0 | `4 passed in 32.07s`; touched ignored `data/chroma/` during analyzer fallback |
| `F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider --ignore=tests/test_embed.py` | 0 | 9 | 0 | 0 | `9 passed in 17.11s`; largest safe non-embedding suite |
| `tests/test_embed.py` | not run | 0 | 0 | 0 | Explicitly non-mocked real embedding/Chroma smoke test; may require external HuggingFace model/cache state and writes temp Chroma data |

No baseline test failures were found in the safe subset. No implementation fixes were made.

## 13. RAGAS readiness
- Installed: NO
- Version: `not installed in the active environment`
- Existing evaluation code: no RAGAS runner or dataset found; only `eval/results/report.md` placeholder.
- Available metrics: cannot inspect installed RAGAS metrics because the package is not installed. Project guide examples mention `faithfulness`, `answer_relevancy`, `context_precision`, and `context_recall` in `docs/guide/chapter-08.md`.
- Required environment variables: current runtime model path needs `GOOGLE_API_KEY` for Gemini; config also defines `OPENAI_API_KEY`, LangSmith variables, and Chroma settings. Do not expose values.
- Integration blockers:
  - `ragas` dependency absent from `requirements.txt` and active virtualenv.
  - Current `AgentState.retrieved_contexts` exists but analyzer does not populate it; contexts are local variables only.
  - API response exposes indicator `sources`, but not retrieved context text or selected reference metadata.
  - RAGAS evaluation generally calls evaluator LLMs; no harmless documented baseline command exists.
- Cooperation needed from Vũ:
  - Approve any graph/state contract changes needed to collect `retrieved_contexts`, question, answer, and source metadata without breaking existing nodes.
  - Confirm whether RAGAS should evaluate analyzer output through the existing graph or a separate non-production eval harness.
  - Confirm LLM provider/model and safe evaluation budget before paid API calls.
- Input fields collectible without architecture changes: request `patient_age`, `patient_gender`, `test_date`, `language`, raw indicators, final indicators, explanations, indicator sources, summary, disclaimer, guardrail flags. Retrieved context text is not available without code/contract changes.
- Built-in metric explicitly named `hallucination`: not verifiable from installed package because RAGAS is not installed; no project code imports a `hallucination` metric.

## 14. Safe future edit scope

### Safe candidates
- `src/agents/nodes/reference_range_checker_node.py` — Tuấn scope, but preserve output contract and critical separation.
- `tests/test_agents/test_reference_range_checker_node.py` — new focused checker tests.
- `tests/test_agents/test_critical_detector_node.py` — add regression tests only; do not change expected critical policy without approval.
- `data/reference/metrics_range.csv` and `data/reference/metrics_range.json` — generated/runtime reference outputs in later TIPs if produced from approved source rules.
- `data/reference/units_metric.csv` — candidate only for approved unit mapping updates.
- `scripts/validate_mock_reports.py` — candidate validation support.
- Future `scripts/build_reference_ranges.py` or similar — candidate builder script, not present yet.
- Future `eval/datasets/*`, `eval/scripts/*`, `eval/results/*` — candidate RAGAS baseline artifacts, if created in later approved TIPs.
- `docs/version-handoff/*` — handoff/reporting documentation.

### Protected files
- `src/agents/graph.py` — graph definition and node ordering owned by Vũ.
- `src/agents/state.py` — shared node contract owned by Vũ.
- `src/agents/nodes/critical_detector_node.py` — critical behavior must remain separate and protected.
- `data/reference/critical_thresholds.json` — critical threshold policy.
- `src/agents/nodes/analyzer_node.py` — RAG/LLM architecture path owned by Vũ unless approved.
- `src/services/vector_store.py` — RAG storage/retrieval infrastructure.
- `src/services/llm.py` — model provider integration.
- `src/agents/nodes/guardrail_node.py` — guardrail ownership.
- `src/api/routes.py` and `src/models/schemas.py` — API contract changes require coordination.
- `.env`, `.env.example`, deployment/auth/logging scripts and configs — credentials/deployment ownership; do not expose or alter secrets.
- `adult_outpatient_laboratory_reference_map.csv` — protected source reference CSV.

### Approval-required files
- `src/models/schemas.py` — adding source/reference metadata changes API response contract.
- `src/agents/state.py` — adding fields for source metadata or retrieved contexts changes graph contract.
- `src/agents/graph.py` — any node order/edge changes require Vũ approval.
- `src/agents/nodes/analyzer_node.py` — needed if RAGAS requires context capture; owned by RAG architecture.
- `src/api/routes.py` — response/request shape changes affect frontend/API users.
- `data/reference/critical_thresholds.json` — safety policy file.
- `src/agents/nodes/critical_detector_node.py` — critical logic.
- `requirements.txt` — adding RAGAS or pytest plugins is dependency work, explicitly out of TIP-000 and needs later approval.
- `adult_outpatient_laboratory_reference_map.csv` — source data must not be modified.

## 15. Gaps and blockers
- No direct checker tests exist.
- Checker does not validate units and can silently classify values using a wrong unit.
- Checker does not use age despite age being in API/state and in V2 lookup requirements.
- Current output contract lacks structured source/reference metadata.
- RAGAS is not installed; no dataset or runner exists.
- Analyzer does not populate `retrieved_contexts`, so RAGAS context metrics are not directly collectible from current graph output.
- Primary V2 source has 22 quarantined rows under the strict filter; HbA1c, LDL-C, and Potassium are all `MD` and must not be promoted into runtime config without approval.
- `tests/test_embed.py` is a real, non-mocked embedding smoke test and was not run in TIP-000 safe baseline.
- Command failures recorded:
  - Sandboxed PowerShell spawn failed initially: `CreateProcessAsUserW failed: 1920 (The file cannot be accessed by the system.)`; read-only commands were rerun with approved escalation.
  - PATH `python --version` and `python -m pip show ...` failed: `Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.`
  - First strict-filter one-liner failed with `SyntaxError: '{' was never closed`; rerun succeeded.
  - One diagnostic print of WBC range data failed with `UnicodeEncodeError: 'charmap' codec can't encode character '\u1ed9'...`; other evidence was sufficient.

## 16. Conflicts with the proposed implementation plan
- Proposed "hardcoded three analytes" is only partly accurate: current checker supports 9 analytes through `explanations.json`, but not through the richer source map or strict V2 filter.
- Proposed lookup dimensions `(analyte, unit, sex, age_scope)` are not currently implemented; current checker uses only analyte and sex.
- Proposed data quality rule matches the root source CSV, but existing runtime `metrics_range.*` already contains 80 rows and lacks `range_flag/confidence`, so it cannot enforce the strict filter by itself.
- Kickoff says Tuấn should filter questionable rows and "tách 17 dòng nghi vấn"; actual strict dry-run finds 22 quarantined rows, not 17.
- Plan mentions HbA1c, LDL-C, and Potassium in V2, but the primary source marks all three as `MD`; they should not be accepted by strict filter without explicit data-quality decision.
- Critical policy already includes LDL-C and Glucose, not only Potassium, but docs emphasize critical separation. Any "only Kali critical" policy needs reconciliation with current `critical_thresholds.json`.
- Current `metrics_range.*` lipid rows are in `mg/dL` to match mocks, while primary source stores lipid rows in `mmol/L`; builder rules must avoid accidental unit regression.

## 17. Recommended paths for TIP-001 onward
- Build a read-only strict-filter test first against `adult_outpatient_laboratory_reference_map.csv` so accepted/quarantine counts are locked before generating runtime config.
- In TIP-001, generate candidate whitelist/quarantine outputs from the primary source without modifying the source CSV; include row-level rejection reasons.
- Add direct checker tests before refactoring: supported analyte, unsupported analyte, wrong unit, missing value, lower/upper inclusive boundaries, sex-specific ranges, age-scope behavior.
- Keep critical detector and normal reference checker separate; add regression tests for Potassium/Kali equality boundaries before any surrounding refactor.
- Ask Vũ to approve any `AgentState`, graph, or API response additions for source metadata and RAGAS context capture.
- Treat `HbA1c`, `LDL-C`, and `Potassium` as quarantined until Contractor/Homeowner approves the `MD` rows or updated source evidence.
- Do not add RAGAS dependency or paid model calls until an approved RAGAS TIP permits dependency changes and model budget.

## 18. TIP-000 conclusion
- Recommended next action: proceed to TIP-001 only for reference-data filtering/baseline tests, with quarantined MD rows excluded from runtime output.
- Ready for TIP-001: YES
- Conditions before continuing:
  - Do not modify `graph.py`, `state.py`, critical detector, critical thresholds, or primary source CSV.
  - Get Vũ approval before any schema/API/graph contract change.
  - Keep HbA1c, LDL-C, and Potassium `MD` rows out of accepted runtime config unless explicitly approved.
  - Add checker tests before changing checker behavior.
  - Treat RAGAS setup as a later dependency/evaluation TIP, not TIP-001 unless scope changes.
