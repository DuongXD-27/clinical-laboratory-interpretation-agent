# VMEC-05 DATA AUDIT V1

Audit date: 2026-08-14  
Mode: repository-consistency Pass 1, read-only; no web/external medical lookup  
Frozen scope: exactly 25 V1 analytes  
Audited artifacts: `data/reference/critical_thresholds.json`, `explanations.json`, `reference_build_report.json`, `reference_checker_v2_config.json`, `reference_ranges.json`, `units_metric.csv`, `templates.json`, plus the runtime loaders/checkers/detectors under `src/`.

## A. EXECUTIVE SUMMARY

- Scope: **25**
- READY: **0**
- NEEDS_REVIEW: **0**
- BLOCKED: **25**

```text
DATA_STABLE_V1 = NO
```

The current repository is not ready for the frozen Core 25:

1. `reference_ranges.json` contains rules for 23/25 analytes, but the runtime repository approves and resolves only 9/25. A direct read-only runtime lookup returned a rule for WBC, RBC, HGB, Fasting plasma glucose, HbA1c, LDL-C, HDL-C, Creatinine and Potassium; the other 16 returned `analyte_not_supported`.
2. Runtime explicitly permits only `RI`; it discards every `CDL` record before rule selection. This silently removes clinical-decision bands for Fasting plasma glucose, HbA1c, LDL-C, HDL-C and Potassium, and makes the CDL-only Total cholesterol and Triglyceride unusable.
3. Multi-band boundary semantics are not deterministic: there are explicit overlaps, explicit gaps, and adjacent decimal bands without a declared input-precision policy. The schema has no inclusive/exclusive fields.
4. The critical registry has 12 records (9 canonical analytes after alias grouping), but no record has source/provenance fields. Four records use `-1`; five threshold fields use that sentinel. The detector compares raw, uncanonicalized names and raw numeric values without validating or converting the unit.
5. eGFR and Uric acid are named as quarantined, but the quarantine artifact is absent and the build report simultaneously says `quarantined_rows=0` and lists six quarantined analytes. Their original quarantine reason cannot be proven from the repository.
6. Explanation data covers 9/25. The ingest job is separate, `data/chroma` is absent, and the deterministic analyte catalog deliberately stores `curated_explanation=""`; therefore repository state does not prove that even those nine entries are available to live RAG.

The decisive relation is:

```text
DATA_ACCEPTED != RUNTIME_SUPPORTED
23 Core-25 analytes have catalog records
9 Core-25 analytes are approved/resolvable at runtime
```

## B. 25-ANALYTE AUDIT MATRIX

Evidence tokens are resolved immediately after the matrix. Rule IDs are object identifiers in `data/reference/reference_ranges.json`.

| Panel | Analyte | Reference Data | Runtime Approval | Alias | Unit | Explanation | Critical | Boundary | Overall | Action |
| ----- | ------- | -------------- | ---------------- | ----- | ---- | ----------- | -------- | -------- | ------- | ------ |
| CBC | WBC | READY (RRV2-0002) | APPROVED (A1) | READY (L1) | READY (U1) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C1) | DETERMINISTIC (B1) | BLOCKED | REVIEW |
| CBC | RBC | READY (RRV2-0003/0004) | APPROVED (A1) | READY (L1) | READY (U1) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C2) | DETERMINISTIC (B1) | BLOCKED | REVIEW |
| CBC | HGB | READY (RRV2-0005/0006) | APPROVED (A1) | READY (L1) | READY (U1) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C1) | DETERMINISTIC (B1) | BLOCKED | REVIEW |
| CBC | HCT | READY (RRV2-0007/0008) | NOT_APPROVED (A2) | MISSING (L2) | READY (U1) | MISSING (X2) | MISSING_EXPECTED_RULE (C3) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| CBC | MCV | READY (RRV2-0009/0010) | NOT_APPROVED (A2) | MISSING (L2) | READY (U1) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| CBC | MCH | READY (RRV2-0011/0012) | NOT_APPROVED (A2) | MISSING (L2) | READY (U1) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| CBC | MCHC | READY (RRV2-0013/0014) | NOT_APPROVED (A2) | MISSING (L2) | READY (U1) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| CBC | PLT | READY (RRV2-0017/0018) | NOT_APPROVED (A2) | MISSING (L2) | READY (U1) | MISSING (X2) | MISSING_EXPECTED_RULE (C3) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| Glycemic | Fasting plasma glucose | CONFLICT (RRV2-0040/0060/0061) | APPROVED (A1) | READY (L1) | NEED_REVIEW (U2) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C1) | OVERLAP (B2) | BLOCKED | REVIEW |
| Glycemic | HbA1c | CONFLICT (EXPV2-HBA1C-001..003) | APPROVED (A1) | INCOMPLETE (L3) | READY (U1) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C2) | OVERLAP (B2) | BLOCKED | REVIEW |
| Lipid | Total cholesterol | CONFLICT (RRV2-0065..0067) | NOT_APPROVED (A2) | MISSING (L2) | NEED_REVIEW (U3) | MISSING (X2) | N/A (C4) | OVERLAP (B2) | BLOCKED | REVIEW |
| Lipid | LDL-C | CONFLICT (EXPV2-LDLC-001..005) | APPROVED (A1) | READY (L1) | NEED_REVIEW (U2) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C2) | AMBIGUOUS (B3) | BLOCKED | REVIEW |
| Lipid | HDL-C | CONFLICT (EXPV2-HDLC-001..005) | APPROVED (A1) | READY (L1) | NEED_REVIEW (U2) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C1) | OVERLAP (B2) | BLOCKED | REVIEW |
| Lipid | Triglyceride | CONFLICT (RRV2-0068..0071) | NOT_APPROVED (A2) | MISSING (L2) | NEED_REVIEW (U3) | MISSING (X2) | N/A (C4) | GAP (B4) | BLOCKED | REVIEW |
| Liver | ALT | READY (RRV2-0057) | NOT_APPROVED (A2) | MISSING (L2) | NEED_REVIEW (U4) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| Liver | AST | READY (RRV2-0056) | NOT_APPROVED (A2) | MISSING (L2) | NEED_REVIEW (U4) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| Liver | GGT | READY (RRV2-0058/0059) | NOT_APPROVED (A2) | MISSING (L2) | READY (U1) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| Liver | Albumin | READY (RRV2-0053) | NOT_APPROVED (A2) | MISSING (L2) | READY (U1) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| Renal | Creatinine | READY (RRV2-0042/0043) | APPROVED (A1) | INCOMPLETE (L3) | READY (U1) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C2) | DETERMINISTIC (B1) | BLOCKED | REVIEW |
| Renal | eGFR | QUARANTINED (Q1) | NOT_APPROVED (A2) | MISSING (L2) | NEED_REVIEW (U5) | MISSING (X2) | N/A (C4) | NOT_APPLICABLE | BLOCKED | BUILD |
| Renal | Urea | READY (RRV2-0041) | NOT_APPROVED (A2) | MISSING (L2) | READY (U1) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| Renal | Uric acid | QUARANTINED (Q1) | NOT_APPROVED (A2) | MISSING (L2) | NEED_REVIEW (U5) | MISSING (X2) | N/A (C4) | NOT_APPLICABLE | BLOCKED | BUILD |
| Electrolytes | Sodium | READY (RRV2-0037) | NOT_APPROVED (A2) | MISSING (L2) | NEED_REVIEW (U4) | MISSING (X2) | MISSING_EXPECTED_RULE (C3) | DETERMINISTIC (B1) | BLOCKED | BUILD |
| Electrolytes | Potassium | CONFLICT (EXPV2-POTASSIUM-001..007) | APPROVED (A1) | READY (L1) | READY (U1) | CONFLICT (X1) | OLD_RULE_NEEDS_REVIEW (C1) | OVERLAP (B2) | BLOCKED | REVIEW |
| Electrolytes | Chloride | READY (RRV2-0039) | NOT_APPROVED (A2) | MISSING (L2) | NEED_REVIEW (U4) | MISSING (X2) | N/A (C4) | DETERMINISTIC (B1) | BLOCKED | BUILD |

### Matrix evidence register

- **A1 — approved:** `data/reference/reference_checker_v2_config.json:4-13`, field `approved_analytes`; direct `ReferenceRepository.from_default_files()` returned the same nine. `src/services/reference_repository.py:92-101` calculates effective approval.
- **A2 — unsupported:** the other 16 have no entry in `analyte_aliases` (`reference_checker_v2_config.json:16-43`), so `resolve_analyte()` returns `None` (`reference_repository.py:276-277`) and `select_rule()` returns `analyte_not_supported` (`reference_repository.py:226-232`).
- **L1:** aliases are explicitly present at `reference_checker_v2_config.json:17-43`; examples include Vietnamese WBC/RBC/HGB names, Glucose/Fasting Blood Glucose, LDL-/HDL-Cholesterol, Kali and Potassium (K+).
- **L2:** canonical/alias is absent from the entire alias object; canonical names from `reference_ranges.json` are not automatically registered by runtime.
- **L3:** only the canonical spelling exists for HbA1c and Creatinine (`reference_checker_v2_config.json:37-38`); variants already anticipated elsewhere, such as `Hemoglobin A1c` (`src/models/db.py:303-306`), are not resolvable.
- **U1:** reference unit and `units_metric.csv` agree, and required symbol aliases are covered by `ReferenceRepository.normalize_unit()` (`reference_repository.py:297-313`).
- **U2:** reference/CSV use mmol/L, but runtime has no mg/dL↔mmol/L conversion; the normalizer only maps symbol spellings (`reference_repository.py:297-313`). The requested common incoming mg/dL path is therefore unsupported.
- **U3:** `units_metric.csv:24-25` says mg/dL for Total Cholesterol/Triglycerides, while the reference rules use mmol/L; no conversion exists.
- **U4:** units are numerically compatible, but CSV keys differ (`AST (GOT)`, `ALT (GPT)`, `Sodium (Na)`, `Chloride (Cl-)`) and no corresponding `unit_map_aliases` exist (`reference_checker_v2_config.json:51-55`). If approved as-is, `_find_unit_conflicts()` would remove them (`reference_repository.py:192-216`).
- **U5:** `units_metric.csv:33-34` defines a unit, but there is no reference rule/machine/display-unit record to cross-check; Uric acid also has a case/name mismatch (`Uric Acid` vs `Uric acid`).
- **X1:** `explanations.json` has entries for the nine approved analytes, but `src/services/analyte_catalog.py:104-111` sets `curated_explanation=""`; live text requires the separate ingest job (`src/scripts/ingest_kb.py:17-87`). `data/chroma` is absent, so runtime ingestion is not evidenced. Failure falls back to the generic template (`analyzer_node.py:103-107,126-138,164`; `templates.json:2`).
- **X2:** no entry exists in `explanations.json`; coverage is 9/25 (`reference_build_report.json:94-104` confirms only nine scanned).
- **C1:** active non-sentinel rule exists, but the JSON object contains only `low`, `high`, `unit` and no provenance. ADR-003 itself says a Potassium number was temporary/unverified (`docs/adr/adr-003-critical-value-detection.md:42-46`).
- **C2:** same missing provenance plus sentinel `-1` in at least one side (`critical_thresholds.json:6,10,12-13`).
- **C3:** no registry entry exists for a specifically requested critical-audit target (HCT, PLT, Sodium). Whether a rule is medically required is `EXTERNAL_MEDICAL_REVIEW_REQUIRED`; repository state cannot safely classify it as `NOT_REQUIRED`.
- **C4:** no registry rule and no repository evidence proving a panic-value rule is required; status remains `N/A`, not a medical assertion of “not required.”
- **B1:** exactly one applicable RI rule is selected after age/sex filtering; `_classify()` defines lower/upper edges inclusively (`reference_range_checker_node.py:68-83`).
- **B2/B3/B4:** see Section F. The catalog lacks inclusive/exclusive fields and a precision policy; the build report already records five inclusive overlaps (`reference_build_report.json:105-155`).
- **Q1:** `reference_build_report.json:50-56` names eGFR/Uric acid as quarantined, but the report says zero quarantined rows (`:7-13`) and the referenced `data/reference/quarantine_v2.csv` does not exist. See Section H.

### Reference rule inventory and runtime visibility

`Adult` is mapped by runtime to ages 18–60 inclusive (`reference_checker_v2_config.json:45-49`). Explicit `18–60` rows are parsed the same way. “A” means all sexes.

| Analyte | Rule IDs | Population / age / sex / specimen | Canonical unit | Type(s) | Runtime visibility |
| ------- | -------- | --------------------------------- | -------------- | ------- | ------------------ |
| WBC | RRV2-0002 | Adult 18–60; A; whole blood EDTA | 10^9/L | RI | RI selected |
| RBC | RRV2-0003/0004 | Adult 18–60; M/F; whole blood EDTA | 10^12/L | RI | sex-specific RI selected |
| HGB | RRV2-0005/0006 | Adult 18–60; M/F; whole blood EDTA | g/L | RI | sex-specific RI selected |
| HCT | RRV2-0007/0008 | Adult 18–60; M/F; whole blood EDTA | L/L | RI | rejected before rule lookup |
| MCV | RRV2-0009/0010 | Adult 18–60; M/F; whole blood EDTA | fL | RI | rejected before rule lookup |
| MCH | RRV2-0011/0012 | Adult 18–60; M/F; whole blood EDTA | pg | RI | rejected before rule lookup |
| MCHC | RRV2-0013/0014 | Adult 18–60; M/F; whole blood EDTA | g/L | RI | rejected before rule lookup |
| PLT | RRV2-0017/0018 | Adult 18–60; M/F; whole blood EDTA | 10^9/L | RI | rejected before rule lookup |
| Fasting plasma glucose | RRV2-0040/0060/0061 | Adult 18–60; A; fluoride plasma preferred | mmol/L | RI + CDL | only RRV2-0040 RI selected; CDL dropped |
| HbA1c | EXPV2-HBA1C-001..003 | Adult 18–60; A; specimen missing | % | RI + CDL | only EXPV2-HBA1C-001 RI selected; CDL dropped |
| Total cholesterol | RRV2-0065..0067 | Adult 18–60; A; serum/plasma | mmol/L | CDL only | alias/approval reject; CDL would also be dropped |
| LDL-C | EXPV2-LDLC-001..005 | Adult 18–60; A; specimen missing | mmol/L | RI + CDL | only EXPV2-LDLC-001 RI selected; CDL dropped |
| HDL-C | EXPV2-HDLC-001..005 | Adult 18–60; A/M/F; specimen missing | mmol/L | RI + CDL | sex-specific RI selected; CDL dropped |
| Triglyceride | RRV2-0068..0071 | Adult 18–60; A; serum/plasma | mmol/L | CDL only | alias/approval reject; CDL would also be dropped |
| ALT | RRV2-0057 | Adult 18–60; A; serum/plasma | U/L | RI | rejected before rule lookup |
| AST | RRV2-0056 | Adult 18–60; A; serum/plasma | U/L | RI | rejected before rule lookup |
| GGT | RRV2-0058/0059 | Adult 18–60; M/F; serum/plasma | U/L | RI | rejected before rule lookup |
| Albumin | RRV2-0053 | Adult 18–60; A; serum/plasma | g/L | RI | rejected before rule lookup |
| Creatinine | RRV2-0042/0043 | Adult 18–60; M/F; serum/plasma | umol/L | RI | sex-specific RI selected |
| eGFR | none | unknown; quarantine evidence missing | CSV only: mL/min/1.73 m^2 | none | rejected before rule lookup |
| Urea | RRV2-0041 | Adult 18–60; A; serum/plasma | mmol/L | RI | rejected before rule lookup |
| Uric acid | none | unknown; quarantine evidence missing | CSV only: µmol/L | none | rejected before rule lookup |
| Sodium | RRV2-0037 | Adult 18–60; A; serum/plasma | mmol/L | RI | rejected before rule lookup |
| Potassium | EXPV2-POTASSIUM-001..007 | Adult 18–60; A; specimen missing | mmol/L | RI + CDL | only EXPV2-POTASSIUM-001 RI selected; CDL dropped |
| Chloride | RRV2-0039 | Adult 18–60; A; serum/plasma | mmol/L | RI | rejected before rule lookup |

## C. P0 BLOCKERS

### P0-01 — Runtime scope is 9/25

```text
ID: P0-01
Severity: P0
Analyte: 16 unsupported Core-25 analytes
Evidence: reference_checker_v2_config.json:4-43; reference_repository.py:226-232,276-277
Runtime impact: HCT, MCV, MCH, MCHC, PLT, Total cholesterol, Triglyceride, ALT, AST, GGT, Albumin, eGFR, Urea, Uric acid, Sodium and Chloride return unknown without classification.
Recommended next action: Add explicit canonical/alias and approval decisions only after the data issues below are resolved; add a golden runtime lookup for all 25.
```

### P0-02 — CDL rules are silently discarded

```text
ID: P0-02
Severity: P0
Analyte: Fasting plasma glucose, HbA1c, Total cholesterol, LDL-C, HDL-C, Triglyceride, Potassium
Evidence: reference_checker_v2_config.json:3; reference_repository.py:238-242; rule IDs in Section B
Runtime impact: clinical decision bands are not loaded. Total cholesterol and Triglyceride have no RI fallback; the other five collapse to a single RI and cannot return their named CDL stages.
Recommended next action: Define V1 reference-type policy and value-aware multi-band selection; do not merely add CDL to allowed_reference_types because the current resolver returns ambiguous when multiple demographic candidates remain (reference_repository.py:263-267).
```

### P0-03 — Boundary semantics are unresolved

```text
ID: P0-03
Severity: P0
Analyte: Fasting plasma glucose, HbA1c, Total cholesterol, LDL-C, HDL-C, Triglyceride, Potassium
Evidence: Section F; reference_build_report.json:105-155; no inclusive flags in reference_repository.py:41-48
Runtime impact: a value can belong to two bands, no band, or depend on an unstated decimal-precision assumption. Current runtime avoids the problem only by discarding CDL, not by resolving it.
Recommended next action: Review source semantics and encode lower/upper inclusivity plus accepted precision; add one-result-per-value boundary tests.
```

### P0-04 — Critical registry has no traceable provenance

```text
ID: P0-04
Severity: P0
Analyte: all 9 canonical registry analytes
Evidence: critical_thresholds.json:2-13 contains only low/high/unit; ADR-003:42-46 acknowledges an unverified Potassium number
Runtime impact: 0/8 canonical analytes with an active threshold meet the 100%-provenance stability rule. LDL-C 4.91 exactly equals the “very_high” CDL lower bound (EXPV2-LDLC-005), and HbA1c 9.0 appears only as an educational “mức báo động” note (explanations.json:143-148); neither artifact proves a laboratory panic value.
Recommended next action: Clinical owner must trace every active low/high threshold to an actual critical/panic-value source; until then retain values unchanged but mark inactive/review-required by an approved process.
```

### P0-05 — Invalid `-1` sentinel design

```text
ID: P0-05
Severity: P0
Analyte: LDL-C, HbA1c, Creatinine, RBC
Evidence: critical_thresholds.json:6,10,12-13; critical_detector_node.py:62,75
Runtime impact: five fields encode “no threshold” as a numeric value. Runtime silently disables them via >=0 checks; RBC is present in the registry but has no active side at all.
Recommended next action: Replace sentinel semantics with explicit null/absent-side representation after schema and medical review; preserve existing numbers during this audit.
Flag: INVALID_SENTINEL_DESIGN
```

### P0-06 — Critical detector bypasses canonical aliases

```text
ID: P0-06
Severity: P0
Analyte: Fasting plasma glucose, Potassium, LDL-C, HDL-C (and any future alias)
Evidence: critical_detector_node.py:53-60 performs raw lowercase-key lookup; reference aliases are separate at reference_checker_v2_config.json:16-43
Runtime impact: direct runtime probes showed Fasting Blood Glucose, Potassium (K+), LDL-Cholesterol and HDL-Cholesterol were classified by the reference layer but produced zero critical alerts at the exact registry high thresholds. Canonical/selected aliases did alert.
Recommended next action: Resolve once to the same canonical analyte before both reference and critical lookup; add alias-equivalence critical tests.
```

### P0-07 — Critical detector ignores unit compatibility

```text
ID: P0-07
Severity: P0
Analyte: every active critical rule
Evidence: critical_detector_node.py:56-60 reads the threshold unit only for display and compares raw val at lines 62/75; no normalizer/converter is called
Runtime impact: direct probes marked Glucose 27.8 mg/dL, Potassium 6.5 mg/dL and WBC 30 10^12/L as critical against thresholds expressed in mmol/L, mmol/L and 10^9/L respectively.
Recommended next action: Reject or deterministically convert the input unit before comparison; critical comparison must use canonical value+unit.
```

### P0-08 — Unit conversion/scope is incomplete

```text
ID: P0-08
Severity: P0
Analyte: Fasting plasma glucose, Total cholesterol, LDL-C, HDL-C, Triglyceride
Evidence: units_metric.csv:22-27; reference rules in Section B; reference_repository.py:297-313
Runtime impact: no mg/dL↔mmol/L conversion exists. Total cholesterol and Triglyceride additionally conflict directly between CSV mg/dL and reference mmol/L.
Recommended next action: Approve a deterministic analyte-specific conversion and rounding policy, then test both input units at all boundaries. EXTERNAL_MEDICAL_REVIEW_REQUIRED for constants/rounding.
```

### P0-09 — eGFR and Uric acid are Core-25 but have no usable rule

```text
ID: P0-09
Severity: P0
Analyte: eGFR, Uric acid
Evidence: absent from reference_ranges.json/config aliases/approval; build report:50-56; direct lookup returned analyte_not_supported
Runtime impact: direct values read from a report cannot be classified. eGFR has no computation path, which is correct for V1 policy, but also has no direct-value stage/range path.
Recommended next action: Recover the missing source/quarantine evidence, approve direct-value rules only, and do not build CKD-EPI computation in V1.
```

### P0-10 — Build/quarantine report is internally inconsistent

```text
ID: P0-10
Severity: P0
Analyte: eGFR, Uric acid (plus four non-scope quarantined names)
Evidence: reference_build_report.json:7-13 says 80 accepted/0 quarantined, but :50-56 and :158-162 say six quarantined; output file at :87-90 is missing
Runtime impact: quarantine root cause and reproducibility cannot be audited; a reviewer cannot distinguish missing source, demographic, unit, schema or quality rejection.
Recommended next action: Reconcile report with the exact immutable input and quarantine artifact; verify all three output hashes in one build provenance record.
```

### P0-11 — Requested critical targets are absent

```text
ID: P0-11
Severity: P0 pending medical decision
Analyte: Sodium, HCT, PLT
Evidence: no key in critical_thresholds.json; user-requested critical audit target list
Runtime impact: no alert is possible for any value. Repository evidence cannot prove whether omission is intentional.
Recommended next action: EXTERNAL_MEDICAL_REVIEW_REQUIRED to decide whether a panic-value rule is expected; document an explicit NOT_REQUIRED decision or add a source-traced rule through review.
```

## D. P1 DATA GAPS

| ID | Gap | Evidence | Impact / action |
| -- | --- | -------- | --------------- |
| P1-01 | Explanation coverage is 9/25 | `explanations.json` names; `reference_build_report.json:94-104` | Add source-backed description/high/low content for the missing 16 only after content review. |
| P1-02 | RAG ingestion is not evidenced | `ingest_kb.py:17-87`; no `data/chroma`; `analyte_catalog.py:104-111` empties curated text | Nine data entries do not guarantee runtime retrieval; record collection version/count/hash in readiness/build evidence. |
| P1-03 | Alias coverage is 9/25 | `reference_checker_v2_config.json:16-43` | Add canonical names plus reviewed English/Vietnamese/OCR variants; avoid separate alias registries for reference and critical. |
| P1-04 | HbA1c and Creatinine aliases are thin | config lines 37-38; `db.py:303-306` anticipates Hemoglobin A1c | Add reviewed variants and tests; current exact-only lookup misses common spellings. |
| P1-05 | Supplemental specimen is null | all EXPV2 rules in `reference_ranges.json` | Confirm specimen applicability before enabling bands. |
| P1-06 | “Adult” means only 18–60 | config lines 45-49; repository lines 249-257 | Age 61+ and under-18 return unknown even where data label says Adult. Clarify population scope or add reviewed coverage. |
| P1-07 | Primary input is absent | build report line 3 names `adult_outpatient_laboratory_reference_map.csv`; file not in repo | Input hash cannot be independently verified or quarantine rebuilt. |
| P1-08 | Boundary warning generator is incomplete | extractor warnings lines 42-80 versus Section F | It reports five overlaps but omits Potassium 2.5, HDL 1.54 gap, Triglyceride 2.25/5.64 gaps and all precision ambiguities. |
| P1-09 | QA test enforces registry presence, not panic provenance | `tests/test_data/test_critical_data_quality.py:135-148,225-263` | Current tests can pass with sentinel or clinical-band-derived numbers; add schema/provenance/sentinel/alias-unit behavior checks. |

## E. CRITICAL REGISTRY AUDIT

No threshold was changed. `Provenance=MISSING` means there is no source URL/document/type in the registry record; an educational URL elsewhere is not accepted as panic-value provenance.

| Analyte / registry key | Old Low | Old High | Provenance | Assessment | Action |
| ---------------------- | ------: | -------: | ---------- | ---------- | ------ |
| Potassium | 2.5 | 6.5 | MISSING | OLD_RULE_NEEDS_REVIEW; active; duplicate of Kali | REVIEW |
| Kali | 2.5 | 6.5 | MISSING | OLD_RULE_NEEDS_REVIEW; alias duplicate; raw-key detector | REVIEW |
| Glucose | 3.0 | 27.8 | MISSING | OLD_RULE_NEEDS_REVIEW; duplicate canonical intent | REVIEW |
| Fasting Plasma Glucose | 3.0 | 27.8 | MISSING | OLD_RULE_NEEDS_REVIEW; duplicate; does not cover Fasting Blood Glucose | REVIEW |
| LDL-C | -1.0 | 4.91 | MISSING | OLD_RULE_NEEDS_REVIEW; INVALID_SENTINEL_DESIGN; high equals CDL “very_high” boundary | REVIEW |
| WBC | 2.5 | 30.0 | MISSING | OLD_RULE_NEEDS_REVIEW; active both sides | REVIEW |
| HGB | 60.0 | 200.0 | MISSING | OLD_RULE_NEEDS_REVIEW; active; duplicate of Hemoglobin | REVIEW |
| Hemoglobin | 60.0 | 200.0 | MISSING | OLD_RULE_NEEDS_REVIEW; alias duplicate | REVIEW |
| HbA1c | -1.0 | 9.0 | MISSING | OLD_RULE_NEEDS_REVIEW; INVALID_SENTINEL_DESIGN; 9% trace found only in educational note | REVIEW |
| HDL-C | 0.7 | 2.1 | MISSING | OLD_RULE_NEEDS_REVIEW; active; HDL-Cholesterol bypasses it | REVIEW |
| Creatinine | -1.0 | 353.6 | MISSING | OLD_RULE_NEEDS_REVIEW; INVALID_SENTINEL_DESIGN | REVIEW |
| RBC | -1.0 | -1.0 | MISSING | OLD_RULE_NEEDS_REVIEW; INVALID_SENTINEL_DESIGN; record has no active side | REVIEW |

Registry summary:

- Records: 12
- Canonical analytes after grouping aliases: 9
- Canonical analytes with at least one active side: 8
- Records with provenance: 0/12
- Active canonical analytes with provenance: 0/8
- Sentinel fields: 5 across 4 records
- Missing specifically requested targets: Sodium, HCT, PLT

## F. BOUNDARY AUDIT

The JSON schema has `range_lower`/`range_upper` only. It does not encode `<`, `<=`, `>`, `>=` or input precision. “Potential gap” below means the gap disappears only if an unstated precision is assumed; runtime accepts arbitrary `Decimal`, so that assumption is not enforceable.

| Analyte | Band A | Band B | Boundary | Problem | Evidence |
| ------- | ------ | ------ | -------: | ------- | -------- |
| Fasting plasma glucose | RI 4.1–6.1 | CDL 5.6–6.9 | 5.6–6.1 | REFERENCE_TYPE_OVERLAP; same values have RI-normal and CDL-band semantics | RRV2-0040 vs RRV2-0060 |
| Fasting plasma glucose | CDL 5.6–6.9 | CDL ≥7.0 | 6.9/7.0 | AMBIGUOUS precision; potential gap for arbitrary Decimal | RRV2-0060/0061 |
| HbA1c | RI normal 4.0–5.7 | CDL prediabetes 5.7–6.4 | 5.7 | BOUNDARY_OVERLAP | EXPV2-HBA1C-001/002; build report:107-115 |
| HbA1c | prediabetes ≤6.4 | diabetes ≥6.5 | 6.4/6.5 | AMBIGUOUS precision; potential gap | EXPV2-HBA1C-002/003 |
| Total cholesterol | desirable 0–5.18 | borderline 5.18–6.18 | 5.18 | BOUNDARY_OVERLAP | RRV2-0065/0066 |
| Total cholesterol | borderline ≤6.18 | high ≥6.19 | 6.18/6.19 | AMBIGUOUS precision; potential gap | RRV2-0066/0067 |
| LDL-C | optimal ≤2.58 | acceptable 2.59–3.35 | 2.58/2.59 | AMBIGUOUS precision; potential gap | EXPV2-LDLC-001/002 |
| LDL-C | acceptable ≤3.35 | borderline ≥3.36 | 3.35/3.36 | AMBIGUOUS precision; potential gap | EXPV2-LDLC-002/003 |
| LDL-C | borderline ≤4.13 | high ≥4.14 | 4.13/4.14 | AMBIGUOUS precision; potential gap | EXPV2-LDLC-003/004 |
| LDL-C | high ≤4.90 | very high ≥4.91 | 4.90/4.91 | AMBIGUOUS precision; potential gap | EXPV2-LDLC-004/005 |
| HDL-C male | low ≤1.04 | average 1.04–1.53 | 1.04 | BOUNDARY_OVERLAP after conversion/rounding | EXPV2-HDLC-005/003; build report:137-145 |
| HDL-C female | low ≤1.30 | average 1.30–1.53 | 1.30 | BOUNDARY_OVERLAP after conversion/rounding | EXPV2-HDLC-004/002; build report:147-155 |
| HDL-C M/F | average ≤1.53 | optimal ≥1.55 | 1.54 | BOUNDARY_GAP at declared 2-decimal converted precision | EXPV2-HDLC-002/003 vs 001; `conversion_rounding=ROUND_HALF_UP_2DP` |
| Triglyceride | normal ≤1.69 | borderline ≥1.70 | 1.69/1.70 | AMBIGUOUS precision; potential gap | RRV2-0068/0069 |
| Triglyceride | borderline ≤2.24 | high ≥2.26 | 2.25 | BOUNDARY_GAP | RRV2-0069/0070 |
| Triglyceride | high ≤5.63 | very high ≥5.65 | 5.64 | BOUNDARY_GAP | RRV2-0070/0071 |
| Potassium | severe hypo ≤2.5 | moderate hypo 2.5–3.0 | 2.5 | BOUNDARY_OVERLAP (omitted from build warnings) | EXPV2-POTASSIUM-007/006 |
| Potassium | moderate hypo ≤3.0 | mild hypo 3.0–3.4 | 3.0 | BOUNDARY_OVERLAP | EXPV2-POTASSIUM-006/005; build report:117-125 |
| Potassium | mild hypo ≤3.4 | RI normal ≥3.5 | 3.4/3.5 | AMBIGUOUS precision; potential gap | EXPV2-POTASSIUM-005/001 |
| Potassium | RI normal ≤5.0 | mild hyper ≥5.1 | 5.0/5.1 | AMBIGUOUS precision; potential gap | EXPV2-POTASSIUM-001/002 |
| Potassium | mild hyper ≤6.0 | moderate hyper ≥6.1 | 6.0/6.1 | AMBIGUOUS precision; potential gap | EXPV2-POTASSIUM-002/003 |
| Potassium | moderate hyper ≤7.0 | severe hyper ≥7.0 | 7.0 | BOUNDARY_OVERLAP | EXPV2-POTASSIUM-003/004; build report:127-135 |

The remaining single-RI analytes are deterministic only for the selected age/sex rule because `_classify()` uses `< lower`, `> upper`, otherwise normal. This does not make the unused multi-band catalog deterministic.

## G. UNIT AUDIT

### Runtime-supported symbol normalization

`ReferenceRepository.normalize_unit()` supports these spelling aliases only:

- `×10^9/L`, `10^9/L`, `10^3/uL`, `10^3/µL`, `10^3/μL`, `G/L` → `10^9/L`
- `×10^12/L`, `10^12/L`, `T/L` → `10^12/L`
- `µmol/L`, `μmol/L`, `umol/L` → `umol/L`

It does not perform numeric conversion.

| Analyte(s) | Reference unit | Units CSV | Runtime condition | Assessment / requirement |
| ---------- | -------------- | --------- | ----------------- | ------------------------ |
| WBC, PLT | 10^9/L | 10^9/L | symbol aliases supported | READY for listed aliases |
| RBC | 10^12/L | 10^12/L | symbol aliases supported | READY for listed aliases |
| Creatinine | umol/L | µmol/L | µ/μ/u aliases supported | READY |
| Fasting plasma glucose | mmol/L | mmol/L | mg/dL not converted | NEED_REVIEW; analyte-specific conversion and rounding required |
| LDL-C, HDL-C | mmol/L | mmol/L | mg/dL not converted | NEED_REVIEW; analyte-specific conversion and rounding required |
| Total cholesterol | mmol/L | mg/dL | direct file conflict; no key mapping/conversion | BLOCKING mismatch |
| Triglyceride | mmol/L | mg/dL | direct file conflict; plural key mismatch; no conversion | BLOCKING mismatch |
| ALT, AST | U/L | U/L under `ALT (GPT)`/`AST (GOT)` | no unit-map alias | Would be removed from approval as `unit_data_conflict` |
| Sodium, Chloride | mmol/L | mmol/L under decorated names | no unit-map alias | Would be removed from approval as `unit_data_conflict` |
| eGFR | no reference rule | mL/min/1.73 m^2 | cannot cross-check | NEED_REVIEW |
| Uric acid | no reference rule | µmol/L under `Uric Acid` | cannot cross-check; name mismatch | NEED_REVIEW |

Display/machine handling is also incomplete for supplemental HbA1c/LDL-C/HDL-C/Potassium rules: both unit fields exist, but specimen is null and accepted alternative input units are not represented as data. Unit compatibility is enforced as exact normalized equality at `reference_repository.py:244-247`.

## H. QUARANTINE ROOT CAUSE

### eGFR

V1 policy is respected in one narrow sense: no code computes eGFR from Creatinine. The graph only consumes reported indicators. However, direct-value support is absent.

What can be proven:

- `units_metric.csv:34` defines `eGFR,mL/min/1.73 m^2`.
- No eGFR rule/stage exists in `reference_ranges.json`.
- No eGFR canonical alias or approval exists in `reference_checker_v2_config.json`.
- Direct lookup returns `analyte_not_supported` before unit/range evaluation.
- `reference_build_report.json:56` calls eGFR quarantined.
- The report gives no row/reason and its claimed quarantine CSV is absent.

Root-cause conclusion:

```text
DATA QUARANTINE CAUSE = UNPROVABLE_FROM_CURRENT_REPOSITORY
RUNTIME REJECTION CAUSE = missing alias/approval + missing reference/stage rules
```

The repository cannot distinguish missing source, demographic, range, schema or quality flag. It is not a loader rejection of an existing eGFR rule; no rule reaches the loader. The builder only knows structural reasons (`missing_analyte`, `invalid_sex`, `missing_age_scope`, `missing_unit`, `missing_reference_type`, missing/invalid/reversed bounds at `build_reference_config.py:44-54,204-251`), but the report says zero structurally rejected rows. Claiming any one of those as the historical cause would be speculation.

To support a direct reported value in V1, reviewed stage/band records need analyte, population/age, sex, specimen, canonical unit, bounds with inclusive semantics, reference type and source provenance; then canonical alias/approval must be explicit. No CKD-EPI computation layer is recommended.

### Uric acid

What can be proven:

- `units_metric.csv:33` defines `Uric Acid,µmol/L`.
- No Uric acid rule exists in `reference_ranges.json`.
- No Uric acid canonical alias, `unit_map_alias` or approval exists in config.
- Direct lookup returns `analyte_not_supported`.
- `reference_build_report.json:55` calls it quarantined, but supplies no reason row and the quarantine CSV is absent.

Root-cause conclusion:

```text
DATA QUARANTINE CAUSE = UNPROVABLE_FROM_CURRENT_REPOSITORY
RUNTIME REJECTION CAUSE = missing alias/approval + missing reference rules
KNOWN UNIT ISSUE = CSV name/case cannot be mapped to canonical Uric acid as configured
```

There is evidence that a unit definition exists, so “missing unit” cannot be asserted for the present CSV catalog; whether the historical source row lacked a unit is unknowable without the missing input/quarantine artifact.

### Build report reconciliation

| Check | Reported | Repository observation | Assessment |
| ----- | -------- | ---------------------- | ---------- |
| Input rows | 80 | source input absent | hash/row count not independently verifiable |
| Runtime accepted rows | 80 | final JSON has 73 rules after replacement/supplement | definitions refer to different build stages |
| Accepted analytes | 34 | 23 are in Core 25 | DATA_ACCEPTED, not runtime approval |
| Quarantined rows | 0 | quarantine CSV absent | artifact hash cannot be verified |
| Quarantined analytes | 6 | list includes eGFR/Uric acid | internally contradicts zero rows and current builder logic |
| Runtime promoted | 3 | effective approved set is 9 | report is not a full runtime snapshot |
| Reference JSON hash | `8606...A25` | current file hash matches | verified |
| Reference CSV hash | `1761...660` | current file hash matches | verified |
| Quarantine hash | `1A7E...EC7E` | file missing | not verifiable |
| Boundary warnings | 5 overlaps | Section F finds additional overlap/gap/precision cases | incomplete |

## I. RECOMMENDED WORK ORDER

Minimal order to reach stable V1; this is a work queue, not an implementation in this audit:

1. **P0 correctness — freeze semantics first.** Decide which Core-25 rules are RI versus CDL, define value-aware multi-band selection, encode inclusive/exclusive bounds and precision, and resolve every Section F overlap/gap. Do not enable CDL in the current selector unchanged.
2. **Critical safety.** Obtain medical-owner decisions and panic-value provenance for every active side; decide Sodium/HCT/PLT explicitly; eliminate `-1` through an approved nullable schema; canonicalize aliases and units before critical comparison.
3. **Units.** Reconcile Total cholesterol/Triglyceride CSV-vs-reference units; approve analyte-specific mg/dL↔mmol/L conversions and rounding for glucose/lipids; complete unit-map aliases for decorated CSV names.
4. **Runtime scope.** Recover/reconcile the immutable build input and quarantine artifact, resolve eGFR/Uric acid direct-value data, then explicitly register aliases and approval for all 25. Keep eGFR as a reported value; no calculation layer.
5. **Explanations/RAG.** Expand 9/25 coverage with source-backed description/high/low fields; keep educational critical notes separate from panic thresholds; make corpus version/count/hash observable and supply a deterministic non-empty fallback if RAG is absent.
6. **Golden tests.** Add a 25-analyte matrix test; all aliases and common units; ages 18, 60, 61; both sexes; every exact/adjacent boundary; one-and-only-one band; critical alias equivalence; wrong-unit rejection; provenance completeness; no sentinels; build-report/hash/quarantine consistency.

Exit criteria remain strict: 25/25 explicit runtime states, zero unresolved overlap/gap, deterministic unit/alias handling, source-traced active critical registry, no `-1`, eGFR/Uric acid resolved, and no silent CDL filtering. Until all are met:

```text
DATA_STABLE_V1 = NO
```

## Audit execution note

- No repository code/data was changed; this Markdown report is the only created artifact.
- No web source was consulted.
- Direct runtime probes were read-only and used the repository's actual loaders.
- A targeted pytest invocation could not start its fixtures because the sandbox denied `C:\Users\duong\AppData\Local\Temp\pytest-of-duong` (`WinError 5`). This is an environment setup error, not a passing/failing assertion result; no alternative temp directory was created in order to preserve the read-only audit constraint.
