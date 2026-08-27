# VMEC-05 Fix 2 — Generic Glucose/Fasting Alias Evidence

Date: 2026-08-15  
Decision: `FIX2_POLICY_A = APPROVED`

## 1. Scope

This correction removes only the two unsafe generic runtime aliases from
`data/reference/reference_checker_v2_config.json` and updates directly affected tests.
No runtime implementation, medical threshold, reference-range number, unit data,
schema, frontend, database, RAG, CDL, or approved-analyte scope was changed.

## 2. Human Policy A approval

The approved policy is fail-closed runtime behavior: generic `Glucose` and
`Đường huyết` must not imply a fasting specimen. Explicit fasting labels remain
mapped to canonical `Fasting plasma glucose`.

## 3. Before behavior

Before Fix 2, the runtime `analyte_aliases` mapped both generic labels to
`Fasting plasma glucose`. Consequently, `Glucose 5.2 mmol/L` and `Đường huyết
5.2 mmol/L` could receive the fasting RI 4.1–6.1 mmol/L despite having no
fasting context.

## 4. Exact config diff

```diff
-    "Glucose": "Fasting plasma glucose",
-    "Đường huyết": "Fasting plasma glucose",
```

No other production alias was removed or changed.

## 5. After behavior

Runtime probes and tests establish:

- `resolve_analyte("Glucose") is None`
- `resolve_analyte("Đường huyết") is None`
- generic inputs produce `status="unknown"`, null reference bounds,
  `is_abnormal=False`, and `is_critical=False`
- explicit fasting inputs continue to resolve to `Fasting plasma glucose`

## 6. Generic Glucose RI fail-closed proof

`test_e2e_04c_generic_glucose_does_not_receive_fasting_ri[Glucose]` passes for
`5.2 mmol/L`. It asserts unknown status, no attached bounds, no abnormal flag,
no critical flag, no alerts, and no aggregate critical state.

`test_e2e_04d_generic_glucose_low_value_preserves_unknown_status` passes for
`3.0 mmol/L` through Reference Range and Critical Detector. The detector does
not rescue or recanonicalize the raw name.

## 7. Generic Đường huyết RI fail-closed proof

`test_e2e_04c_generic_glucose_does_not_receive_fasting_ri[Đường huyết]` passes
with the same unknown/null/no-alert assertions. Repository tests also prove the
generic Vietnamese label resolves to `None`.

## 8. Explicit fasting aliases retained

All four runtime aliases resolve to canonical `Fasting plasma glucose`:

- `Fasting plasma glucose`
- `Fasting Blood Glucose`
- `Đường huyết lúc đói`
- `Glucose máu lúc đói`

Repository and standalone detector parameterized tests cover all four.

## 9. Explicit FPG Critical path proof

The full-pipeline test covers `Fasting plasma glucose` and retained alias
`Đường huyết lúc đói` at `3.0 mmol/L`:

- RI result: `low`, range 4.1–6.1 mmol/L
- existing conversion utility result: exact `Decimal("54.04677")` mg/dL
- ARUP comparison: `54.04677 < 55`
- final result: `critical_low`, one alert

No conversion constant was duplicated in the test.

## 10. Fix 1 invariants preserved

`test_generic_glucose_has_no_standalone_raw_name_critical_fallback` passes:
standalone raw `Glucose 3.0 mmol/L` remains unknown and creates no alert. The
Critical Detector production file is byte-identical to its pre-Fix2 state; no
`_CRITICAL_LAYER_ANALYTE_ALIASES` or raw-name threshold lookup was introduced.
The full-pipeline generic test also proves upstream unknown preservation.

## 11. OCR behavior change

`test_fix2_ocr_generic_glucose_is_unsupported_but_explicit_fasting_is_supported`
passes. Generic `Glucose` has `supported=False` and a populated
`unsupported_reason`; `Fasting Blood Glucose` has `supported=True` and no
unsupported reason. Unrelated OCR happy-path fixtures now use an explicit
fasting label so they continue to test their intended mechanics.

## 12. Build-time alias distinction

`src/scripts/extract_explanation_reference_ranges.py` was not changed.
Its `ALIAS_MAP["Glucose"]` remains valid as `BUILD_TIME_ALIAS` behavior and is
explicitly distinguished in tests from the removed `RUNTIME_REFERENCE_ALIAS`.
Both edited build-time alias tests pass.

## 13. Tests changed or added

- `tests/test_services/test_reference_repository.py`
- `tests/test_agents/test_critical_detector_node.py`
- `tests/test_integration/test_v2_reference_pipeline.py`
- `tests/test_data/test_explanation_reference_sync.py`
- `tests/test_api/test_ocr_review_gate.py`
- `tests/test_api/test_guest_flow.py` (directly relevant existing OCR fixture)

The requested root path `tests/test_ocr_review_gate.py` does not exist in this
repository. The actual relevant suite is `tests/test_api/test_ocr_review_gate.py`.

## 14. Commands run

Pytest commands used a workspace-local `--basetemp` because the sandbox denied
access to the host pytest temp directory.

```text
pytest tests/test_services/test_reference_repository.py -v
pytest tests/test_agents/test_critical_detector_node.py -v
pytest tests/test_integration/test_v2_reference_pipeline.py -v
pytest tests/test_data/test_explanation_reference_sync.py -v
pytest tests/test_data/test_explanation_reference_sync.py::test_sync_02_build_time_alias_resolution tests/test_data/test_explanation_reference_sync.py::test_sync_02_build_time_alias_map_completeness -v
pytest tests/test_api/test_ocr_review_gate.py -v
pytest tests/test_api/test_guest_flow.py::test_guest_can_complete_the_ocr_flow_without_persistence -v
pytest tests/test_agents/ tests/test_services/ tests/test_api/ -v
ruff check tests/test_services/test_reference_repository.py tests/test_data/test_explanation_reference_sync.py tests/test_agents/test_critical_detector_node.py tests/test_integration/test_v2_reference_pipeline.py tests/test_api/test_ocr_review_gate.py tests/test_api/test_guest_flow.py
git diff --check
```

## 15. Actual results

- Reference Repository: **65 passed**
- Critical Detector: **78 passed**
- V2 reference pipeline: **64 passed**
- OCR review gate: **20 passed**
- Directly relevant guest OCR retest: **1 passed**
- Agents + services + API aggregate rerun: **291 passed**
- Explanation-sync complete command: **8 passed, 13 failed** only because the
  repository lacks `adult_outpatient_laboratory_reference_map.csv`
- Explanation-sync edited Fix 2/build-time distinction tests: **2 passed**
- Ruff: **passed**
- `git diff --check`: **passed** (line-ending warnings only)

The first pytest attempt without `--basetemp` did not execute tests because the
host temp directory returned `WinError 5`; workspace-local reruns produced the
results above.

## 16. Protected-file proof

The worktree already contained Human-accepted Phase 2B changes, so protection
is proven by pre-Fix2 versus post-Fix2 SHA-256 equality rather than by Git
cleanliness. Every recorded hash is unchanged:

| Protected file | Pre-Fix2 SHA-256 | Post-Fix2 SHA-256 |
|---|---|---|
| `data/reference/critical_thresholds.json` | `8BE5418B796CA2768C50A01581D5E109565D331A0A23CA2F0E5CBBDFD58712AD` | same |
| `data/reference/reference_ranges.json` | `8606EC069E6EDE8ABD90BB969BFC6969FC9BCCCD3866192DE7459D36CD144A25` | same |
| `data/reference/units_metric.csv` | `10C03743DC14F36D7FEB84931CDB903F8A6BD74314C2A8D44C4EF5D064071903` | same |
| `src/agents/nodes/critical_detector_node.py` | `7913BD589E46AD32F523F0F0AF070E5F57F65E72A676A737AB276B8B89A8ED73` | same |
| `src/agents/nodes/reference_range_checker_node.py` | `BF9549EFE37EAABF55AE89181CE5C49E6DEB606AB5AAC8BFD33697EA2A84B930` | same |
| `src/services/reference_repository.py` | `9B93624AF8E6FC1A164CEE438984C1CFB4AB7D761A792584FFA8CF44D8DB2388` | same |
| `src/services/measurement_conversion.py` | `BF20501B3A31CBD4F068623685C50129A4DB4D4B981BF2938E7EB24D04941830` | same |

Therefore critical threshold data, reference-range numbers, unit data, Critical
Detector code, Reference Checker code, repository code, and conversion code did
not change in Fix 2.

## 17. Known limitations

- The complete explanation-sync suite cannot rebuild its generated catalog
  because the source artifact `adult_outpatient_laboratory_reference_map.csv`
  is absent from the repository. This is unrelated to Fix 2; all Fix 2-specific
  assertions pass.
- The optional whole-repository `pytest tests/ -q` was not run after the required
  aggregate suites because the known missing source artifact deterministically
  fails the explanation rebuild tests.
- V1 intentionally does not perform critical evaluation for generic glucose
  when fasting context is unknown. A future fasting-status schema is outside
  this correction's approved scope.

## Final disposition

`FIX2_IMPLEMENTED = YES`  
`POLICY_A_IMPLEMENTED = YES`  
`GENERIC_GLUCOSE_FPG_RUNTIME_ALIAS_EXISTS = NO`  
`FIX2_TESTS_PASS = YES`  
`READY_FOR_HUMAN_FIX2_REVIEW = YES`
