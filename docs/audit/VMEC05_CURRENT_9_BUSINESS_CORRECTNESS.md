# VMEC-05 — Current 9 Analytes Business Correctness Audit

**Role:** Senior Backend/Data QA Auditor  
**Date:** 2026-08-14  
**Status:** READ-ONLY — No code/data/config changes made  
**Scope:** WBC · RBC · HGB · Fasting plasma glucose · HbA1c · LDL-C · HDL-C · Creatinine · Potassium

---

## AUDIT SUMMARY

This document audits the **runtime behavior** of the 9 approved analytes in the VMEC-05 system.
It is derived entirely from repo evidence (code, data files, executed probes).
No medical thresholds were changed or inferred from memory.

---

## PART 1 — PIPELINE TRACE (4 analytes)

### 1A. WBC trace

| Step | File / Function | Input | Output |
|------|----------------|-------|--------|
| 1. Input | `AnalyzeRequest` / `IndicatorInputSchema` | `{name:"WBC", value:11.2, unit:"10^9/L"}` | Pydantic-validated dict |
| 2. State | `routes.py:run_analysis()` | `raw_indicators=[{...}]` | `initial_state` |
| 3. Graph entry | `graph.py:route_on_input()` | no `ocr_drafts` | → `reference_range_checker` |
| 4. Canonicalize | `reference_repository.py:resolve_analyte("WBC")` | `_alias_key("WBC")` → `"wbc"` | `"WBC"` (canonical) |
| 5. Approved? | `reference_repository.py:select_rule()` | canonical=`"WBC"`, in `approved_analytes` | passes |
| 6. Unit normalize | `normalize_unit("10^9/L")` | `"10^9/L"` | `"10^9/L"` (identity) |
| 7. Rule selected | `select_rule(...)` | canonical=WBC, unit=10^9/L, sex=M, age=35 | **rule_id=RRV2-0002** (sex=A, age=18-60, lower=4.72, upper=11.3) |
| 8. Classify | `_classify(11.2, 4.72, 11.3)` | 11.2 <= 11.3, >= 4.72 | **`normal`** |
| 9. Critical | `detect_critical_values_node()` | name_lower=`"wbc"`, CRITICAL_THRESHOLDS["wbc"]={low:2.5,high:30.0} | 11.2 < 30.0 → **no trigger** |
| 10. Final status | `indicators[0].status` | — | `"normal"` |

**Result:** WBC 11.2 → NORMAL. Consistent with observed UI.

---

### 1B. Potassium trace

| Step | File / Function | Input | Output |
|------|----------------|-------|--------|
| 1. Canonicalize | `resolve_analyte("Potassium")` | alias key `"potassium"` | `"Potassium"` |
| 2. Approved? | `approved_analytes` | `"Potassium"` in set | passes |
| 3. Unit normalize | `normalize_unit("mmol/L")` | `"mmol/L"` | `"mmol/L"` (identity) |
| 4. Rule selected | `select_rule()` | CDL rules filtered; only EXPV2-POTASSIUM-001 (RI) survives | lower=3.5, upper=5.0 |
| 5. Classify | `_classify(5.6, 3.5, 5.0)` | 5.6 > 5.0 | **`high`** |
| 6. Critical | CRITICAL_THRESHOLDS["potassium"]={low:2.5, high:6.5} | 5.6 < 6.5 → no trigger | **no trigger** |
| 7. Final | `status` | — | `"high"` |

**Result:** Potassium 5.6 mmol/L → HIGH. Rule correctly isolated to RI only (CDL rules filtered by `allowed_reference_types: ["RI"]`).

---

### 1C. Fasting plasma glucose trace

| Step | File / Function | Input | Output |
|------|----------------|-------|--------|
| 1. Canonicalize | `resolve_analyte("Glucose")` | alias key `"glucose"` | `"Fasting plasma glucose"` ⚠️ |
| 2. Approved? | `"Fasting plasma glucose"` in `approved_analytes` | yes | passes |
| 3. Unit normalize | `normalize_unit("mmol/L")` | — | `"mmol/L"` |
| 4. Rule selected | CDL rules filtered; only **RRV2-0040** (RI, lower=4.1, upper=6.1) survives | — | matched |
| 5. Classify | `_classify(6.2, 4.1, 6.1)` | 6.2 > 6.1 | **`high`** |
| 6. Critical | CRITICAL_THRESHOLDS["glucose"]={low:3.0, high:27.8} | 6.2 < 27.8 → no trigger | **no trigger** |
| 7. Final | `status` | — | `"high"` |

**Result:** FPG 6.2 → HIGH. RI classification correct given the rule.
**Issue found:** Generic "Glucose" resolves to "Fasting plasma glucose" — see Part 6.

---

### 1D. LDL-C trace

| Step | File / Function | Input | Output |
|------|----------------|-------|--------|
| 1. Canonicalize | `resolve_analyte("LDL-C")` | alias key `"ldl c"` | `"LDL-C"` |
| 2. Approved? | `"LDL-C"` in `approved_analytes` | yes | passes |
| 3. Unit normalize | `normalize_unit("mmol/L")` | — | `"mmol/L"` |
| 4. Rule filter | `allowed_reference_types: ["RI"]` | 5 rules; 4 CDL, 1 RI | Only **EXPV2-LDLC-001**: lower=None, upper=2.58 |
| 5. Classify | `_classify(5.3, None, 2.58)` | 5.3 > 2.58 | **`high`** |
| 6. Critical | CRITICAL_THRESHOLDS["ldl-c"]={low:-1.0, high:4.91} | low=-1.0 → low_val>=0 fails; 5.3 >= 4.91 → **`critical_high`** | critical_high |
| 7. Final | `status` overwritten | — | `"critical_high"` |

**Result:** LDL-C 5.3 → CRITICAL_HIGH.
**Issue found:** Critical trigger at 4.91 matches CDL band boundary, not a conventional panic value — see Part 7.

---

## PART 2 — DEFINITION OF "CORRECT" FOR CURRENT V1

- **RI status** (LOW/NORMAL/HIGH): single RI rule from `reference_ranges.json` after `allowed_reference_types: ["RI"]` filter
- **CRITICAL**: separate subsystem (`critical_detector_node.py`), runs AFTER RI checker
- HIGH RI does NOT automatically become CRITICAL
- CDL bands filtered at `select_rule()` — do NOT affect RI classification
- Three concepts remain separate:

```
RI status {low, normal, high}
  != critical status {critical_low, critical_high}  [critical_detector overrides]
  != CDL category {prediabetes, borderline_high...}  [not runtime-active]
```

---

## PART 3 — 9-ANALYTE CORRECTNESS MATRIX

| Analyte | Canonicalization | RI source | RI rule | Age | Sex | Unit | Boundary | Critical | Runtime result | Overall | Action |
|---------|-----------------|-----------|---------|-----|-----|------|---------|---------|---------------|---------|--------|
| WBC | "WBC"→"WBC" (direct) | RRV2-0002 | RI: 4.72–11.3 | Adult (18–60) | A | 10^9/L | inclusive | {low:2.5, high:30.0} active, unit-unsafe | Classifies | **NEEDS_FIX** | CRITICAL_REVIEW |
| RBC | "RBC"→"RBC" (direct) | RRV2-0003(M), RRV2-0004(F) | RI: M 4.45–6.19, F 4.01–5.48 | 18–60 | M/F | 10^12/L | correct | {low:-1.0, high:-1.0} sentinel inactive | Classifies by sex | **PASS** | KEEP |
| HGB | "HGB","Hemoglobin"→"HGB" | RRV2-0005(M), RRV2-0006(F) | RI: M 128–183, F 110–150 | 18–60 | M/F | g/L | correct | {low:60.0, high:200.0} unit-unsafe | Classifies | **NEEDS_FIX** | CRITICAL_REVIEW |
| Fasting plasma glucose | "Glucose"→"Fasting plasma glucose" ⚠️ | RRV2-0040 | RI: 4.1–6.1 | Adult | A | mmol/L | correct | {low:3.0, high:27.8} unit-unsafe | Classifies; alias contamination | **NEEDS_FIX** | DATA_FIX + CRITICAL_REVIEW |
| HbA1c | "HbA1c"→"HbA1c" | EXPV2-HBA1C-001 | RI: 4.0–5.7 | Adult | A | % | correct | {low:-1.0 sentinel, high:9.0} — no traceable panic provenance | Classifies | **NEEDS_FIX** | CRITICAL_REVIEW |
| LDL-C | "LDL-C","LDL-Cholesterol"→"LDL-C" | EXPV2-LDLC-001 | RI: upper only <=2.58 | Adult | A | mmol/L | upper-only | {low:-1.0, high:4.91} — matches CDL boundary | Classifies | **NEEDS_FIX** | CRITICAL_REVIEW |
| HDL-C | "HDL-C","HDL-Cholesterol"→"HDL-C" | EXPV2-HDLC-002(F), EXPV2-HDLC-003(M) | RI: F 1.30–1.53, M 1.04–1.53 | Adult | M/F | mmol/L | overlap noted in build report | {low:0.7, high:2.1} — no source | Classifies | **NEEDS_FIX** | CRITICAL_REVIEW |
| Creatinine | "Creatinine"→"Creatinine" | RRV2-0042(M), RRV2-0043(F) | RI: M 59–104, F 45–84 | Adult | M/F | umol/L | correct | {low:-1.0, high:353.6} low sentinel inactive | Classifies | **NEEDS_FIX** | CRITICAL_REVIEW |
| Potassium | "Kali","Potassium"→"Potassium" | EXPV2-POTASSIUM-001 | RI: 3.5–5.0 | Adult | A | mmol/L | correct | {low:2.5, high:6.5} unit-unsafe | Classifies | **NEEDS_FIX** | CRITICAL_REVIEW |

**Legend:** PASS=no action; NEEDS_FIX=confirmed issue with evidence; CRITICAL_REVIEW=critical threshold requires medical source review.

---

## PART 4 — REFERENCE RANGE AUDIT

### 4.1 WBC

| Field | Value |
|-------|-------|
| Rule ID | RRV2-0002 |
| Source URL | https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653 |
| Reference type | RI |
| Lower / Upper | 4.72 / 11.3 |
| Unit | 10^9/L |
| Age scope | `18-60` (range literal) |
| Sex scope | A (all) |
| Specimen | Whole blood EDTA |
| Fasting required | NO |
| Correct demographic rule selected? | YES (single rule, no ambiguity) |
| CDL contamination risk | None |
| Checker can stay? | **YES** |

### 4.2 RBC

| Field | Value |
|-------|-------|
| Rule IDs | RRV2-0003 (M), RRV2-0004 (F) |
| Source URL | https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653 (T1) |
| Reference type | RI |
| Lower / Upper | M: 4.45–6.19; F: 4.01–5.48 |
| Unit | 10^12/L |
| Age scope | `18-60` (range literal, not Adult alias — functionally equivalent) |
| Sex scope | M / F (no A fallback; "other" → unknown) |
| Specimen | Whole blood EDTA |
| Fasting required | NO |
| Correct demographic rule selected? | YES for M/F |
| CDL contamination risk | None |
| Checker can stay? | **YES** |

### 4.3 HGB

| Field | Value |
|-------|-------|
| Rule IDs | RRV2-0005 (M), RRV2-0006 (F) |
| Source URL | https://tapchiyhocvietnam.vn/index.php/vmj/article/download/9352/8252/16653 (T1) |
| Reference type | RI |
| Lower / Upper | M: 128–183; F: 110–150 |
| Unit | g/L |
| Age scope | `18-60` |
| Sex scope | M / F |
| Fasting required | NO |
| Correct rule selected? | YES for M/F |
| CDL contamination risk | None |
| Checker can stay? | **YES** |

### 4.4 Fasting plasma glucose

| Field | Value |
|-------|-------|
| Rule ID | RRV2-0040 |
| Source URL | https://tapchiyhocvietnam.vn/index.php/vmj/article/download/10898/9528/19171 (T1) |
| Reference type | RI |
| Lower / Upper | 4.1 / 6.1 |
| Unit | mmol/L |
| Age scope | Adult (→ 18–60) |
| Sex scope | A |
| Fasting required | Implied by name but NOT enforced at runtime |
| CDL contamination risk? | CDL rules RRV2-0060, RRV2-0061 exist but filtered by allowed_reference_types ✓ |
| Checker can stay? | **YES** — alias contamination is separate issue |

### 4.5 HbA1c

| Field | Value |
|-------|-------|
| Rule ID | EXPV2-HBA1C-001 |
| Source URL | https://diabetes.org/about-diabetes/a1c |
| Reference type | RI |
| Lower / Upper | 4.0 / 5.7 |
| Unit | % |
| Age scope | Adult |
| Sex scope | A |
| CDL contamination risk? | EXPV2-HBA1C-002, -003 are CDL — filtered ✓ |
| Boundary note | upper=5.7 overlaps prediabetes lower=5.7 (build report flagged). CDL filtered → RI only sees 4.0–5.7. Value exactly 5.7 → NORMAL. |
| Checker can stay? | **YES for RI** |

### 4.6 LDL-C

| Field | Value |
|-------|-------|
| Rule ID | EXPV2-LDLC-001 |
| Source URL | https://www.heart.org/en/health-topics/cholesterol/hdl-good-ldl-bad-cholesterol-... |
| Reference type | RI |
| Lower / Upper | None / 2.58 (upper-only) |
| Unit | mmol/L |
| Age scope | Adult |
| Sex scope | A |
| CDL contamination risk? | 4 CDL rules exist, all filtered ✓ |
| Upper-only behavior | Values <= 2.58 → NORMAL; values > 2.58 → HIGH. No LOW possible. |
| Source note | AHA uses < 100 mg/dL (2.59 mmol/L) as optimal. Rule uses <= 2.58. BOUNDARY_REVIEW_REQUIRED |
| Checker can stay? | **YES** |

### 4.7 HDL-C

| Field | Value |
|-------|-------|
| Rule IDs | EXPV2-HDLC-002 (F), EXPV2-HDLC-003 (M) |
| Source URL | https://www.heart.org/en/health-topics/cholesterol/hdl-good-ldl-bad-cholesterol-... |
| Reference type | RI |
| Lower / Upper | M: 1.04–1.53; F: 1.30–1.53 |
| Unit | mmol/L |
| Age scope | Adult |
| Sex scope | M / F |
| CDL contamination risk? | 3 CDL rules exist, all filtered ✓ |
| Boundary note | Build report: 1.04(M)/1.30(F) are shared with CDL-low upper. CDL filtered → runtime: exactly 1.04/1.30 → NORMAL (>= lower). |
| Checker can stay? | **YES** |

### 4.8 Creatinine

| Field | Value |
|-------|-------|
| Rule IDs | RRV2-0042 (M), RRV2-0043 (F) |
| Source URL | https://www.uhnm.nhs.uk/our-services/pathology/tests/creatinine/ |
| Reference type | RI |
| Lower / Upper | M: 59–104; F: 45–84 |
| Unit | umol/L |
| Age scope | Adult |
| Sex scope | M / F |
| CDL contamination risk? | None present |
| Note | unit_machine=µmol/L, unit_canonical=umol/L; normalize_unit() maps µ→u ✓ |
| Checker can stay? | **YES** |

### 4.9 Potassium

| Field | Value |
|-------|-------|
| Rule ID | EXPV2-POTASSIUM-001 |
| Source URL | https://www.vinmec.com/vie/bai-viet/kali-mau-bao-nhieu-la-binh-thuong-vi |
| Reference type | RI |
| Lower / Upper | 3.5 / 5.0 |
| Unit | mmol/L |
| Age scope | Adult |
| Sex scope | A |
| CDL contamination risk? | 6 CDL rules exist, all filtered ✓ |
| Source tier | Vinmec = T2 hospital source (not primary guideline). SOURCE_REVIEW recommended. |
| Checker can stay? | **YES** |

---

## PART 5 — BOUNDARY CORRECTNESS

**Runtime semantics** (`reference_range_checker_node.py:_classify()`):

```python
if value < lower:  → "low"
if value > upper:  → "high"
else:              → "normal"   # [lower, upper] inclusive
```

| Analyte | Boundary | Runtime behavior | Source evidence | Correct? | Action |
|---------|---------|-----------------|----------------|---------|--------|
| WBC | lower=4.72 | 4.72 → normal (inclusive) | VMJ article: semantics not specified | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| WBC | upper=11.3 | 11.3 → normal (inclusive) | Same | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| RBC (M) | lower=4.45, upper=6.19 | inclusive | VMJ article | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| RBC (F) | lower=4.01, upper=5.48 | inclusive | Same | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| HGB (M) | lower=128, upper=183 | inclusive | VMJ article | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| HGB (F) | lower=110, upper=150 | inclusive | Same | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| FPG | lower=4.1, upper=6.1 | inclusive | VN internal medicine journal | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| HbA1c | lower=4.0, upper=5.7 | inclusive (5.7 → normal) | diabetes.org: "below 5.7%" implies strict < 5.7; runtime uses <= 5.7 | BOUNDARY_SEMANTICS_REVIEW_REQUIRED | SOURCE_REVIEW |
| LDL-C | upper=2.58 | inclusive | AHA: < 100 mg/dL = < 2.59 mmol/L; 2.58 <= 2.58 → normal consistent | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| HDL-C (M) | lower=1.04 | inclusive | AHA: 40 mg/dL = 1.036 mmol/L rounded to 1.04 | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| HDL-C (F) | lower=1.30 | inclusive | AHA: 50 mg/dL = 1.295 mmol/L rounded to 1.30 | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| Creatinine (M) | lower=59, upper=104 | inclusive | UHNM: "59–104 µmol/L" — typically inclusive | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| Creatinine (F) | lower=45, upper=84 | inclusive | UHNM: "45–84 µmol/L" | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |
| Potassium | lower=3.5, upper=5.0 | inclusive | Vinmec: "3.5–5.0" — typically inclusive | BOUNDARY_REVIEW_REQUIRED | SOURCE_REVIEW |

**HbA1c boundary note:** diabetes.org states "normal: below 5.7%", implying strict `< 5.7`. Runtime uses `<= 5.7` (inclusive upper). Value exactly 5.7% → NORMAL by runtime. The source semantics are disputed. **BOUNDARY_SEMANTICS_REVIEW_REQUIRED.** If `< 5.7` must be represented exactly, a future implementation must either (A) adopt an explicit validated precision policy, or (B) make a minimal boundary-operator extension. Do not use numeric threshold manipulation (e.g., 5.69) to simulate exclusive boundaries without an explicit precision contract.

---

## PART 6 — FASTING GLUCOSE CANONICALIZATION

**Current config** (`reference_checker_v2_config.json` lines 29-34):

```json
"Glucose":                 "Fasting plasma glucose",   <- GENERIC -> FPG (ISSUE)
"Duong huyet":             "Fasting plasma glucose",   <- GENERIC -> FPG (ISSUE)
"Duong huyet luc doi":     "Fasting plasma glucose",   <- context-specific OK
"Glucose mau luc doi":     "Fasting plasma glucose",   <- context-specific OK
"Fasting Blood Glucose":   "Fasting plasma glucose",   <- context-specific OK
"Fasting plasma glucose":  "Fasting plasma glucose"    <- canonical OK
```

**A. Generic "Glucose" mapped to "Fasting plasma glucose"?**
YES. Config line 29. Runtime probe confirmed: `resolve_analyte("Glucose")` → `"Fasting plasma glucose"`.

**B. Can this cause non-fasting glucose to use FPG RI?**
YES. Post-prandial glucose of 7.8 mmol/L with name="Glucose" → HIGH (FPG RI 4.1–6.1). This is clinically misleading. **P1 business correctness bug.**

**C. Where is fasting context obtained?**
Nowhere. No `fasting_required` enforcement in `reference_range_checker_node.py`. The `fasting_required` field in rules is never read by the checker.

**D. Does parser/OCR/manual input pass fasting evidence?**
NO. `IndicatorInputSchema` has only `{name, value, unit}`. No `fasting_context` field anywhere.

**E. Minimal safe fix:**
Remove "Glucose" and "Duong huyet" from alias map. They should return `unknown` (no RI classification) until fasting context is explicitly established. Do NOT implement in this task.

**Business rule violation confirmed:** Generic analyte naming ("Glucose") silently creates fasting context that does not exist.

---

## PART 7 — CRITICAL REGISTRY AUDIT

**File:** `data/reference/critical_thresholds.json`

| Analyte | Current low | Current high | Unit | Active? | Source/provenance | Looks like clinical band? | Assessment |
|---------|------------|-------------|------|---------|-----------------|--------------------------|-----------|
| Potassium | 2.5 | 6.5 | mmol/L | YES | No source field | No clear CDL-band match; no source field | NEEDS_SOURCE_VERIFICATION |
| Kali | 2.5 | 6.5 | mmol/L | YES (alias) | Same as Potassium | No clear CDL-band match | NEEDS_SOURCE_VERIFICATION |
| Glucose | 3.0 | 27.8 | mmol/L | YES | No source field | No clear CDL-band match; 27.8 mmol/L cited in some panic references but unverified | NEEDS_SOURCE_VERIFICATION |
| Fasting Plasma Glucose | 3.0 | 27.8 | mmol/L | YES (alias) | Same as Glucose | Same | NEEDS_SOURCE_VERIFICATION |
| LDL-C | -1.0 | 4.91 | mmol/L | Partially (high only, low=-1 inactive) | No source field | **YES — 4.91 = EXPV2-LDLC-005 CDL lower boundary** | LIKELY_CLINICAL_BAND_CONTAMINATION |
| WBC | 2.5 | 30.0 | 10^9/L | YES | No source field | No clear CDL-band match; no source field | NEEDS_SOURCE_VERIFICATION |
| HGB | 60.0 | 200.0 | g/L | YES | No source field | 60 g/L = severe anemia (conventional), 200 unverified | NEEDS_SOURCE_VERIFICATION |
| Hemoglobin | 60.0 | 200.0 | g/L | YES (alias) | Same as HGB | Same | NEEDS_SOURCE_VERIFICATION |
| HbA1c | -1.0 | 9.0 | % | Partially (high only, low=-1 sentinel inactive) | No source field | No traceable critical/panic-value provenance in repository | NEEDS_SOURCE_VERIFICATION |
| HDL-C | 0.7 | 2.1 | mmol/L | YES | No source field | No clear CDL-band match; no traceable panic-value provenance | NEEDS_SOURCE_VERIFICATION |
| Creatinine | -1.0 | 353.6 | umol/L | Partially (high only, low=-1 sentinel inactive) | No source field | No clear CDL-band match; no traceable panic-value provenance | NEEDS_SOURCE_VERIFICATION |
| RBC | -1.0 | -1.0 | 10^12/L | **NO** (-1 sentinel inactive at runtime due to `low_val >= 0` guard) | — | — | NO_ACTIVE_THRESHOLD — see sentinel note |

**Key findings:**
- **LDL-C high=4.91:** Exactly matches `EXPV2-LDLC-005.range_lower=4.91` (CDL "very_high" band). This numeric coincidence is evidence of suspicious clinical-band contamination. It does not prove that no critical threshold exists for LDL-C — medical source review is required to confirm or deny. → **LIKELY_CLINICAL_BAND_CONTAMINATION; pending source review**
- **HbA1c high=9.0:** No traceable critical/panic-value provenance in the repository. Do not infer its clinical origin; the only justified repository conclusion is that it lacks verifiable panic provenance. → **NEEDS_SOURCE_VERIFICATION; do not assume absence or presence of a panic threshold without authoritative source review**
- **RBC -1/-1:** Currently runtime-inactive due to the `low_val >= 0` guard — no false critical alerts are produced. However, using -1 as a sentinel in a numeric threshold field is **legacy technical debt**: it relies on an implicit guard that is not documented or enforced by the data schema. A future code change removing that guard would cause -1 to trigger false critical alerts. This encoding should not be described as correct data design.
- **Alias duplicates** (Potassium/Kali, HGB/Hemoglobin, Glucose/FPG): confirm critical detector does NOT canonicalize — uses raw name lookup. Any alias missing from the JSON is silently skipped.

---

## PART 8 — CRITICAL DETECTOR SOFTWARE BEHAVIOR

**File:** `src/agents/nodes/critical_detector_node.py`

**Q1: Canonicalize analyte before lookup?**
NO. Uses `name.lower()` only. CRITICAL_THRESHOLDS already lowercased at load time. Case-insensitive string match, not alias canonicalization.

**Q2: Alias variants give same result?**
PARTIALLY. Potassium/Kali YES (separate entries). HGB/Hemoglobin YES. Glucose/FPG YES. But a typo like "HBG" → NOT in registry → no trigger. Not canonicalized via ReferenceRepository.

**Q3: Validates unit?**
**NO.** Unit only used in alert message string. Never compared against threshold unit. This means no analyte-aware unit compatibility check is performed before the numeric comparison.

**Q4: Converts units?**
**NO.** No numeric conversion of any kind.

**Q5: Compares raw numeric value regardless of unit?**
**YES. P0 BUG.** Raw float from `ind["value"]` compared directly against threshold floats with no unit canonicalization, no analyte-aware compatibility check, and no fail-closed behavior when units differ.

**Probe evidence (executed):**
```
critical_check('Potassium', 6.5, 'mEq/L')   = critical_high
  NOTE: For K+ (monovalent), 1 mEq == 1 mmol (EQUIVALENT_ALIAS).
  The numeric result happens to be clinically valid for K+, but only by
  accident because the code performs no unit verification.
  For multivalent ions, mEq/L != mmol/L.

critical_check('Potassium', 6500, 'umol/L') = critical_high
  NOTE: µmol/L and mmol/L are CONVERTIBLE SI units (6500 µmol/L = 6.5 mmol/L).
  However, without numeric conversion implemented in V1, raw float comparison (6500 >= 6.5)
  triggers a false critical. When numeric conversion is absent, the system must fail closed.

critical_check('Glucose', 27.8, 'mg/dL')    = critical_high
  NOTE: mg/dL is CONVERTIBLE to mmol/L (27.8 mg/dL ≈ 1.54 mmol/L, not critical).
  Raw comparison triggers false critical high. Must fail closed in V1 without converter.

critical_check('HGB', 60, 'g/dL')           = critical_low
  NOTE: g/dL is CONVERTIBLE to g/L (60 g/dL = 600 g/L).
  Raw comparison triggers false critical low. Must fail closed in V1 without converter.
critical_check('Hemoglobin', 60, 'g/L')     = critical_low   <- correct unit, correct
critical_check('HBG', 60, 'g/L')            = NOT_IN_CRITICAL_REGISTRY  <- typo safe
critical_check('LDL-C', 4.91, 'mmol/L')    = critical_high  <- triggers at >=4.91
critical_check('LDL-C', 4.90, 'mmol/L')    = no_trigger     <- correct
critical_check('RBC', 4.0, '10^12/L')       = no_trigger     <- -1 sentinel; inactive by guard
```

**Q6: Handles -1?**
Currently runtime-inactive (by guard). `low_val >= 0` condition means -1 never satisfies → no trigger. RBC -1/-1 → always no trigger at runtime. **However, -1 as a numeric sentinel in a threshold field is legacy technical debt** — the `>= 0` guard is implicit, undocumented in the data schema, and could be broken by future refactoring. The fact that no false alert is produced today does not make this a safe long-term encoding.

**Q7: CRITICAL overwrites RI status?**
YES. `new_ind["status"] = "critical_low"` overwrites whatever RI checker set. Intended behavior.

**Q8: Field triggering red banner?**
`has_critical_values: bool` in `AnalyzeResponse`. Also `is_critical: bool` per indicator. `critical_alerts: list`. Frontend reads all three.

**P0 CONFIRMED:** No unit validation in critical detector. Wrong unit inputs produce incorrect critical classifications.

---

## PART 9 — UNIT CORRECTNESS

### Unit Compatibility Taxonomy

To ensure robust and clinically safe unit handling across all components, units are categorized into three explicit classes:

1. **`EQUIVALENT_ALIAS`**: Same physical quantity and identical numeric value after symbol/canonical normalization.
   - Examples: `µmol/L` ↔ `umol/L`, `×10^9/L` ↔ `10^9/L`, `10^3/uL` ↔ `10^9/L`, `G/L` ↔ `10^9/L`.
   - Analyte-specific: `mEq/L` ↔ `mmol/L` for monovalent ions only (e.g., $K^+$).
   - Runtime action: Standard symbol normalization; directly comparable without numeric transformation.

2. **`CONVERTIBLE`**: Same physical quantity but measured in different unit scales, requiring explicit numeric conversion factors.
   - Examples: `µmol/L` ↔ `mmol/L` (factor $10^{-3}$; e.g., $6500	ext{ }\mu	ext{mol/L} = 6.5	ext{ mmol/L}$), `mg/dL` ↔ `mmol/L` (molar-mass dependent, e.g., Glucose factor $1/18.016$, Cholesterol factor $1/38.67$), `g/dL` ↔ `g/L` (factor $10$).
   - Current V1 Policy: If a `CONVERTIBLE` unit does not have an approved/implemented numeric conversion at runtime, the Critical Detector **must fail closed** (suppress critical comparison and report conversion unavailable) rather than executing an erroneous raw numeric comparison.

3. **`UNSUPPORTED_OR_INCOMPATIBLE`**: Units representing different physical dimensions or invalid units for the analyte (e.g., `mg/dL` for WBC).
   - Current V1 Policy: Reject immediately / return `unknown` in RI checker, fail closed in Critical Detector.

| Analyte | Runtime RI unit | Input units accepted | Unit Taxonomy Class | Numeric conversion in V1 | Critical unit-safe in V1? |
|---------|----------------|---------------------|--------------------|--------------------------|--------------------------|
| WBC | 10^9/L | 10^9/L, x10^9/L, 10^3/uL, 10^3/µL, G/L | EQUIVALENT_ALIAS | NO_CONVERSION_NEEDED | **NO** — unit check absent; unverified/incompatible units compared raw |
| RBC | 10^12/L | 10^12/L, x10^12/L, T/L | EQUIVALENT_ALIAS | NO_CONVERSION_NEEDED | N/A — critical sentinel -1/-1 inactive at runtime |
| HGB | g/L | g/L | EQUIVALENT_ALIAS | CONVERTIBLE (g/dL ↔ g/L factor 10) | **NO** — g/dL (CONVERTIBLE) compared raw without conversion |
| Fasting plasma glucose | mmol/L | mmol/L | EQUIVALENT_ALIAS | CONVERTIBLE (mg/dL ↔ mmol/L) | **NO** — mg/dL (CONVERTIBLE) compared raw without conversion |
| HbA1c | % | % | EQUIVALENT_ALIAS | NO_CONVERSION_NEEDED | **NO** — unit check absent |
| LDL-C | mmol/L | mmol/L | EQUIVALENT_ALIAS | CONVERTIBLE (mg/dL ↔ mmol/L) | **NO** — mg/dL (CONVERTIBLE) compared raw without conversion |
| HDL-C | mmol/L | mmol/L | EQUIVALENT_ALIAS | CONVERTIBLE (mg/dL ↔ mmol/L) | **NO** — unit check absent |
| Creatinine | umol/L | umol/L, µmol/L, μmol/L | EQUIVALENT_ALIAS | CONVERTIBLE (mg/dL ↔ umol/L factor ~88.4) | **NO** — mg/dL (CONVERTIBLE) compared raw without conversion |
| Potassium | mmol/L | mmol/L, mEq/L (monovalent) | EQUIVALENT_ALIAS (mEq/L for K+ only) | CONVERTIBLE (µmol/L ↔ mmol/L factor $10^{-3}$) | **NO** — µmol/L (CONVERTIBLE) compared raw without conversion (6500 vs 6.5); mEq/L works only by coincidence |

**Key findings:**
1. `normalize_unit()` in `reference_repository.py`: handles symbol normalization only (`µ`→`u`, `G/L`→`10^9/L`, `T/L`→`10^12/L`, `10^3/uL`→`10^9/L`). No numeric conversion is implemented.
2. RI checker rejects unsupported units (`unit_not_supported` → `unknown`).
3. Critical detector: NO unit validation or conversion check — P0 bug.
4. Units CSV Creatinine entry `µmol/L` → rule `unit_canonical=umol/L` → `normalize_unit("µmol/L")` → `"umol/L"` ✓ No conflict.

---

## PART 10 — AGE / SEX CORRECTNESS

### Age Scope

| Analyte | Age scope value | Parsed as | Min | Max | age=18? | age=60? | age=61? | age=17? |
|---------|----------------|-----------|-----|-----|---------|---------|---------|---------|
| WBC | "18-60" (literal) | AgeRange(18, 60) | 18 | 60 | YES | YES | NO → unknown | NO |
| RBC | "18-60" | same | 18 | 60 | YES | YES | NO | NO |
| HGB | "18-60" | same | 18 | 60 | YES | YES | NO | NO |
| FPG | "Adult" alias | AgeRange(18, 60) | 18 | 60 | YES | YES | NO | NO |
| HbA1c | "Adult" alias | AgeRange(18, 60) | 18 | 60 | YES | YES | NO | NO |
| LDL-C | "Adult" alias | AgeRange(18, 60) | 18 | 60 | YES | YES | NO | NO |
| HDL-C | "Adult" alias | AgeRange(18, 60) | 18 | 60 | YES | YES | NO | NO |
| Creatinine | "Adult" alias | AgeRange(18, 60) | 18 | 60 | YES | YES | NO | NO |
| Potassium | "Adult" alias | AgeRange(18, 60) | 18 | 60 | YES | YES | NO | NO |

**Finding:** All 9 analytes scope 18–60. Patients age 61+ → `unknown` for all. Known V1 limitation, not a bug.
**Age boundary semantics:** `min_age <= patient_age <= max_age` inclusive (`reference_repository.py` line 254). Age 18 and 60 both match. Age 17 and 61 both miss.

### Sex Scope

| Analyte | Rules | M input | F input | "other" input |
|---------|-------|---------|---------|---------------|
| WBC | A only | A rule ✓ | A rule ✓ | A rule ✓ |
| RBC | M, F | M rule ✓ | F rule ✓ | no match → unknown |
| HGB | M, F | M rule ✓ | F rule ✓ | unknown |
| FPG | A only | A rule ✓ | A rule ✓ | A rule ✓ |
| HbA1c | A only | A rule ✓ | A rule ✓ | A rule ✓ |
| LDL-C | A only | A rule ✓ | A rule ✓ | A rule ✓ |
| HDL-C | M, F (RI) | M rule ✓ | F rule ✓ | unknown |
| Creatinine | M, F | M rule ✓ | F rule ✓ | unknown |
| Potassium | A only | A rule ✓ | A rule ✓ | A rule ✓ |

**`normalize_patient_gender()` mapping:** "male"/"nam"/"m" → "M"; "female"/"nữ"/"nu"/"f" → "F"; "other"/"a"/"all"/"any" → "A".
Input "other" → "A". For RBC/HGB/Creatinine (no A rule), "other" → unknown. Safe, not a bug.

---

## PART 11 — UI OBSERVATION CROSS-CHECK

| Observed UI | Selected RI rule | RI result | Critical result | Final status | Correct? |
|-------------|-----------------|-----------|----------------|-------------|---------|
| Potassium 5.6 mmol/L → HIGH | EXPV2-POTASSIUM-001 (3.5–5.0) | high | no trigger (5.6 < 6.5) | `high` | YES |
| Glucose 6.2 mmol/L → HIGH | RRV2-0040 (4.1–6.1) via "Glucose" alias | high | no trigger (6.2 < 27.8) | `high` | YES for RI; alias concern noted |
| LDL-C 5.3 mmol/L → CRITICAL_HIGH | EXPV2-LDLC-001 (None–2.58) | high | 5.3 >= 4.91 → critical_high | `critical_high` | RI correct; **critical threshold CDL-derived — UI correct by coincidence** |
| WBC 11.2 10^9/L → NORMAL | RRV2-0002 (4.72–11.3) | normal | no trigger (11.2 < 30.0) | `normal` | YES |
| HGB 168 g/L → NORMAL | RRV2-0005 M (128–183) | normal | no trigger (168 < 200) | `normal` | YES |
| HbA1c 6.5% → HIGH | EXPV2-HBA1C-001 (4.0–5.7) | high | no trigger (6.5 < 9.0; sentinel low=-1 inactive) | `high` | YES for RI; critical 9.0% has no traceable panic provenance in repo |
| Creatinine 92 umol/L → NORMAL | RRV2-0042 M (59–104) | normal | no trigger (92 < 353.6) | `normal` | YES |

**"Correct by coincidence" flag:**
- **LDL-C CRITICAL_HIGH at 5.3:** RI says HIGH correctly; critical fires at >= 4.91. But 4.91 mmol/L as a panic value is unverified — matches CDL boundary. If no guideline confirms LDL-C critical threshold, this classification is misleading but happens to match current code.

---

## PART 12 — WHAT CAN STAY UNCHANGED

| Subsystem | File | Assessment | Rationale |
|-----------|------|-----------|-----------|
| ReferenceRepository architecture | `src/services/reference_repository.py` | **KEEP_AS_IS** | Alias resolution, unit normalization, CDL filtering, age/sex selection all correct |
| Reference Range Checker architecture | `src/agents/nodes/reference_range_checker_node.py` | **KEEP_AS_IS** | Pipeline and selection architecture correct; no rewrite needed |
| Current inclusive boundary implementation | `reference_range_checker_node.py:_classify()` | **KEEP_FOR_NOW_PENDING_SOURCE_REVIEW** | Current `[lower, upper]` inclusive implementation remains active for V1. If source review confirms an exclusive boundary for any active RI, a minimal boundary-operator patch may be applied without rewriting the checker. |
| alias config | `data/reference/reference_checker_v2_config.json` | **DATA_ONLY** | "Glucose" alias must change; rest correct |
| unit normalization | `reference_repository.py:normalize_unit()` | **KEEP_AS_IS** | Correct and complete for 9 analytes |
| age/sex selection | `reference_repository.py:select_rule()` | **KEEP_AS_IS** | Logic correct |
| Critical Detector | `src/agents/nodes/critical_detector_node.py` | **SMALL_FIX** | Add unit guard; core lookup logic OK |
| critical_thresholds.json | `data/reference/critical_thresholds.json` | **DATA_ONLY** (after medical review) | Disable LDL-C and HbA1c critical entries; add provenance |
| API response | `src/api/routes.py`, `src/models/schemas.py` | **KEEP_AS_IS** | No issues found |
| frontend result rendering | `frontend/` | **KEEP_AS_IS** | Reads status/is_critical/has_critical_values/critical_alerts correctly |
| history persistence | `src/services/history_repository.py` | **KEEP_AS_IS** | No logic concern |

---

## PART 13 — MINIMAL REMEDIATION PLAN

### Fix 1 — Critical Detector Unit Safety

**Priority: P0**
**Files:** `src/agents/nodes/critical_detector_node.py`
**Why:** Critical detector compares raw numeric value against thresholds with no unit canonicalization, no analyte-aware compatibility check, and no fail-closed behavior when units are incompatible. Glucose 27.8 mg/dL (≈1.5 mmol/L) triggers critical_high; HGB 60 g/dL (≈600 g/L) triggers critical_low. The absence of any check means the system cannot distinguish a compatible unit from a dangerously incompatible one.

**Required approach for the fix:**
- Perform **analyte canonicalization** before the threshold lookup (use `resolve_analyte()` from `ReferenceRepository`, not just `.lower()`).
- Perform **analyte-aware unit compatibility check**: determine whether the input unit is compatible with the threshold unit for the specific analyte (e.g., mEq/L and mmol/L are compatible for monovalent K+, but are NOT generalized to arbitrary analytes).
- If the input unit is compatible (same canonical unit or declared equivalent): proceed with numeric comparison.
- If the input unit is incompatible or unknown: **fail closed** — do not trigger a critical alert. Log a unit mismatch warning.
- For current V1, do NOT add broad numeric conversion support unless a specific analyte/unit pair requires it.

**Expected behavior change:** No critical trigger when input unit is incompatible with threshold unit. Correct triggers preserved for correct units.
**Regression risk:** Medium — tests with incompatible units that previously triggered will now correctly get no trigger.
**Tests required:**
- Potassium 6.5 mmol/L → critical_high (threshold unit mmol/L, compatible)
- Potassium 6500 umol/L → NO critical trigger in V1 (CONVERTIBLE unit without implemented numeric conversion → fail closed)
- Glucose 27.8 mmol/L → critical_high
- Glucose 27.8 mg/dL → NO critical trigger in V1 (CONVERTIBLE unit without implemented numeric conversion → fail closed)
- HGB 60 g/L → critical_low
- HGB 60 g/dL → NO critical trigger in V1 (CONVERTIBLE unit without implemented numeric conversion → fail closed)
- Kali 2.4 mmol/L → critical_low (alias + compatible unit)
- Note: Potassium mEq/L compatibility is analyte-specific (monovalent K+ only); do not generalize
**What must NOT change:** -1 sentinel guard behavior (RBC stays inactive at runtime), existing alias entries in JSON.

---

### Fix 2 — Generic Glucose Alias

**Priority: P1**
**Files:** `data/reference/reference_checker_v2_config.json`
**Why:** "Glucose" and "Duong huyet" → "Fasting plasma glucose". Any non-fasting glucose classified against FPG RI (4.1–6.1). Post-prandial 7.8 mmol/L falsely flagged HIGH.
**Expected behavior change:** Input "Glucose"/"Duong huyet" → `unknown`. FPG-specific aliases unaffected.
**Regression risk:** Low — only generic-named glucose affected. Result changes from potentially-wrong HIGH to explicit unknown.
**Tests required:**
- name="Glucose" → unknown
- name="Fasting plasma glucose" → classifies correctly
- name="Fasting Blood Glucose" → classifies correctly
- name="Duong huyet luc doi" → classifies correctly
**What must NOT change:** RRV2-0040 rule, critical threshold for glucose.

---

### Fix 3 — Suspend Unverified Critical Rules (LDL-C, HbA1c, HDL-C)

**Priority: P1 — pending medical source verification**
**Files:** `data/reference/critical_thresholds.json`
**Why:**
- LDL-C high=4.91 matches CDL band boundary (EXPV2-LDLC-005) — strongly suspicious of clinical-band contamination. No traceable panic provenance in the repository. Medical review required to confirm or deny the existence of an LDL-C critical threshold.
- HbA1c high=9.0 has no traceable critical/panic-value provenance in the repository. Classification: NEEDS_SOURCE_VERIFICATION.
- HDL-C low=0.7 / high=2.1 has no traceable provenance. Classification: NEEDS_SOURCE_VERIFICATION.
- **This fix is contingent on medical review.** Do not disable thresholds unilaterally before review.
**Expected behavior change (post review, if confirmed unsupported):** LDL-C, HbA1c, HDL-C no longer trigger critical alerts. RI status (high/low) preserved.
**Regression risk:** Medium — LDL-C CRITICAL_HIGH becomes HIGH if suspended. Impacts UI red banner.
**Tests required (after medical decision):**
- LDL-C 5.3 mmol/L → `high` (not `critical_high`, after suspension)
- HbA1c 9.5% → `high` (not `critical_high`, after suspension)
**Prerequisite:** Medical team provides authoritative source confirming or denying panic thresholds for LDL-C, HbA1c, HDL-C.
**What must NOT change (pending review):** Potassium, Glucose, WBC, HGB, Creatinine critical thresholds.

---

### Fix 4 — Add Provenance to Critical Thresholds

**Priority: P2**
**Files:** `data/reference/critical_thresholds.json`
**Why:** Potassium, Glucose, WBC, HGB, HDL-C, Creatinine have no source_url. Cannot distinguish valid panic values from CDL contamination without provenance.
**Expected behavior change:** None at runtime. Data enrichment only.
**Tests required:** None runtime. Schema validation if added.

---

### Fix 5 — HbA1c Boundary Semantics Review

**Priority: P2**
**Files:** `data/reference/reference_ranges.json` (rule EXPV2-HBA1C-001, upper=5.7)
**Why:** The source (diabetes.org) states "normal: below 5.7%", implying strict `< 5.7`. Runtime uses `<= 5.7` (inclusive). At exactly 5.7%: runtime says NORMAL. This requires **BOUNDARY_SEMANTICS_REVIEW_REQUIRED**.
**Expected action:** Obtain explicit boundary semantics from the authoritative source (ADA/diabetes.org) and decide whether the inclusive or exclusive interpretation is correct.
**Constraint:** Do NOT use numeric threshold manipulation (e.g., 5.69) to simulate `< 5.7` without an explicit precision contract. If `< 5.7` must be enforced, future implementation must either (A) adopt an explicit validated precision policy across all analytes, or (B) introduce a minimal boundary-operator extension. Neither is in scope for this task.
**What must NOT change:** All other HbA1c rules, CDL filtering.

---

## PART 14 — CURRENT_9_STABLE GATE

### Stability Gate Policy

`CURRENT_9_STABLE` may become **YES** only when:
1. Critical detector enforces analyte canonicalization and unit compatibility (with fail-closed behavior for unsupported/unconverted units).
2. Every **ACTIVE** critical threshold is either:
   - **`SOURCE_TRACED_AND_APPROVED`** (verified against authoritative panic/critical-value guidelines with documented source), OR
   - **`EXPLICITLY SUSPENDED / INACTIVE`** pending medical review.
   *(No threshold may remain active merely because it looks plausible or conventional).*
3. Generic analyte aliases (e.g., "Glucose") do not silently imply specialized clinical states (e.g., fasting).
4. Boundary implementations are deterministic and aligned with validated source semantics.

| Gate criterion | Status | Evidence |
|---------------|--------|---------|
| 9/9 canonicalization behavior reviewed | PASS | Parts 1, 3, 6 |
| 9/9 RI active rules reviewed | PASS | Part 4 |
| RI boundary behavior deterministic / documented | PASS (V1) | All 9 reviewed; current inclusive logic KEEP_FOR_NOW_PENDING_SOURCE_REVIEW |
| Age/sex selection verified | PASS | Part 10 |
| Unit taxonomy & behavior verified | PASS | Part 9 (EQUIVALENT_ALIAS, CONVERTIBLE, UNSUPPORTED_OR_INCOMPATIBLE) |
| Critical detector uses analyte-aware unit compatibility | **FAIL** | P0 bug — raw float comparison without unit check (lines 56–87) |
| Critical aliases resolve consistently | PARTIAL | Alias entries match in JSON; canonicalization not integrated — fragile |
| All active critical thresholds source-traced or suspended | **FAIL** | Active thresholds lack traceable provenance (`NEEDS_SOURCE_VERIFICATION`); LDL-C additionally flagged `LIKELY_CLINICAL_BAND_CONTAMINATION` |
| -1 sentinel does not produce false critical alerts at runtime | PASS (runtime only) | Guard `low_val >= 0` prevents trigger; legacy technical debt to be cleaned up |
| Generic Glucose does not silently imply fasting | **FAIL** | "Glucose" alias → FPG in config |
| API/frontend/history regression passes | PASS | No crash path found |

### CURRENT_9_STABLE = **NO**

Gate currently fails on 3 critical criteria:
1. Critical detector lacks analyte-aware unit compatibility and fail-closed mechanism (P0 bug).
2. Active critical thresholds lack traceable panic-value provenance (Potassium, Glucose, WBC, HGB, HDL-C, Creatinine, HbA1c: `NEEDS_SOURCE_VERIFICATION`; LDL-C: `LIKELY_CLINICAL_BAND_CONTAMINATION`).
3. Generic "Glucose" alias silently creates fasting context.

---

## PART 15 — GOLDEN TEST PLAN

### A. RI Tests

| Test ID | Input | Expected | Why |
|---------|-------|---------|-----|
| RI-01 | WBC=4.72, 10^9/L, M, age=35 | normal | Lower boundary inclusive |
| RI-02 | WBC=11.3, 10^9/L, M, age=35 | normal | Upper boundary inclusive |
| RI-03 | WBC=4.71, 10^9/L, M, age=35 | low | Below lower |
| RI-04 | WBC=11.31, 10^9/L, M, age=35 | high | Above upper |
| RI-05 | RBC=4.45, 10^12/L, M, age=35 | normal | M lower boundary |
| RI-06 | RBC=4.44, 10^12/L, M, age=35 | low | Below M lower |
| RI-07 | RBC=4.01, 10^12/L, F, age=35 | normal | F lower boundary |
| RI-08 | HGB=128, g/L, M, age=35 | normal | M lower boundary |
| RI-09 | HGB=127, g/L, M, age=35 | low | Below M lower |
| RI-10 | name="Fasting plasma glucose", 4.1, mmol/L, A, 35 | normal | FPG lower boundary |
| RI-11 | name="Fasting plasma glucose", 6.1, mmol/L, A, 35 | normal | FPG upper boundary |
| RI-12 | name="Fasting plasma glucose", 6.11, mmol/L, A, 35 | high | Above FPG upper |
| RI-13 | HbA1c=5.7, %, A, 35 | normal | Upper boundary — lock current behavior |
| RI-14 | HbA1c=5.71, %, A, 35 | high | Above upper |
| RI-15 | LDL-C=2.58, mmol/L, A, 35 | normal | Upper-only rule, at boundary |
| RI-16 | LDL-C=2.59, mmol/L, A, 35 | high | Above upper |
| RI-17 | LDL-C=0.5, mmol/L, A, 35 | normal | Upper-only: no LOW possible |
| RI-18 | Potassium=3.5, mmol/L, A, 35 | normal | Lower boundary |
| RI-19 | Potassium=5.0, mmol/L, A, 35 | normal | Upper boundary |
| RI-20 | Creatinine=59, umol/L, M, 35 | normal | M lower boundary |

### B. Boundary Tests

| Test ID | Input | Expected | Why |
|---------|-------|---------|-----|
| BD-01 | WBC=4.72 (exact lower) | normal | Confirm inclusive lower |
| BD-02 | WBC=11.3 (exact upper) | normal | Confirm inclusive upper |
| BD-03 | HbA1c=5.7 (exact upper) | normal | Lock current behavior (disputed source semantics) |
| BD-04 | Potassium=2.5 (exact critical low) | critical_low | Critical boundary inclusive |
| BD-05 | Potassium=6.5 (exact critical high) | critical_high | Critical boundary inclusive |

### C. Sex/Age Tests

| Test ID | Input | Expected | Why |
|---------|-------|---------|-----|
| SA-01 | RBC=4.5, F, age=35 | normal (F: 4.01–5.48) | F rule selected |
| SA-02 | RBC=4.44, M, age=35 | low | Below M lower (4.45) |
| SA-03 | RBC=5.0, other, age=35 | unknown | No A rule for RBC |
| SA-04 | WBC=5.0, age=17 | unknown | Below age scope |
| SA-05 | WBC=5.0, age=61 | unknown | Above age scope |
| SA-06 | WBC=5.0, age=18 | normal | Lower age boundary |
| SA-07 | WBC=5.0, age=60 | normal | Upper age boundary |
| SA-08 | HGB=140, other, age=35 | unknown | No A rule for HGB |
| SA-09 | HDL-C=1.5, other, age=35 | unknown | No A rule for HDL-C RI |

### D. Unit Tests

| Test ID | Input | Expected | Why |
|---------|-------|---------|-----|
| UN-01 | WBC=7, x10^9/L | normal | Symbol alias accepted |
| UN-02 | WBC=7, 10^3/uL | normal | Legacy alias |
| UN-03 | WBC=7, G/L | normal | G/L alias |
| UN-04 | WBC=7, mg/dL | unknown | Wrong unit rejected by RI |
| UN-05 | Creatinine=92, µmol/L | normal | Unicode µ normalized |
| UN-06 | Creatinine=92, mg/dL | unknown | Wrong unit → no RI match |
| UN-07 | HGB=150, g/dL | unknown | Wrong unit rejected by RI |

### E. Alias Tests

| Test ID | Input | Expected | Why |
|---------|-------|---------|-----|
| AL-01 | Kali=5.6, mmol/L | high | Kali → Potassium |
| AL-02 | Hemoglobin=168, g/L, M | normal | Hemoglobin → HGB |
| AL-03 | "Fasting Blood Glucose"=6.2, mmol/L | high | Alias → FPG |
| AL-04 | "Glucose"=6.2, mmol/L | high (CURRENT) / unknown (POST-FIX-2) | Generic alias — update after Fix 2 |
| AL-05 | LDL-Cholesterol=3.0, mmol/L | high | Alias → LDL-C |
| AL-06 | HDL-Cholesterol=1.5, mmol/L, F | normal | Alias → HDL-C |
| AL-07 | "Bach cau"=7.0, 10^9/L, M | normal | Vietnamese WBC alias |
| AL-08 | "Hong cau"=5.0, 10^12/L, M | normal | Vietnamese RBC alias |

### F. Critical Tests (after Fix 1 — analyte-aware unit compatibility added)

| Test ID | Input | Expected | Why |
|---------|-------|---------|-----|
| CR-01 | Potassium=2.4, mmol/L | critical_low | Below 2.5 threshold; compatible unit |
| CR-02 | Potassium=2.5, mmol/L | critical_low | Exact threshold (<= 2.5); compatible unit |
| CR-03 | Potassium=6.5, mmol/L | critical_high | Exact threshold (>= 6.5); compatible unit |
| CR-04 | Potassium=6500, umol/L | NO critical after Fix 1 | CONVERTIBLE unit (6500 µmol/L = 6.5 mmol/L) without implemented conversion in V1 → fail closed |
| CR-05 | Glucose=3.0, mmol/L | critical_low | Exact threshold; compatible unit (EQUIVALENT_ALIAS) |
| CR-06 | Glucose=27.8, mmol/L | critical_high | Exact threshold; compatible unit (EQUIVALENT_ALIAS) |
| CR-07 | Glucose=27.8, mg/dL | NO critical after Fix 1 | CONVERTIBLE unit without implemented conversion in V1 → fail closed |
| CR-08 | HGB=60, g/L | critical_low | Exact threshold; compatible unit (EQUIVALENT_ALIAS) |
| CR-09 | HGB=60, g/dL | NO critical after Fix 1 | CONVERTIBLE unit without implemented conversion in V1 → fail closed |
| CR-10 | Kali=2.4, mmol/L | critical_low | Alias + compatible unit |
| CR-11 | Hemoglobin=60, g/L | critical_low | Alias + compatible unit |
| CR-12 | RBC=0.5, 10^12/L | NO critical | -1 sentinel inactive at runtime |
| CR-13 | LDL-C=5.0, mmol/L | high (NOT critical — after Fix 3, pending medical review) | Suspicious CDL-band threshold suspended |
| CR-14 | HbA1c=9.5, % | high (NOT critical — after Fix 3, pending medical review) | Unverified panic threshold suspended |

### G. API End-to-End Smoke Tests

| Test ID | Input | Expected | Why |
|---------|-------|---------|-----|
| E2E-01 | WBC=7, 10^9/L, male, 35 → POST /analyze | status=normal, is_critical=false | Happy path |
| E2E-02 | Potassium=7.0, mmol/L, male, 35 | status=critical_high, is_critical=true, has_critical_values=true | Critical trigger end-to-end |
| E2E-03 | 9 normal analytes, authenticated patient | saved_report_id != null, GET /history returns report | Persistence |
| E2E-04 | 9 normal analytes, guest session | saved_report_id=null | No persistence for guest |
| E2E-05 | name="Unsupported-XYZ" | status=unknown, no crash | Unknown analyte safe fallback |
| E2E-06 | patient_age=65, WBC=7 | status=unknown | Age out of scope |

---

## MANDATORY FINAL ANSWERS

### A. Confirmed Software Bugs

**Bug CD-P0-001 (P0) — No analyte-aware unit compatibility in Critical Detector**
- **File:** `src/agents/nodes/critical_detector_node.py` lines 56–87
- **What:** `ind["value"]` (raw float) is compared directly against threshold floats. No unit canonicalization, no analyte-aware taxonomy check (`EQUIVALENT_ALIAS` vs `CONVERTIBLE` vs `UNSUPPORTED_OR_INCOMPATIBLE`), no fail-closed behavior.
- **Proven effects:** Glucose 27.8 mg/dL → critical_high (CONVERTIBLE unit without conversion; 27.8 mg/dL ≈ 1.54 mmol/L, not critical). HGB 60 g/dL → critical_low (CONVERTIBLE unit; 60 g/dL = 600 g/L). Potassium 6500 umol/L → critical_high (CONVERTIBLE SI unit; 6500 µmol/L = 6.5 mmol/L, raw comparison against 6.5 triggers false critical high).
- **Required fix:** Analyte canonicalization via `resolve_analyte()` + unit taxonomy compatibility check before numeric comparison; fail closed on `CONVERTIBLE` units without converters and on `UNSUPPORTED_OR_INCOMPATIBLE` units.

**Bug CD-P0-002 (P0) — Critical Detector does not canonicalize via ReferenceRepository**
- **File:** `src/agents/nodes/critical_detector_node.py`
- **What:** Uses `name.lower()` only. Any alias not explicitly duplicated in `critical_thresholds.json` silently misses critical detection. Currently mitigated by manual duplicate entries (Kali, Hemoglobin, Fasting Plasma Glucose) but fragile.

**Bug CD-P1-003 (P1) — -1 sentinel is technical debt**
- **File:** `data/reference/critical_thresholds.json`
- **What:** -1 is used as a sentinel to disable a threshold. It is currently runtime-inactive due to the `low_val >= 0` guard in `critical_detector_node.py`. No false alerts are produced today. However, -1 in a numeric threshold field is an implicit contract between data and code with no schema enforcement. A future refactor removing the guard would cause -1 to trigger false critical alerts. **This must be replaced by an explicit schema-level mechanism** (e.g., `null` / `None`, or a `disabled: true` flag) before expanding to 25 analytes.

---

### B. Medical / Data Questions Requiring Verification

| Question | Affected | Priority |
|----------|---------|----------|
| Does any authoritative guideline define a panic/critical threshold for LDL-C? | LDL-C critical entry high=4.91 (suspicious CDL-band match: EXPV2-LDLC-005) | P1 — must confirm before re-enabling or removing |
| Does any authoritative guideline define a panic/critical threshold for HbA1c? | HbA1c critical entry high=9.0 (NEEDS_SOURCE_VERIFICATION — no traceable panic provenance) | P1 — must confirm before re-enabling or removing |
| Does any authoritative guideline define a panic/critical threshold for HDL-C? | HDL-C critical entry low=0.7, high=2.1 (no provenance) | P1 — must confirm |
| Confirm traceable source for Potassium critical thresholds (2.5 / 6.5 mmol/L) | Currently NEEDS_SOURCE_VERIFICATION | P2 |
| Confirm traceable source for Glucose critical thresholds (3.0 / 27.8 mmol/L) | Currently NEEDS_SOURCE_VERIFICATION | P2 |
| Confirm traceable source for WBC critical thresholds (2.5 / 30.0 ×10^9/L) | Currently NEEDS_SOURCE_VERIFICATION | P2 |
| Confirm traceable source for HGB critical thresholds (60.0 / 200.0 g/L) | Currently NEEDS_SOURCE_VERIFICATION | P2 |
| Confirm traceable source for Creatinine critical threshold (353.6 umol/L) | Currently NEEDS_SOURCE_VERIFICATION | P2 |
| HbA1c boundary at 5.7%: is the correct semantic `< 5.7` (strict) or `<= 5.7` (inclusive)? | EXPV2-HBA1C-001 upper=5.7 | P2 — BOUNDARY_SEMANTICS_REVIEW_REQUIRED |
| Confirm Potassium RI source — Vinmec (T2) or primary guideline | EXPV2-POTASSIUM-001 | P2 |

---

### C. Things That Can Remain Unchanged

| Subsystem | File | Rationale |
|-----------|------|-----------|
| ReferenceRepository architecture | `src/services/reference_repository.py` | Alias resolution, CDL filtering, unit normalization, age/sex selection all correct |
| Reference Range Checker architecture | `src/agents/nodes/reference_range_checker_node.py` | Pipeline and demographic selection architecture correct; no rewrite needed |
| Current inclusive boundary implementation | `reference_range_checker_node.py:_classify()` | **KEEP_FOR_NOW_PENDING_SOURCE_REVIEW** — current `[lower, upper]` inclusive logic remains active for V1. If source review confirms an exclusive edge, a minimal boundary patch is applied without rewriting the checker. |
| unit normalization | `reference_repository.py:normalize_unit()` | Correct and complete for 9 analytes |
| age/sex selection | `reference_repository.py:select_rule()` | Logic correct |
| API / response schemas | `routes.py`, `schemas.py` | No issues found |
| Frontend result rendering | `frontend/` | Reads status/is_critical/has_critical_values correctly |
| History persistence | `history_repository.py` | No logic concern |
| RI-only filtering | `allowed_reference_types: ["RI"]` config | CDL correctly inert at runtime |

**REFERENCE_CHECKER_REWRITE_REQUIRED = NO**

---

### D. Corrected Remediation Order

**Phase 1 — Software Correctness (P0)**
1. Add analyte-aware unit compatibility check to `critical_detector_node.py` (Bug CD-P0-001) — fail closed on incompatible/unknown units
2. Integrate `resolve_analyte()` canonicalization into critical detector (Bug CD-P0-002)

**Phase 2 — Medical Critical Registry Verification (P1)**
3. Medical team reviews LDL-C, HbA1c, HDL-C critical thresholds against authoritative panic-value guidelines → decision: keep / suspend / remove each entry
4. Add traceable `source_url` provenance to all entries in `critical_thresholds.json`; verify Potassium, Glucose, WBC, HGB, Creatinine
5. Replace -1 sentinel with explicit schema mechanism (null or disabled flag) — technical debt cleanup

**Phase 3 — Fasting Glucose Alias Decision (P1)**
6. Remove generic "Glucose" and "Duong huyet" aliases from FPG mapping in `reference_checker_v2_config.json` — or route to a separate no-RI-rule analyte

**Phase 4 — RI Boundary Review (P2)**
7. Confirm HbA1c boundary semantics (< 5.7 vs <= 5.7) — BOUNDARY_SEMANTICS_REVIEW_REQUIRED; do not implement without explicit precision policy
8. Confirm boundary semantics (inclusive/exclusive) for all 9 analytes against original source documents
9. Confirm Potassium RI source — upgrade from Vinmec T2 to primary guideline if available

**Phase 5 — Golden Regression Tests**
10. Implement golden test plan (Part 15) covering RI, boundary, age/sex, unit, alias, critical, E2E sections

**Phase 6 — CURRENT_9_STABLE Re-check**
11. Re-evaluate all gate criteria in Part 14
12. Only proceed to 9 → 25 expansion after gate = YES

---

### Final Gate Answers

- **CURRENT_9_AUDIT_FINALIZED = YES**
- **CURRENT_9_STABLE = NO**
- **REFERENCE_CHECKER_REWRITE_REQUIRED = NO**
- **READY_FOR_FIX_1_IMPLEMENTATION = YES**

---

## APPENDIX: FILE EVIDENCE

| File | Role in audit |
|------|--------------|
| [reference_checker_v2_config.json](file:///d:/vin-ai/project/P-056/data/reference/reference_checker_v2_config.json) | approved_analytes, analyte_aliases, age_scope_aliases, allowed_reference_types |
| [reference_ranges.json](file:///d:/vin-ai/project/P-056/data/reference/reference_ranges.json) | All RI and CDL rules; 9 analytes traced |
| [critical_thresholds.json](file:///d:/vin-ai/project/P-056/data/reference/critical_thresholds.json) | 12 entries for 9 analytes (with aliases); all reviewed |
| [units_metric.csv](file:///d:/vin-ai/project/P-056/data/reference/units_metric.csv) | Unit validation baseline; no unit_conflict for 9 analytes |
| [reference_build_report.json](file:///d:/vin-ai/project/P-056/data/reference/reference_build_report.json) | Boundary overlap warnings for HbA1c, Potassium, HDL-C |
| [reference_repository.py](file:///d:/vin-ai/project/P-056/src/services/reference_repository.py) | select_rule(), normalize_unit(), resolve_analyte(), age/sex logic |
| [reference_range_checker_node.py](file:///d:/vin-ai/project/P-056/src/agents/nodes/reference_range_checker_node.py) | RI classification pipeline, _classify() |
| [critical_detector_node.py](file:///d:/vin-ai/project/P-056/src/agents/nodes/critical_detector_node.py) | Critical detection — P0 bug location (lines 56-87) |
| [graph.py](file:///d:/vin-ai/project/P-056/src/agents/graph.py) | Pipeline order: RR checker → critical detector → analyzer → guardrail |
| [schemas.py](file:///d:/vin-ai/project/P-056/src/models/schemas.py) | IndicatorInputSchema, AnalyzeResponse |
| [routes.py](file:///d:/vin-ai/project/P-056/src/api/routes.py) | run_analysis(), state assembly, persistence gate |
