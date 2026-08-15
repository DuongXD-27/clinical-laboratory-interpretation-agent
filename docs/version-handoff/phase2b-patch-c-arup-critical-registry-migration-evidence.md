# VMEC-05 Phase 2B Patch C — ARUP Production Registry Migration Evidence

## 1. Scope

Patch C migrates the production Critical Detector registry from an unprovenanced
12-key hybrid registry to the human-approved ARUP Rev.46 canonical current-9
registry.

Patch C changed production critical data and critical-registry-specific tests
only. It did not change Patch A/B runtime implementation, Reference Range
behavior, aliases, approved analytes, CDL, API schemas, frontend, persistence,
RAG, or explanations.

## 2. Human governance reference

The migration implements the frozen decisions:

- ADR-009: **ACCEPTED**
- CRIT-ARUP-02: **APPROVED**
- Patch A: **HUMAN ACCEPTED**
- GLUCOSE-CONV-01: **APPROVED**
- Patch B: **HUMAN ACCEPTED**

The sole V1 operational Critical Detector authority is:

- ARUP Laboratories
- *CRITICAL VALUES LIST*
- Document `CORP-APPEND-0104A`
- Revision 46
- April 2026
- Official PDF:
  `https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf`

No secondary source was used to fill ARUP gaps.

## 3. Before registry

Before Patch C, `critical_thresholds.json` contained 12 keys:

- canonical and alias duplicates: `Potassium`/`Kali`,
  `Glucose`/`Fasting Plasma Glucose`, and `HGB`/`Hemoglobin`;
- no explicit operators or provenance;
- active legacy values for WBC, HGB, LDL-C, HbA1c, HDL-C, and Creatinine;
- negative `-1.0` inactive sentinels;
- inclusive runtime defaults that could not encode ARUP's strict boundaries.

Pre-migration SHA-256:

`9AF68E06B037CE327D27FFFA396BD4DEE289E1BFAE48B0E1DBFAF36EEB9E37AE`

## 4. After registry

The production file now contains exactly nine canonical records. Only
Potassium and Fasting plasma glucose have active execution sides. The other
seven records use explicit `null` threshold/operator pairs and bounded
`inactive_reason` values.

Post-migration SHA-256:

`8BE5418B796CA2768C50A01581D5E109565D331A0A23CA2F0E5CBBDFD58712AD`

## 5. Canonical records

Exact production keys:

1. WBC
2. RBC
3. HGB
4. Fasting plasma glucose
5. HbA1c
6. LDL-C
7. HDL-C
8. Creatinine
9. Potassium

The independent alias keys `Kali`, `Glucose`,
`Fasting Plasma Glucose`, and `Hemoglobin` are absent.

## 6. Active rules

Potassium:

- low: `3.0`
- low operator: `<`
- high: `6.1`
- high operator: `>`
- unit: `mmol/L`
- source literal: `< 3.0 or > 6.1 mmol/L`

Fasting plasma glucose:

- low: `55`
- low operator: `<`
- high: `450`
- high operator: `>`
- source unit: `mg/dL`
- source literal: `< 55 or > 450 mg/dL`
- population: `>30 days to adult`
- comparison strategy: `CONVERT_INPUT_TO_SOURCE_UNIT`
- VMEC canonical input unit: `mmol/L`
- conversion authority: `NIST-CAS-492-62-6-MW-180.1559`
- scope: `CRITICAL_LAYER_ONLY`

No converted mmol/L threshold is stored.

## 7. Inactive rules

The following analytes have `low = null`, `low_operator = null`,
`high = null`, and `high_operator = null`:

- WBC — `SOURCE_ROW_RESTRICTED_U_OF_U_ONLY`
- HGB — `SOURCE_ROW_RESTRICTED_U_OF_U_ONLY`
- LDL-C — `NO_APPLICABLE_ARUP_REV46_RULE`
- HbA1c — `NO_APPLICABLE_ARUP_REV46_RULE`
- HDL-C — `NO_APPLICABLE_ARUP_REV46_RULE`
- Creatinine — `NO_APPLICABLE_ARUP_REV46_ADULT_RULE`
- RBC — `NO_APPLICABLE_ARUP_REV46_RBC_COUNT_RULE`

These states mean no active VMEC-05 V1 critical rule. They do not claim that a
value is medically safe or that the analyte is unsupported.

## 8. Provenance

Both active records contain the complete final provenance set:

- `source_id`
- `source_title`
- `source_document_id`
- `source_revision`
- `source_date`
- `source_url`
- `source_page`
- `source_literal`
- `source_analyte_label`
- `population_context`
- `qualifier`

All inactive records contain the required ARUP document identity and a bounded
inactive reason. WBC and HGB additionally retain their source analyte labels
and the exact qualifier:

`Test performed for University of Utah Health System only`

Restricted WBC/HGB threshold numbers were not placed in executable fields.

## 9. Sentinel removal

A structured scan of both execution sides reports:

`NEGATIVE_SENTINEL_COUNT = 0`

Final production schema tests reject negative sentinel values. Every inactive
side is explicit `null`/`null`.

## 10. Alias deduplication

Production registry alias duplicate count is zero. Alias behavior remains in
`ReferenceRepository`; the registry does not duplicate alias records.

Tests prove:

- Potassium and Kali reach the same active Potassium rule.
- Existing FPG aliases reach the single canonical FPG rule.
- HGB and Hemoglobin both reach the same inactive HGB rule and do not alert.

No alias configuration was added or changed.

## 11. Boundary tests

Production Potassium rule:

| Input | Result |
|---:|---|
| 2.99 mmol/L | critical low |
| 3.00 mmol/L | not critical |
| 3.01 mmol/L | not critical |
| 6.09 mmol/L | not critical high |
| 6.10 mmol/L | not critical high |
| 6.11 mmol/L | critical high |

Production FPG conversion path:

| Input | Exact converted value | Result |
|---:|---:|---|
| 3.050 mmol/L | 54.94754950 mg/dL | critical low |
| 3.053 mmol/L | 55.00159627 mg/dL | not critical low |
| 24.97 mmol/L | 449.84928230 mg/dL | not critical high |
| 24.99 mmol/L | 450.20959410 mg/dL | critical high |

Standalone source-unit cases also pass at 54.99, 55.00, 450.00, and
450.01 mg/dL with strict operators.

## 12. Inactive-analyte tests

Production standalone tests and end-to-end RI/Critical pipeline tests cover:

- WBC 35 ×10^9/L
- HGB 200 g/L
- LDL-C 5.3 mmol/L
- HbA1c 10 %
- HDL-C 0.5 mmol/L
- Creatinine 400 umol/L
- RBC 100 ×10^12/L

None creates a critical alert. In end-to-end tests, the pre-existing RI
classification remains unchanged (`high` or `low` as applicable).

## 13. Commands run

```text
.venv\Scripts\python.exe -m pytest tests\test_services\test_measurement_conversion.py -v --basetemp .tmp\pytest-patch-c-conversion
.venv\Scripts\python.exe -m pytest tests\test_agents\test_critical_detector_node.py -v --basetemp .tmp\pytest-patch-c-detector
.venv\Scripts\python.exe -m pytest tests\test_data\test_critical_data_quality.py -v --basetemp .tmp\pytest-patch-c-data
.venv\Scripts\python.exe -m pytest tests\test_integration\test_v2_reference_pipeline.py -v --basetemp .tmp\pytest-patch-c-integration
.venv\Scripts\python.exe -m pytest tests\test_agents tests\test_services tests\test_api -v --basetemp .tmp\pytest-patch-c-regression
.venv\Scripts\python.exe -m pytest tests -q --basetemp .tmp\pytest-patch-c-full
.venv\Scripts\python.exe -m ruff check tests\test_data\test_critical_data_quality.py tests\test_agents\test_critical_detector_node.py tests\test_integration\test_v2_reference_pipeline.py tests\test_data\test_explanation_reference_sync.py
git diff --check
git diff --exit-code -- data/reference/reference_ranges.json data/reference/reference_checker_v2_config.json data/reference/units_metric.csv src/agents/nodes/reference_range_checker_node.py data/reference/explanations.json
Get-FileHash -Algorithm SHA256 <registry and protected files>
```

A structured Python registry scan also printed canonical keys, active keys, and
negative-sentinel count.

## 14. Actual results

- Measurement conversion: **13 passed** in 2.47 seconds.
- Critical Detector: **76 passed** in 9.79 seconds.
- Critical production data quality: **24 passed** in 3.97 seconds.
- V2 Reference pipeline integration: **59 passed** in 8.37 seconds.
- Agents/services/API regression: **283 passed** in 54.79 seconds.
- Ruff lint on changed Python tests: **passed**.
- `git diff --check`: **passed**.
- Protected-file diff check: **passed**.

Optional repository-wide suite: **464 passed, 31 failed, 1 warning** in 86.40
seconds. The 31 failures reproduce known checkout limitations outside Patch C:
missing `adult_outpatient_laboratory_reference_map.csv`, missing
`data/reference/quarantine_v2.csv`, and cascading data-build/RAGAS evidence
failures. No production critical schema, ARUP boundary, inactive-analyte,
operator, conversion, or Reference Range regression test failed.

## 15. Protected-file proofs

The protected files have zero Git diff and retain their pre-Patch-C hashes:

| Protected file | SHA-256 |
|---|---|
| `data/reference/reference_ranges.json` | `8606EC069E6EDE8ABD90BB969BFC6969FC9BCCCD3866192DE7459D36CD144A25` |
| `data/reference/reference_checker_v2_config.json` | `BEF8FE1E0084428C860D4A5C6B0631247312AEC0BE2BDE346D5BDFB2B918FB30` |
| `data/reference/units_metric.csv` | `10C03743DC14F36D7FEB84931CDB903F8A6BD74314C2A8D44C4EF5D064071903` |
| `src/agents/nodes/reference_range_checker_node.py` | `BF9549EFE37EAABF55AE89181CE5C49E6DEB606AB5AAC8BFD33697EA2A84B930` |
| `data/reference/explanations.json` | `1286D65A1CB0763EE43E1B8F96899CEB06A78BE8CD09BD26B15F8D1A7586854A` |

The generic RI alias remains exactly:

```json
"Glucose": "Fasting plasma glucose"
```

Patch C did not modify runtime implementation. The current source-code diff in
the working tree belongs to the previously accepted Patch A/B work.

## 16. Known limitations

- ARUP Rev.46 is the accepted V1 operational/demo authority, not a formally
  endorsed Vinmec Laboratory SOP.
- Only Potassium and FPG have active V1 critical rules.
- FPG source-unit mg/dL remains unsupported end-to-end by the current RI layer;
  upstream `unknown` is intentionally preserved. Standalone same-unit detector
  capability is tested separately.
- The runtime still retains Patch A's legacy operator fallback for transitional
  compatibility, but no production record depends on it.
- The optional full suite requires the unrelated absent source artifacts noted
  above.

## 17. Final production registry matrix

| Analyte | Low | Low op | High | High op | Unit | Active? | Reason/source |
|---|---:|:---:|---:|:---:|:---:|:---:|---|
| WBC | null | null | null | null | 10^9/L | No | SOURCE_ROW_RESTRICTED_U_OF_U_ONLY |
| RBC | null | null | null | null | 10^12/L | No | NO_APPLICABLE_ARUP_REV46_RBC_COUNT_RULE |
| HGB | null | null | null | null | g/L | No | SOURCE_ROW_RESTRICTED_U_OF_U_ONLY |
| Fasting plasma glucose | 55 | < | 450 | > | mg/dL | Yes | ARUP Rev.46, Glucose >30 days to adult |
| HbA1c | null | null | null | null | % | No | NO_APPLICABLE_ARUP_REV46_RULE |
| LDL-C | null | null | null | null | mmol/L | No | NO_APPLICABLE_ARUP_REV46_RULE |
| HDL-C | null | null | null | null | mmol/L | No | NO_APPLICABLE_ARUP_REV46_RULE |
| Creatinine | null | null | null | null | umol/L | No | NO_APPLICABLE_ARUP_REV46_ADULT_RULE |
| Potassium | 3.0 | < | 6.1 | > | mmol/L | Yes | ARUP Rev.46 |

## Review flags

```text
PATCH_C_IMPLEMENTED = YES
ARUP_REV46_PRODUCTION_REGISTRY_ACTIVE = YES
PRODUCTION_CANONICAL_RECORD_COUNT = 9
ACTIVE_CANONICAL_ANALYTES = Potassium, Fasting plasma glucose
ACTIVE_CANONICAL_ANALYTE_COUNT = 2
INACTIVE_CANONICAL_ANALYTES = WBC, HGB, LDL-C, HbA1c, HDL-C, Creatinine, RBC
POTASSIUM_ARUP_RULE_ACTIVE = YES
GLUCOSE_ARUP_RULE_ACTIVE = YES
WBC_CRITICAL_INACTIVE = YES
HGB_CRITICAL_INACTIVE = YES
LDL_C_CRITICAL_INACTIVE = YES
HBA1C_CRITICAL_INACTIVE = YES
HDL_C_CRITICAL_INACTIVE = YES
CREATININE_CRITICAL_INACTIVE = YES
RBC_CRITICAL_INACTIVE = YES
NEGATIVE_SENTINEL_COUNT = 0
CRITICAL_ALIAS_DUPLICATE_COUNT = 0
ACTIVE_RULES_WITH_COMPLETE_PROVENANCE = 2/2
PRODUCTION_USES_LEGACY_OPERATOR_DEFAULT = NO
POTASSIUM_BOUNDARY_TESTS_PASS = YES
GLUCOSE_BOUNDARY_TESTS_PASS = YES
INACTIVE_ANALYTE_NO_ALERT_TESTS_PASS = YES
REFERENCE_RANGE_CHANGED = NO
GENERIC_GLUCOSE_FPG_ALIAS_CHANGED = NO
PATCH_A_REGRESSION_PASS = YES
PATCH_B_REGRESSION_PASS = YES
FIX1_REGRESSION_PASS = YES
PATCH_C_TESTS_PASS = YES
READY_FOR_HUMAN_PATCH_C_REVIEW = YES
```

