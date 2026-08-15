# VMEC-05 — Phase 2B ARUP Rev.46 Critical Registry Migration Plan

**Role:** Senior Medical Data Engineer + Safety QA Auditor
**Plan date:** 2026-08-14
**Mode:** Read-only planning; no production data, code, tests, frontend, database, aliases, reference ranges, or RAG changed
**Human-approved V1 authority:** ARUP Laboratories, *CRITICAL VALUES LIST*, `CORP-APPEND-0104A`, Rev. 46, April 2026

---

## 1. Frozen governance decision

The Human owner has selected the following single operational benchmark for VMEC-05 V1:

> ARUP Laboratories, *CRITICAL VALUES LIST*, document `CORP-APPEND-0104A`, Rev. 46, April 2026.

Policy consequences:

- An ARUP Rev.46 rule is eligible only for the analyte, side, population, and context actually stated by ARUP.
- If Rev.46 does not define the analyte or side for the applicable population/context, that VMEC side must be inactive.
- Mayo, University of Iowa, RCPath, surveys, AHA, ADA, Vinmec articles, and all other sources are excluded from the V1 operational registry. They are not gap-fillers.
- No hybrid registry is proposed.

The declared authority is recorded, but the production migration is not yet ready: strict operators are not representable by the current detector, source-to-canonical unit conversions need a deterministic policy, and the ARUP generic Glucose to repository `Fasting plasma glucose` identity needs explicit resolution.

---

## 2. Official source verification

The official PDF was opened from the current ARUP Critical and Alert Values page, not inferred from a search snippet or the obsolete Rev.34 URL.

| Field | Verified value |
|---|---|
| Organization | ARUP Laboratories |
| Exact title | *CRITICAL VALUES LIST* |
| Document ID | `CORP-APPEND-0104A` |
| Revision | Rev. 46 |
| Date | April 2026 |
| Length | 3 pages |
| Official URL | https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf |
| Relevant page | Page 1 of 3 |
| Status | `DECLARED_VMEC_V1_OPERATIONAL_BENCHMARK` |
| Page-level qualifier | `*Test performed for University of Utah Health System only` |

The asterisk applies to asterisked rows, including the Hemoglobin and White Blood Cell Count rows. Potassium and Glucose are not asterisked. The document does not state a specimen for these four rows. No specimen is inferred.

---

## 3. Part 1 — source-of-truth extraction

Values below are source literals. No unit conversion, rounding, operator normalization, or gap filling has been applied.

| ARUP analyte | Population/context | Low operator | Low | High operator | High | Source unit | Page | Exact notes |
|---|---|---|---:|---|---:|---|---:|---|
| Glucose | birth to 30 days | `<` | 46 | `>` | 200 | mg/dL | 1 | No specimen/comment stated |
| Glucose | >30 days to adult | `<` | 55 | `>` | 450 | mg/dL | 1 | No specimen/comment stated |
| Potassium | Population not stated | `<` | 3.0 | `>` | 6.1 | mmol/L | 1 | No specimen/comment stated |
| Hemoglobin* | birth to 6 days | `<=` | 12.0 | `>=` | 22.0 | g/dL | 1 | `*Test performed for University of Utah Health System only` |
| Hemoglobin* | >=7 days to adult | `<` | 7.0 | NULL | NULL | g/dL | 1 | `*Test performed for University of Utah Health System only`; no adult high side |
| White Blood Cell Count* | Population not stated | `<=` | 2.0 | `>=` | 40 | x 10^3/µL | 1 | `*Test performed for University of Utah Health System only` |
| LDL-C | Not listed | NULL | NULL | NULL | NULL | NULL | — | No LDL-C critical rule in the 3-page list |
| HbA1c | Not listed | NULL | NULL | NULL | NULL | NULL | — | No HbA1c critical rule in the 3-page list |
| HDL-C | Not listed | NULL | NULL | NULL | NULL | NULL | — | No HDL-C critical rule in the 3-page list |
| Creatinine | Not listed | NULL | NULL | NULL | NULL | NULL | — | No Creatinine critical rule in the 3-page list |
| RBC count | Not listed | NULL | NULL | NULL | NULL | NULL | — | Page 3 contains `Antibody Screen RBC, Solid Phase`; that is a transfusion-service antibody screen, not an RBC count rule |

VMEC's current approved reference scope is adult 18–60. Therefore, the proposed flat V1 registry uses the ARUP `>30 days to adult` Glucose row and `>=7 days to adult` Hemoglobin row. Neonatal rows are preserved above as source context but are not flattened into adult VMEC rules. A future multi-population critical registry would require explicit population selection in the detector.

---

## 4. Part 2 — current VMEC to ARUP mapping

Alias duplicates are collapsed to the repository canonical returned by `ReferenceRepository.resolve_analyte()`.

| VMEC canonical analyte | Current VMEC rule | ARUP rule exists? | ARUP exact applicable rule | Mapping confidence | Notes |
|---|---|---|---|---|---|
| Potassium | `<=2.5 / >=6.5 mmol/L` | Yes | `<3.0 / >6.1 mmol/L` | **EXACT** | Same analyte; both values and both operators change |
| Fasting plasma glucose | `<=3.0 / >=27.8 mmol/L` | Yes, for `Glucose` | Adult `<55 / >450 mg/dL` | **REVIEW_REQUIRED** | Same measured substance is likely intended, but ARUP does not say fasting or state a specimen; repository currently maps generic `Glucose` to fasting glucose |
| WBC | `<=2.5 / >=30 ×10^9/L` | Yes | White Blood Cell Count `<=2.0 / >=40 x 10^3/µL` | **EXACT** | Measurement identity is exact; ARUP row is asterisked U of U-only and that qualifier must be retained |
| HGB | `<=60 / >=200 g/L` | Yes | Adult Hemoglobin `<7.0 g/dL`; high NULL | **EXACT** | HGB/Hemoglobin identity is confirmed by repository aliases; adult high side must deactivate; ARUP row is U of U-only |
| LDL-C | inactive low / `>=4.91 mmol/L` high | No | NULL / NULL | **NO_ARUP_RULE** | Both sides inactive under ARUP-only policy |
| HbA1c | inactive low / `>=9.0%` high | No | NULL / NULL | **NO_ARUP_RULE** | Both sides inactive under ARUP-only policy |
| HDL-C | `<=0.7 / >=2.1 mmol/L` | No | NULL / NULL | **NO_ARUP_RULE** | Both sides inactive under ARUP-only policy |
| Creatinine | inactive low / `>=353.6 µmol/L` high | No | NULL / NULL | **NO_ARUP_RULE** | Both sides inactive; no other-source replacement allowed |
| RBC | inactive `-1 / -1 ×10^12/L` | No RBC-count rule | NULL / NULL | **NO_ARUP_RULE** | `Antibody Screen RBC` is not RBC count; remains inactive without sentinels |

---

## 5. Part 3 — side-by-side migration matrix

`Current VMEC` shows current inclusive runtime semantics. `ARUP Rev.46` preserves the source literal. Multiple change classifications are shown where the same side requires numeric, operator, and/or unit-representation changes.

| Analyte | Side | Current VMEC | ARUP Rev.46 | Change type | Proposed V1 state |
|---|---|---|---|---|---|
| Potassium | LOW | `<=2.5 mmol/L` | `<3.0 mmol/L` | `CHANGE_NUMERIC + CHANGE_OPERATOR` | `ACTIVE_ARUP` |
| Potassium | HIGH | `>=6.5 mmol/L` | `>6.1 mmol/L` | `CHANGE_NUMERIC + CHANGE_OPERATOR` | `ACTIVE_ARUP` |
| Fasting plasma glucose | LOW | `<=3.0 mmol/L` | `<55 mg/dL` | `CHANGE_NUMERIC + CHANGE_OPERATOR + CHANGE_UNIT_REPRESENTATION` | `ACTIVE_ARUP` after mapping/conversion gate |
| Fasting plasma glucose | HIGH | `>=27.8 mmol/L` | `>450 mg/dL` | `CHANGE_NUMERIC + CHANGE_OPERATOR + CHANGE_UNIT_REPRESENTATION` | `ACTIVE_ARUP` after mapping/conversion gate |
| WBC | LOW | `<=2.5 ×10^9/L` | `<=2.0 x 10^3/µL` | `CHANGE_NUMERIC + CHANGE_UNIT_REPRESENTATION` | `ACTIVE_ARUP` with U of U qualifier |
| WBC | HIGH | `>=30 ×10^9/L` | `>=40 x 10^3/µL` | `CHANGE_NUMERIC + CHANGE_UNIT_REPRESENTATION` | `ACTIVE_ARUP` with U of U qualifier |
| HGB | LOW | `<=60 g/L` | `<7.0 g/dL` | `CHANGE_NUMERIC + CHANGE_OPERATOR + CHANGE_UNIT_REPRESENTATION` | `ACTIVE_ARUP` with adult/U of U context |
| HGB | HIGH | `>=200 g/L` | NULL for >=7 days to adult | `DEACTIVATE_NO_ARUP_RULE` | `INACTIVE_NO_ARUP_RULE` |
| LDL-C | LOW | `-1` sentinel | NULL | `REMOVE_SENTINEL` | `INACTIVE_NO_ARUP_RULE` |
| LDL-C | HIGH | `>=4.91 mmol/L` | NULL | `DEACTIVATE_NO_ARUP_RULE` | `INACTIVE_NO_ARUP_RULE` |
| HbA1c | LOW | `-1` sentinel | NULL | `REMOVE_SENTINEL` | `INACTIVE_NO_ARUP_RULE` |
| HbA1c | HIGH | `>=9.0%` | NULL | `DEACTIVATE_NO_ARUP_RULE` | `INACTIVE_NO_ARUP_RULE` |
| HDL-C | LOW | `<=0.7 mmol/L` | NULL | `DEACTIVATE_NO_ARUP_RULE` | `INACTIVE_NO_ARUP_RULE` |
| HDL-C | HIGH | `>=2.1 mmol/L` | NULL | `DEACTIVATE_NO_ARUP_RULE` | `INACTIVE_NO_ARUP_RULE` |
| Creatinine | LOW | `-1` sentinel | NULL | `REMOVE_SENTINEL` | `INACTIVE_NO_ARUP_RULE` |
| Creatinine | HIGH | `>=353.6 µmol/L` | NULL | `DEACTIVATE_NO_ARUP_RULE` | `INACTIVE_NO_ARUP_RULE` |
| RBC | LOW | `-1` sentinel | NULL | `REMOVE_SENTINEL` | `INACTIVE_NO_ARUP_RULE` |
| RBC | HIGH | `-1` sentinel | NULL | `REMOVE_SENTINEL` | `INACTIVE_NO_ARUP_RULE` |

No existing numeric value is kept merely because it is close to an ARUP value.

---

## 6. Part 4 — operator audit

The current detector hard-codes `numeric_val <= low_val` and `numeric_val >= high_val`. It has no per-side operator fields and cannot represent strict `<` or `>` exactly.

| Analyte | Side | ARUP operator | Current runtime operator | Exact match? | Code change required? |
|---|---|---|---|---|---|
| Potassium | LOW | `<` | `<=` | No | Yes |
| Potassium | HIGH | `>` | `>=` | No | Yes |
| Glucose (>30 days–adult) | LOW | `<` | `<=` | No | Yes |
| Glucose (>30 days–adult) | HIGH | `>` | `>=` | No | Yes |
| WBC | LOW | `<=` | `<=` | Yes | No for operator; qualifier/context still needs preservation |
| WBC | HIGH | `>=` | `>=` | Yes | No for operator; qualifier/context still needs preservation |
| HGB (>=7 days–adult) | LOW | `<` | `<=` | No | Yes |
| HGB (>=7 days–adult) | HIGH | NULL | `>=` if numeric | N/A | No comparison when value is `null` |

Minimal required software change:

1. Add `low_operator` and `high_operator` to each critical record, accepting only `<`, `<=`, `>`, `>=`, or `null` as appropriate for the side.
2. Dispatch the comparison from the configured operator rather than hard-coding inclusive comparisons.
3. Reject/fail closed on a missing or invalid operator for a non-null threshold.
4. Render the configured operator in alert text; do not continue printing `<=`/`>=` unconditionally.
5. Add exact-boundary tests showing that `3.0 mmol/L` Potassium is not critical low, `6.1 mmol/L` is not critical high, `55 mg/dL` Glucose is not critical low, `450 mg/dL` is not critical high, and `7.0 g/dL` HGB is not critical low.

Encoding `>6.1` as `>=6.11` is prohibited. Therefore `OPERATOR_SUPPORT_PATCH_REQUIRED = YES`.

---

## 7. Part 5 — unit audit

`ReferenceRepository.normalize_unit()` is an alias normalizer, not a numeric converter. It currently recognizes `10^3/µL` as equivalent to `10^9/L` and Unicode µ/μ variants of `µmol/L`, but it does not convert glucose mg/dL to mmol/L or HGB g/dL to g/L.

| Analyte/rule | ARUP source unit | VMEC canonical unit | Current normalizer behavior | Classification | Numeric conversion required? |
|---|---|---|---|---|---|
| Potassium | mmol/L | mmol/L | Unchanged text | `IDENTICAL` | No |
| Glucose | mg/dL | mmol/L | Remains different; detector fails closed | `CONVERSION_REQUIRED` | Yes |
| WBC | x 10^3/µL | 10^9/L | `10^3/µL` alias maps to `10^9/L`; the PDF's display prefix `x ` must be preserved only as source literal | `EQUIVALENT_ALIAS` | No; numeric factor is 1 |
| HGB | g/dL | g/L | Remains different; detector fails closed | `CONVERSION_REQUIRED` | Yes |

### Glucose conversion record

- **SOURCE_LITERAL LOW:** `<55 mg/dL`
- **SOURCE_LITERAL HIGH:** `>450 mg/dL`
- **PROPOSED_RUNTIME_CANONICAL LOW:** `<(55 / 18.01559) mmol/L = <3.05291139507504 mmol/L` before rounding
- **PROPOSED_RUNTIME_CANONICAL HIGH:** `>(450 / 18.01559) mmol/L = >24.9783659597049 mmol/L` before rounding
- **CONVERSION_FORMULA:** `glucose_mmol_L = glucose_mg_dL / 18.01559`
- **ROUNDING_POLICY_REQUIRED:** **YES**

The canonical JSON value must not be finalized until the Human-approved precision/rounding rule is documented. Rounding must not change strict source-boundary behavior. A safer implementation is to retain the source literal and use deterministic Decimal conversion at comparison time, with explicitly tested quantization rules.

### HGB conversion record

- **SOURCE_LITERAL:** `<7.0 g/dL`
- **PROPOSED_RUNTIME_CANONICAL:** `<70 g/L`
- **CONVERSION_FORMULA:** `hemoglobin_g_L = hemoglobin_g_dL × 10`
- **ROUNDING_POLICY_REQUIRED:** **NO**; decimal scaling is exact

### WBC unit representation

- **SOURCE_LITERAL:** `<=2.0 or >=40 x 10^3/µL`
- **PROPOSED_RUNTIME_CANONICAL:** `<=2.0 or >=40 ×10^9/L`
- **CONVERSION_FORMULA:** numeric identity; `1 ×10^3/µL = 1 ×10^9/L`
- **ROUNDING_POLICY_REQUIRED:** **NO**

Because at least Glucose and HGB require numeric unit conversion and the current shared service is alias-only, `UNIT_CONVERSION_PATCH_REQUIRED = YES`.

---

## 8. Part 6 — expected consequences for the current nine

Only ARUP Rev.46 is used.

| Canonical analyte | Proposed consequence | Reason |
|---|---|---|
| Potassium | `ACTIVE_BOTH_SIDES` | ARUP defines `<3.0` and `>6.1 mmol/L` |
| Fasting plasma glucose | `ACTIVE_BOTH_SIDES` after mapping/conversion gate | ARUP defines adult Glucose `<55` and `>450 mg/dL`; fasting/specimen wording needs resolution |
| WBC | `ACTIVE_BOTH_SIDES` | ARUP defines White Blood Cell Count `<=2.0 / >=40 x 10^3/µL`; U of U-only qualifier retained |
| HGB | `ACTIVE_LOW_ONLY` | Applicable >=7-days-to-adult row defines `<7.0 g/dL` only; no adult high value |
| LDL-C | `INACTIVE_NO_ARUP_RULE` | Absent |
| HbA1c | `INACTIVE_NO_ARUP_RULE` | Absent |
| HDL-C | `INACTIVE_NO_ARUP_RULE` | Absent |
| Creatinine | `INACTIVE_NO_ARUP_RULE` | Absent |
| RBC | `INACTIVE_NO_ARUP_RULE` | No RBC-count rule; transfusion antibody screen is not equivalent |

Current active canonical analytes: **8**. Proposed active canonical analytes: **4**.

---

## 9. Part 7 — alias and duplicate cleanup plan

The detector now resolves a raw label through `ReferenceRepository` and looks up only the returned canonical key. Duplicate threshold records are unnecessary and create drift risk. The target JSON should retain one canonical record for each of the current nine, using `null` sides for explicit inactivity; aliases remain in `reference_checker_v2_config.json`.

| Current key | Canonical analyte | Keep as production record? | Reason |
|---|---|---|---|
| Potassium | Potassium | Yes | Canonical key |
| Kali | Potassium | No | Alias already resolves to Potassium |
| Glucose | Fasting plasma glucose | No | Alias currently resolves to repository canonical; identity review remains required |
| Fasting Plasma Glucose | Fasting plasma glucose | Yes, with exact canonical casing | Canonical detector lookup lowercases, but data quality should use repository spelling |
| WBC | WBC | Yes | Canonical key |
| HGB | HGB | Yes | Canonical key |
| Hemoglobin | HGB | No | Alias already resolves to HGB |
| LDL-C | LDL-C | Yes, inactive `null/null` | Explicit ARUP absence state |
| HbA1c | HbA1c | Yes, inactive `null/null` | Explicit ARUP absence state |
| HDL-C | HDL-C | Yes, inactive `null/null` | Explicit ARUP absence state |
| Creatinine | Creatinine | Yes, inactive `null/null` | Explicit ARUP absence state |
| RBC | RBC | Yes, inactive `null/null` | Explicit ARUP absence state |

No alias-config expansion is required for duplicate removal. Regression tests must prove `Kali`, `Glucose`, and `Hemoglobin` still reach the single canonical rule through `ReferenceRepository`.

---

## 10. Part 8 — sentinel migration plan

The existing loader and detector already tolerate `null`: `json.load()` yields `None`, and each comparison is guarded by `low_val is not None` / `high_val is not None`. Therefore no code patch is needed merely to replace `-1` with `null`. Schema validation and tests should prohibit numeric sentinels afterward.

| Analyte | Current sentinel | ARUP side exists? | Proposed representation |
|---|---|---|---|
| LDL-C | low `-1` | Neither side | `low: null, high: null` |
| HbA1c | low `-1` | Neither side | `low: null, high: null` |
| Creatinine | low `-1` | Neither side | `low: null, high: null` |
| RBC | low `-1`, high `-1` | Neither side | `low: null, high: null` |

Additional inactive sides without legacy sentinels also become explicit `null`: HGB high, HDL-C low/high, and the active highs being removed for LDL-C, HbA1c, and Creatinine.

Required tests:

- `null` sides never compare or alert.
- Active opposite sides continue to work (HGB low with high `null`).
- Negative numeric sentinels are rejected by data-quality validation.
- All nine canonical records contain explicit `low` and `high` keys.

`SENTINEL_MIGRATION_REQUIRED = YES`.

---

## 11. Part 9 — minimal provenance schema

### Existing loader behavior

`load_critical_thresholds()` loads the top-level JSON object and lowercases its keys. It does not validate an exact per-record schema. The detector reads only `low`, `high`, and `unit`; additional per-record fields do not currently break loading. A top-level envelope such as `{sources, rules}` would break the current lookup and data-quality tests, so it is not the minimal option.

### Proposed per-record shape

Keep the current flat top-level canonical records and add the smallest fields needed for exact execution and traceability:

```json
{
  "Potassium": {
    "low": 3.0,
    "low_operator": "<",
    "high": 6.1,
    "high_operator": ">",
    "unit": "mmol/L",
    "source_id": "SRC-CRIT-ARUP-REV46",
    "source_title": "CRITICAL VALUES LIST",
    "source_document_id": "CORP-APPEND-0104A",
    "source_revision": "46",
    "source_date": "2026-04",
    "source_url": "https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf",
    "source_page": 1,
    "source_literal": "<3.0 or >6.1 mmol/L",
    "population_context": null,
    "qualifier": null
  }
}
```

For inactive records, use `low: null`, `low_operator: null`, `high: null`, `high_operator: null`, `inactive_reason: "NO_ARUP_RULE"`, and the same `source_id`/document fields to make the bounded absence decision auditable. For converted rules, retain both `source_literal` and runtime canonical numeric/unit fields.

Extra provenance fields are loader-compatible today, but the operator fields require detector support. A validation patch should fail closed if an active rule lacks source ID, revision, page, literal, operator, or canonical unit. Thus a production data schema change is required even though a full loader redesign is not.

---

## 12. Part 10 — source registry

```yaml
source_id: SRC-CRIT-ARUP-REV46
organization: ARUP Laboratories
title: CRITICAL VALUES LIST
document_id: CORP-APPEND-0104A
revision: "46"
date: April 2026
url: https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf
status: DECLARED_VMEC_V1_OPERATIONAL_BENCHMARK
```

No secondary operational source record is permitted for V1.

---

## 13. Part 11 — test impact plan

### Existing detector/integration tests

| Existing test or group | Classification | Required impact |
|---|---|---|
| `test_detect_critical_values_node_legacy_mock` | `KEEP` | Values used remain critical/noncritical; update comments to cite ARUP semantics |
| `test_potassium_exact_critical_boundaries_software_execution` | `UPDATE_EXPECTED` | Replace old inclusive-boundary premise with strict ARUP boundary and epsilon/adjacent-value cases |
| `test_canonical_analyte_equivalence_potassium_and_kali` | `KEEP` | Proves alias works after duplicate data key removal |
| `test_canonical_analyte_equivalence_hgb_and_hemoglobin` | `KEEP` | 50 g/L remains below ARUP-derived adult threshold |
| canonicalization failure and upstream-unknown tests | `KEEP` | Safety mechanics must not regress |
| `test_shared_unit_normalizer_aliases_execute_correctly` | `UPDATE_EXPECTED` | WBC 35 is no longer high-critical; use 40 or greater. Replace Creatinine critical assertion with inactive behavior |
| `test_convertible_units_without_converters_fail_closed_standalone` | `UPDATE_EXPECTED` | After converter patch, supported Glucose/HGB conversions should execute; unsupported analyte/unit pairs must still fail closed |
| `test_canonical_unit_exact_execution` | `UPDATE_EXPECTED` | WBC 35 becomes noncritical; use 40 for inclusive high test; HGB 60 remains strict-low critical |
| `test_sentinel_threshold_regression_rbc_never_triggers` | `REPLACE_WITH_INACTIVE_TEST` | Remove sentinel premise; assert `null/null` never alerts |
| noncritical happy-path tests | `KEEP` | Normal values remain normal/noncritical |
| `test_non_critical_high_ri_status_not_escalated_if_below_critical_threshold` | `UPDATE_EXPECTED` | 5.5 remains noncritical, but comment/reference threshold changes from 6.5 to strict >6.1 |
| integration `test_e2e_11_potassium_critical_high` | `UPDATE_EXPECTED` | 6.5 still alerts, but add exact `6.1` noncritical boundary and >6.1 critical case |
| integration `test_e2e_12_kali_critical_low_alias_boundary` | `UPDATE_EXPECTED` | 2.5 remains critical but is no longer boundary; add exact 3.0 noncritical case |
| integration `test_e2e_13_multiple_indicator_order` | `KEEP` | Potassium 6.5 remains critical; order behavior unchanged |
| API `test_api_03_critical_serialization` | `KEEP` | Mocked response-contract test; not tied to detector data |

### Existing data-quality tests

| Existing test | Classification | Required impact |
|---|---|---|
| `test_crit_02_alias_values_consistent_in_critical_thresholds` | `DELETE_OBSOLETE` | Replace with assertion that alias keys are absent and all keys are canonical |
| `test_crit_03b_approved_analytes_in_critical_thresholds` | `KEEP` | All nine canonical records remain present, including explicit inactive records |
| `test_crit_03d_name_case_consistency_across_files` | `UPDATE_EXPECTED` | Remove hard-coded critical alias mapping and validate exact canonical casing |
| `test_crit_04b_critical_thresholds_unit_vs_units_csv` | `KEEP` | Runtime `unit` remains canonical; source literal unit is separately validated |
| `test_sync_16_critical_separation` | `KEEP` | Potassium canonical key remains present |

### Missing coverage that must be added

- Glucose strict source boundaries, both source-unit and canonical-unit paths, plus deterministic conversion precision.
- WBC inclusive `2.0/40` boundaries and U of U qualifier retained in provenance.
- HGB adult strict low boundary, high side inactive, and exact g/dL↔g/L conversion.
- LDL-C `5.3 mmol/L`, HbA1c `>9%`, HDL-C outside both old bounds, and Creatinine `>353.6 µmol/L` all remain RI abnormal where applicable but never become critical.
- RBC `null/null` inactivity.
- Schema validation for operators, provenance, source page/literal, canonical-only keys, and no negative sentinels.
- Full nine-analyte regression proving no secondary source values entered the target registry.

---

## 14. Part 12 — expected UI behavior impact

The frontend renders a red critical banner whenever `critical_alerts` is non-empty and gives critical indicator cards/badges when `is_critical` is true. No frontend code change is expected; backend classification changes alter the visible state.

| Analyte | Old behavior example | Expected ARUP-only behavior |
|---|---|---|
| Potassium | 2.8 or 6.2 mmol/L: not critical under old `<=2.5 / >=6.5` | 2.8 is `CRITICAL_LOW`; 6.2 is `CRITICAL_HIGH`; exact 3.0 and 6.1 are not critical because ARUP is strict |
| Glucose | Values >25 but <27.8 mmol/L: not high-critical | After approved conversion, values corresponding to `>450 mg/dL` become `CRITICAL_HIGH`; exact 450 mg/dL is not critical. Low side follows strict `<55 mg/dL` |
| WBC | 2.2 or 35 ×10^9/L: critical under old `<=2.5 / >=30` | Neither is critical; new inclusive boundaries are `<=2.0 / >=40`, subject to the retained U of U-only qualifier |
| HGB | 65 g/L: not critical; 200 g/L: `CRITICAL_HIGH` | 65 g/L becomes `CRITICAL_LOW`; 200 g/L has no adult ARUP high rule, so no critical alert/red banner from HGB high |
| LDL-C | 5.3 mmol/L: `CRITICAL_HIGH` with red banner | RI/CDL result may remain high according to separate reference logic, but no critical alert, critical card, or red banner |
| HbA1c | 10%: `CRITICAL_HIGH` | RI result may be high, but no critical alert or red banner |
| HDL-C | 0.5 or 2.5 mmol/L: critical low/high | RI result may be abnormal, but neither side creates a critical alert or red banner |
| Creatinine | 400 µmol/L: `CRITICAL_HIGH` | RI result may be high, but no critical alert or red banner |
| RBC | No critical alert because `-1/-1` sentinel | Still no critical alert; implementation becomes explicit `null/null` rather than sentinel-based |

History rows will likewise stop showing the red “Nguy kịch” badge when no remaining analyte creates a critical alert.

---

## 15. Part 13 — smallest ordered implementation plan

No patch below is implemented by this document.

### Patch A — schema, operator, and provenance support

- **Files:** `src/agents/nodes/critical_detector_node.py`; `tests/test_agents/test_critical_detector_node.py`; `tests/test_data/test_critical_data_quality.py`.
- **Why:** Current detector hard-codes inclusive operators and does not validate traceability.
- **Behavior changed:** Reads validated per-side operators; skips null sides; fails closed on malformed active records; messages show exact operator; active records require Rev.46 provenance.
- **Tests:** all four operators, invalid/missing operator, null side, missing provenance, exact alert text, loader with extra fields.
- **Regression risk:** critical alerts could be suppressed or expanded at boundaries if dispatch is wrong.
- **Must not change:** canonicalization fail-closed behavior, upstream `unknown` preservation, RI/CDL evaluation, API response shape, RAG, or UI.

### Patch B — deterministic unit conversion support

- **Files:** `src/services/reference_repository.py` (shared, analyte-aware conversion API without changing existing alias normalization); `src/agents/nodes/reference_range_checker_node.py`; `src/agents/nodes/critical_detector_node.py`; `tests/test_services/test_reference_repository.py`; `tests/test_agents/test_critical_detector_node.py`; `tests/test_integration/test_v2_reference_pipeline.py`.
- **Why:** ARUP adult Glucose is mg/dL while VMEC canonical is mmol/L; ARUP HGB is g/dL while canonical is g/L.
- **Behavior changed:** Approved analyte/unit pairs convert deterministically in both the upstream RI path and the critical comparison path; unsupported conversions still fail closed. This avoids the existing upstream `unknown` gate suppressing a valid source-unit critical comparison. Source literals remain unchanged in data.
- **Tests:** bidirectional/one-way policy as approved, Decimal precision, exact boundary behavior after conversion, WBC identity alias, unsupported pair rejection.
- **Regression risk:** floating/rounding errors could invert strict boundary behavior.
- **Must not change:** reference ranges, CDL bands, canonical units, or global string-only behavior of `normalize_unit()` for callers not requesting conversion.
- **Gate:** Human must approve the Glucose factor/precision/rounding policy before implementation.

### Patch C — canonical ARUP Rev.46 data migration

- **File:** `data/reference/critical_thresholds.json` only.
- **Why:** Replace unproven/hybrid values with the declared single benchmark.
- **Behavior changed:** Potassium, adult Glucose, WBC, and adult HGB-low use ARUP rules; HGB-high and all sides for LDL-C/HbA1c/HDL-C/Creatinine/RBC become null.
- **Tests:** source-literal golden extraction, exact operator/value/unit/provenance assertions, all-nine active/inactive matrix.
- **Regression risk:** incorrect transcription, accidental old-source value retention, or applying neonatal values to adults.
- **Must not change:** any reference range, alias config, explanation, test input catalog, or noncritical classification.

### Patch D — remove critical alias duplication

- **File:** `data/reference/critical_thresholds.json`; tests in `tests/test_data/test_critical_data_quality.py` and `tests/test_agents/test_critical_detector_node.py`.
- **Why:** One canonical record per medical rule; aliases already resolve through `ReferenceRepository`.
- **Behavior changed:** removes `Kali`, `Glucose`, and `Hemoglobin` duplicate records; normal alias inputs still resolve to canonical rules.
- **Tests:** alias equivalence for Potassium/Kali, HGB/Hemoglobin, and reviewed Glucose/Fasting mapping; assert alias keys absent.
- **Regression risk:** casing mismatch for `Fasting plasma glucose` could cause lookup failure.
- **Must not change:** `reference_checker_v2_config.json` aliases in this patch.

### Patch E — remove legacy sentinels

- **File:** `data/reference/critical_thresholds.json`; `tests/test_data/test_critical_data_quality.py`; `tests/test_agents/test_critical_detector_node.py`.
- **Why:** Missing sides must be explicit null, never magic `-1`.
- **Behavior changed:** inactive sides use null and never compare.
- **Tests:** no negative threshold values, null side safe, active opposite side works.
- **Regression risk:** an unguarded comparison with `None` would raise or suppress the opposite side.
- **Must not change:** inactive medical outcome for RBC and other absent rules.

### Patch F — update golden and integration tests

- **Files:** `tests/test_agents/test_critical_detector_node.py`, `tests/test_integration/test_v2_reference_pipeline.py`, `tests/test_data/test_critical_data_quality.py`, `tests/test_data/test_explanation_reference_sync.py` if its canonical-key assertion is tightened.
- **Why:** Old tests encode Rev.34-era/unproven values, inclusive semantics, alias duplication, and sentinels.
- **Behavior changed:** tests enforce Rev.46 source fidelity and ARUP-only inactivity.
- **Tests:** the complete impact list in Part 11.
- **Regression risk:** retaining a permissive old test could mask a hybrid value.
- **Must not change:** unrelated API, OCR, auth, history, DB, frontend, and RAG tests.

### Patch G — end-to-end safety regression

- **Files:** tests only unless a defect is found.
- **Why:** Verify current-nine behavior through reference checker → critical detector → API/UI contract.
- **Behavior changed:** none; verification gate.
- **Tests:** both sides and exact boundary for each active rule; every absent side; aliases; units; unsupported units; upstream unknown; alert deduplication; API serialization; patient/doctor/history red-banner presence or absence.
- **Regression risk:** cross-node status overwrite or stale module-level `CRITICAL_THRESHOLDS` during tests.
- **Must not change:** production data after the approved migration snapshot.

---

## 16. Part 14 — migration safety gate

| Gate | Current plan status |
|---|---|
| Official ARUP Rev.46 source verified | PASS |
| Human ARUP-only policy recorded | PASS |
| Every proposed active side maps to an ARUP rule | CONDITIONAL — Glucose/Fasting identity requires review; U of U qualifiers must be accepted/preserved |
| Absent sides explicitly inactive in target matrix | PASS (planned, not implemented) |
| Exact operators representable | FAIL in current runtime; Patch A required |
| Unit conversions deterministic | FAIL pending Glucose precision/rounding policy; Patch B required |
| No `-1` sentinel in proposed target | PASS in plan; not implemented |
| Canonical aliases do not duplicate medical records | PASS in plan; not implemented |
| Provenance attached to every active rule | PASS in proposed schema; not implemented |
| Test impact fully enumerated | PASS |

`ARUP_REGISTRY_MIGRATION_READY = NO` until the Glucose mapping and conversion precision are approved and Patches A–F are implemented and pass Patch G regression. This `NO` reflects current implementation readiness, not rejection of the frozen Human source policy.

---

## 17. Mandatory final answers

- **ARUP_REV46_VERIFIED = YES**
- **HUMAN_SOURCE_POLICY_RECORDED = YES**
- **CURRENT_ACTIVE_CANONICAL_ANALYTES = 8**
- **PROPOSED_ACTIVE_CANONICAL_ANALYTES = 4**
- **ANALYTES_BECOMING_INACTIVE = LDL-C, HbA1c, HDL-C, Creatinine**
- **SIDES_BECOMING_INACTIVE = HGB: HIGH; LDL-C: HIGH; HbA1c: HIGH; HDL-C: LOW, HIGH; Creatinine: HIGH**
- **NUMERIC_THRESHOLD_CHANGES_REQUIRED = YES**
- **OPERATOR_SUPPORT_PATCH_REQUIRED = YES**
- **UNIT_CONVERSION_PATCH_REQUIRED = YES**
- **SENTINEL_MIGRATION_REQUIRED = YES**
- **CRITICAL_ALIAS_DUPLICATION_CAN_BE_REMOVED = YES**
- **PROVENANCE_SCHEMA_CHANGE_REQUIRED = YES**
- **ARUP_REGISTRY_MIGRATION_READY = NO**
- **PRODUCTION_DATA_CHANGED = NO**
- **CODE_CHANGED = NO**
