# EXPLANATION / REFERENCE RANGE SYNCHRONIZATION REPORT

**TIP-ID:** BONUS-TIP-009  
**Date:** 2026-08-06  
**Branch:** `feature/TQT-reference-ragas`  
**Depends on:** BONUS-TIP-008 (unit-normalization fix)

---

## Summary

Three analytes were semantically absent from the V2 reference catalog (`reference_ranges_v2.json`) despite having curated explanation-range entries in `data/reference/explanations.json`. This report documents the synchronization of 15 explanation-derived supplemental rules into the catalog for HbA1c, LDL-C, and Potassium.

**Catalog presence is not runtime approval.** All three analytes remain pending in the normal reference checker. No approved-analyte list was changed.

---

## Input inventories

| Source | Count |
|---|---:|
| `explanations.json` entries | 9 |
| Primary catalog rules before sync | 58 |
| Supplemental rules added | 15 |
| Catalog total after sync | 73 |

---

## Alias resolution

| Explanation indicator | Canonical analyte | Before status | After status |
|---|---|---|---|
| WBC | WBC | already_present | already_present |
| RBC | RBC | already_present | already_present |
| HGB | HGB | already_present | already_present |
| Glucose | Fasting plasma glucose | alias_present | alias_present |
| HbA1c | HbA1c | missing | added |
| LDL-Cholesterol | LDL-C | missing | added |
| HDL-Cholesterol | HDL-C | alias_present | alias_present |
| Creatinine | Creatinine | already_present | already_present |
| Kali | Potassium | missing | added |

Alias resolution rules applied:
- `Glucose → Fasting plasma glucose`
- `LDL-Cholesterol → LDL-C`
- `HDL-Cholesterol → HDL-C`
- `Kali → Potassium`

---

## Semantic gaps

Analytes confirmed missing from primary catalog before synchronization:

| Analyte | Ranges in explanations.json | Quarantine rows (primary) | Conflict |
|---|---:|---:|---|
| HbA1c | 3 | 3 (range_flag_not_ok) | Boundary value: quarantine normal high=5.6 vs explanation normal high=5.7 |
| LDL-C | 5 | 5 (range_flag_not_ok) | Minor boundary differences in several groups |
| Potassium | 7 | 1 (range_flag_not_ok) | Normal upper: quarantine=5.3 vs explanation=5.0 |

---

## Cross-source conflict audit

### HbA1c
- **Primary source:** 3 rows (rows 62–64), all quarantined (`range_flag=MD → range_flag_not_ok`)
- **Quarantine ranges:** 0–5.6, 5.7–6.4, 6.5–NA
- **Explanation ranges:** null–5.7, 5.7–6.4, 6.5–null
- **Conflict:** Quarantine normal high=5.6 vs explanation normal high=5.7
- **Resolution:** Explanation values used; quarantine not deleted; conflict documented

### LDL-C
- **Primary source:** 5 rows (rows 77–81), all quarantined (`range_flag=MD`)
- **Quarantine ranges:** 0–2.59, 2.60–3.33, 3.36–4.11, 4.14–4.89, 4.91–NA
- **Explanation ranges:** null–2.58, 2.59–3.35, 3.36–4.13, 4.14–4.90, 4.91–null
- **Conflict:** Multiple boundary differences (quarantine lower bound=0 vs null; several upper boundary values differ by 0.01–0.02)
- **Resolution:** Explanation values used; quarantine not deleted; conflict documented

### Potassium
- **Primary source:** 1 row (row 38), quarantined (`range_flag=MD`)
- **Quarantine range:** 3.5–5.3 (RI type)
- **Explanation normal range:** 3.5–5.0
- **Conflict:** Normal upper: quarantine=5.3 vs explanation=5.0
- **Resolution:** Explanation values used; quarantine not deleted; conflict documented

---

## Supplemental mapping policy

- Supplemental rules use stable rule IDs in the `EXPV2-` namespace (separate from `RRV2-` primary IDs)
- Every supplemental rule records: `source_origin="explanations.json"`, `source_entry_id`, `range_group`, `range_note`, `source_url`, `source_urls`
- `confidence="CURATED"`, `range_flag="OK"`, `source_row_number=null`
- `source_priority_tier=null` — supplemental rules do not have a primary-source tier
- Provenance is preserved in both JSON and CSV output artifacts
- Primary primary-source counts (80/58/22/2) are unchanged in the build report

---

## Added analytes and rules

| Rule ID | Analyte | Group | Sex | Unit | Lower | Upper | Type |
|---|---|---|---|---|---:|---:|---|
| EXPV2-HBA1C-001 | HbA1c | normal | A | % | null | 5.7 | MD |
| EXPV2-HBA1C-002 | HbA1c | prediabetes | A | % | 5.7 | 6.4 | MD |
| EXPV2-HBA1C-003 | HbA1c | diabetes | A | % | 6.5 | null | MD |
| EXPV2-LDLC-001 | LDL-C | optimal | A | mmol/L | null | 2.58 | MD |
| EXPV2-LDLC-002 | LDL-C | acceptable | A | mmol/L | 2.59 | 3.35 | MD |
| EXPV2-LDLC-003 | LDL-C | borderline_high | A | mmol/L | 3.36 | 4.13 | MD |
| EXPV2-LDLC-004 | LDL-C | high | A | mmol/L | 4.14 | 4.9 | MD |
| EXPV2-LDLC-005 | LDL-C | very_high | A | mmol/L | 4.91 | null | MD |
| EXPV2-POTASSIUM-001 | Potassium | normal | A | mmol/L | 3.5 | 5.0 | RI |
| EXPV2-POTASSIUM-002 | Potassium | mild_hyperkalemia | A | mmol/L | 5.1 | 6.0 | MD |
| EXPV2-POTASSIUM-003 | Potassium | moderate_hyperkalemia | A | mmol/L | 6.1 | 7.0 | MD |
| EXPV2-POTASSIUM-004 | Potassium | severe_hyperkalemia | A | mmol/L | 7.0 | null | MD |
| EXPV2-POTASSIUM-005 | Potassium | mild_hypokalemia | A | mmol/L | 3.0 | 3.4 | MD |
| EXPV2-POTASSIUM-006 | Potassium | moderate_hypokalemia | A | mmol/L | 2.5 | 3.0 | MD |
| EXPV2-POTASSIUM-007 | Potassium | severe_hypokalemia | A | mmol/L | null | 2.5 | MD |

---

## Reference-type decisions

| Analyte | Groups | Reference type | Reason |
|---|---|---|---|
| HbA1c | all (normal, prediabetes, diabetes) | MD | Diagnostic/medical-decision thresholds; not a normal reference interval |
| LDL-C | all (optimal through very_high) | MD | Lipid decision limits; not a population-based normal RI |
| Potassium normal | normal | RI | Population-based normal interval; RI candidate |
| Potassium severity | mild/moderate/severe hypo/hyperkalemia | MD | Clinical severity categories; diagnostic thresholds |

---

## Boundary warnings

Inclusive boundary overlaps are preserved verbatim from `explanations.json`. Values are **not** altered.

| Analyte | Groups | Shared boundary value | Note |
|---|---|---:|---|
| HbA1c | normal / prediabetes | 5.7 % | normal upper=5.7 equals prediabetes lower=5.7 |
| Potassium | mild_hypokalemia / moderate_hypokalemia | 3.0 mmol/L | mild_hypo lower=3.0 equals moderate_hypo upper=3.0 |
| Potassium | moderate_hyperkalemia / severe_hyperkalemia | 7.0 mmol/L | moderate_hyper upper=7.0 equals severe_hyper lower=7.0 |

These overlaps are recorded as warnings in the build report (`explanation_supplement.boundary_warnings`). Since all overlapping groups are MD (or one RI candidate with no adjacent MD overlap), no normal-checker classification is affected.

---

## Runtime approval status

| Analyte | Catalog data available | Normal-reference runtime approved |
|---|---|---|
| HbA1c | YES (EXPV2-HBA1C-001/002/003) | NO — pending |
| LDL-C | YES (EXPV2-LDLC-001 through 005) | NO — pending |
| Potassium | YES (EXPV2-POTASSIUM-001 through 007) | NO — pending |
| WBC | YES (primary) | YES — approved |
| RBC | YES (primary) | YES — approved |
| Fasting plasma glucose | YES (primary) | YES — approved |
| Creatinine | YES (primary) | YES — approved |

---

## Primary and supplemental counts

| Counter | Value |
|---|---:|
| Primary source input rows | 80 |
| Primary accepted rows | 58 |
| Primary quarantined rows | 22 |
| Primary multiple-reason rows | 2 |
| Explanation entries scanned | 9 |
| Semantically missing analytes | 3 |
| Supplemental rules added | 15 |
| Catalog total rules | 73 |

The build report's `runtime_accepted_rows` remains 58 (primary only). The catalog total is tracked separately in `catalog.total_rules`.

---

## Generated artifacts

| File | Change |
|---|---|
| `data/reference/reference_ranges_v2.json` | +15 supplemental rules (EXPV2-*), total 73 |
| `data/reference/reference_ranges_v2.csv` | +15 supplemental rows with extended provenance columns, total 73 |
| `data/reference/reference_build_report.json` | Added `explanation_supplement` and `catalog` sections |

**Primary rules unchanged:** All 58 primary RRV2-* rules retain their original rule IDs, bounds, units, reference types, and source URLs.

**Quarantine unchanged:** Primary quarantine content (80–58=22 rows) is not modified.

---

## Tests

| Test file | Tests added | All pass |
|---|---:|---|
| `tests/test_data/test_explanation_reference_sync.py` | 21 | YES |
| Existing suite (231 → 252 passing) | 0 new failures | YES |

New tests cover: SYNC-01 through SYNC-20 (input inventory, alias resolution, missing detection, no-duplicate, rule count, stable IDs, provenance, analyte-specific mappings, units, primary rules unchanged, primary counts, catalog total, pending runtime safety, critical separation, boundary warnings, deterministic rebuild, JSON/CSV agreement, RAGAS unchanged).

---

## RAGAS impact

| Item | Status |
|---|---|
| `eval/datasets/ragas_v2_baseline.jsonl` hash | Unchanged |
| `eval/results/ragas_v2_baseline.json` hash | Unchanged |
| Live RAGAS calls | None |

The RAGAS baseline covers only the four approved analytes (WBC, RBC, Fasting plasma glucose, Creatinine). Supplemental rules for pending analytes have no effect on RAGAS.

---

## Remaining medical decisions

The following items require human medical and data owner decisions before HbA1c, LDL-C, or Potassium can be approved for normal-reference classification:

1. **HbA1c** — Catalog data available (3 MD rules). Normal RI approval requires medical/data owner confirmation that the MD-classified ranges are appropriate as a normal reference interval for the target population and measurement context.

2. **LDL-C** — Catalog data available (5 MD rules). Normal RI approval requires medical decision; LDL-C is classified as a medical-decision limit, not a population-based normal interval.

3. **Potassium** — Catalog data available (7 rules: 1 RI candidate + 6 MD). Normal RI approval for the RI candidate requires separate medical/data owner decision. Critical threshold classification remains owned by the Critical Detector independently of this TIP.

The four currently approved analytes (WBC, RBC, Fasting plasma glucose, Creatinine) are unaffected and continue to operate correctly.

---

## Post-VERIFY note

This synchronization was performed **after** TIP-006 VERIFY. The TIP-006 verification baseline covered the 58-rule primary catalog. This report adds supplemental catalog data for pending analytes without changing any approved-analyte behavior, primary catalog content, or RAGAS evaluation results.

Any future re-verification should confirm:
- Catalog total = 73 rules
- Primary counts unchanged (80/58/22/2)
- Supplemental analytes remain pending in normal checker
- Approved analytes (WBC, RBC, FPG, Creatinine) behavior unchanged
