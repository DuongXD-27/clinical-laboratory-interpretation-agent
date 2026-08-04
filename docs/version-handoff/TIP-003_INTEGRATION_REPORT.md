# TIP-003 INTEGRATION REPORT

## Baseline
- Repository: F:\VIN_AI_PROJECT\P-056
- Branch: feature/TQT-reference-ragas
- Start commit: 6b012a4f5a04eff176555dbc157c50908d10c9de
- Working tree at preflight: clean
- Mode: integration tests and documentation artifacts only

## Files changed
- Created: docs/version-handoff/v2_analyte_manifest.json
- Created: tests/test_data/test_v2_analyte_manifest.py
- Created: tests/test_integration/test_v2_reference_pipeline.py
- Modified: tests/test_api/test_routes.py, adding focused API serialization contract tests only
- Created: docs/version-handoff/TIP-003_INTEGRATION_REPORT.md

## Manifest summary
- Total analytes: 9
- Approved normal analytes: WBC, RBC, Fasting plasma glucose, Creatinine
- Pending analytes: HGB, HbA1c, LDL-C, HDL-C, Potassium
- Critical-rule analytes in manifest: Fasting plasma glucose, LDL-C, Potassium
- Explanation coverage: 9 of 9 through exact names or TIP-002B aliases
- Source coverage: 9 of 9 through explanation sources or V2 reference/quarantine records
- RAGAS coverage: 0 of 9; all ragas_case_available values remain false

## Approved analytes
- WBC: approved RI normal classification; legacy 10^3/uL aliases canonicalize to 10^9/L without numeric conversion.
- RBC: approved RI normal classification with M and F sex-specific rules.
- Fasting plasma glucose: approved RI normal classification; CDL rows are ignored.
- Creatinine: approved Adult RI normal classification with M and F sex-specific rules.

## Pending analytes
- HGB: pending due unit_data_conflict between runtime RI rows and units_metric.csv.
- HDL-C: pending because current runtime rows are CDL-only and have a unit-policy conflict.
- HbA1c: pending because source rows are MD and not approved for normal RI runtime.
- LDL-C: pending because source rows are MD/CDL and not approved for normal RI runtime; critical threshold, if triggered, is independent.
- Potassium: pending in the normal checker; Critical Detector still owns Potassium/Kali critical behavior.

## Integration scenarios
- E2E-01 WBC normal legacy unit: PASS
- E2E-02 RBC male sex-specific: PASS
- E2E-03 RBC female sex-specific: PASS
- E2E-04 Fasting plasma glucose RI only: PASS
- E2E-05 Creatinine Adult policy boundaries: PASS
- E2E-06 Wrong WBC unit: PASS
- E2E-07 HGB pending: PASS
- E2E-08 HDL-C pending: PASS
- E2E-09 HbA1c pending: PASS
- E2E-10 LDL-C pending: PASS
- E2E-11 Potassium critical high: PASS
- E2E-12 Kali critical low alias: PASS
- E2E-13 Multiple-indicator order: PASS
- E2E-14 Missing value safety: PASS

## Reference checker results
- WBC with 7.0 10^3/uL at age 30 classified normal with bounds 4.72 to 11.3.
- RBC male value 4.2 10^12/L selected M bounds 4.45 to 6.19 and classified low.
- RBC female value 4.2 10^12/L selected F bounds 4.01 to 5.48 and classified normal.
- Fasting plasma glucose value 6.5 mmol/L selected RI bounds 4.1 to 6.1 and classified high, proving CDL rows were not used.
- Creatinine value 80 umol/L classified at Adult boundary ages 18 and 60, and remained unknown at ages 17 and 61.
- HGB, HDL-C, HbA1c, LDL-C, and Potassium remained unknown in the normal checker.

## Critical detector results
- WBC, RBC, Fasting plasma glucose, HGB, HDL-C, HbA1c, LDL-C at non-critical value, and Creatinine did not receive critical status in the integration tests.
- Potassium value 6.5 mmol/L remained unknown after the normal checker and became critical_high after Critical Detector.
- Kali value 2.5 mmol/L remained unknown after the normal checker and became critical_low after Critical Detector.
- Multi-indicator processing preserved input order and did not remove indicators.

## API contract results
- Source lists are preserved by AnalyzeResponse serialization.
- Disclaimer text from graph result is preserved.
- has_critical_values and critical_alerts are serialized.
- Unknown indicators with null reference bounds serialize successfully.
- Internal repository reason fields are not exposed in the public API response.
- New API contract tests monkeypatch src.api.routes.agent.ainvoke and do not call analyzer, vector store, embeddings, LLMs, or paid APIs.

## Source and disclaimer compatibility
- Indicator sources remain represented as list[str] in the public response schema.
- Disclaimer remains a top-level response field.
- The direct checker continues to provide explanation and source fields for matched indicators.
- The public API does not require schema changes for the TIP-003 verified fields.

## Protected-file integrity
- Production source files are unchanged except the authorized test-only modification to tests/test_api/test_routes.py.
- Reference data files are unchanged.
- Graph, state, schemas, API production route, critical detector policy, analyzer, guardrail, service code, dependencies, README, Makefile, and ruff.toml are unchanged.

## Test commands
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_data\test_v2_analyte_manifest.py -q -rxX -p no:cacheprovider
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_integration\test_v2_reference_pipeline.py -q -rxX -p no:cacheprovider
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_api -q -rxX -p no:cacheprovider
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests\test_agents -q -rxX -p no:cacheprovider
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m pytest tests -q -rxX -p no:cacheprovider --ignore=tests/test_embed.py
- F:\VIN_AI_PROJECT\.venv\Scripts\python.exe -B -m compileall -q src tests

## Test results
- Manifest tests: 11 passed
- Integration tests: 17 passed
- API tests: 9 passed
- Agent tests: 44 passed
- Full safe suite: 144 passed
- Compile: passed
- Failed: 0
- Unexpected xfail/xpass: 0

## Known limitations
- HGB remains pending until the unit-data conflict is resolved by an approved data-policy decision.
- HDL-C remains pending until CDL-only rows and unit policy are resolved for normal RI classification.
- HbA1c, LDL-C, and Potassium MD rows remain excluded from normal RI runtime support.
- Critical Detector does not imply normal reference support.

## RAGAS readiness inputs
- Safe initial analytes for TIP-004 cases: WBC, RBC, Fasting plasma glucose, Creatinine.
- Pending or excluded analytes: HGB, HDL-C, HbA1c, LDL-C, Potassium.
- Available output fields without graph/state changes: explanations, sources, summary, disclaimer.
- Retrieved context text is still not exposed by the graph/state contract.
- TIP-004 must use a separate eval harness unless Vu approves a state/graph contract change for retrieved context capture.

## Recommendation
- Continue to TIP-004 only after Contractor authorization.
- Do not promote pending analytes or alter graph/state/schema contracts without approval.
