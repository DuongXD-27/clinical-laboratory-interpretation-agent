# VMEC-05 — Current 9 Correctness
# Fix 2 Spec — Generic Glucose Must Not Imply Fasting

**Role:** Senior Backend Engineer + Medical Data Contract Auditor  
**Date:** 2026-08-15  
**Mode:** Read-only — no code, data, config, tests, frontend, DB, RAG, critical thresholds, or reference ranges modified  
**Phase context:** Critical Detector Phase 2B is HUMAN ACCEPTED and frozen. This spec concerns the Reference Range layer only.

---

## Background

ADR-009 records that the ARUP source document labels glucose as `"Glucose"` and the VMEC canonical production critical rule is `"Fasting plasma glucose"`. This is a **source-rule / canonical-data mapping** — it describes how the ARUP analyte label was mapped to the VMEC internal canonical analyte when the critical registry was built. It does **not** mean that a raw user input of `"Glucose"` automatically resolves to `"Fasting plasma glucose"` at runtime.

The Reference Range (RI) layer is a separate concern. The current configuration maps the generic label `"Glucose"` to `"Fasting plasma glucose"` inside `analyte_aliases` in `reference_checker_v2_config.json`. This alias feeds the RI checker via `ReferenceRepository.resolve_analyte()`.

**The RI rules stored under `"Fasting plasma glucose"` carry `fasting_required: YES`.** Applying them to a generic `"Glucose"` input — where fasting status is unknown — is a clinical data contract violation.

---

## Part 1 — Alias trace: every location where Glucose names appear

### 1a. `data/reference/reference_checker_v2_config.json`

```
analyte_aliases:
  "Glucose"               → "Fasting plasma glucose"   ← UNSAFE for RI
  "Đường huyết"          → "Fasting plasma glucose"   ← UNSAFE for RI (generic Vietnamese: "blood sugar")
  "Đường huyết lúc đói"  → "Fasting plasma glucose"   ← SAFE (explicit fasting: "fasting blood sugar")
  "Glucose máu lúc đói"  → "Fasting plasma glucose"   ← SAFE (explicit fasting: "fasting blood glucose")
  "Fasting Blood Glucose" → "Fasting plasma glucose"   ← SAFE (explicit fasting)
  "Fasting plasma glucose"→ "Fasting plasma glucose"   ← SAFE (explicit fasting)

unit_map_aliases:
  "Fasting plasma glucose" → "Fasting Blood Glucose"    (unit lookup in units_metric.csv)
```

### 1b. `data/reference/units_metric.csv`

```
Fasting Blood Glucose,mmol/L
```

No entry for generic `"Glucose"`. Unit lookup is indirect via `unit_map_aliases`.

### 1c. `data/reference/reference_ranges.json` (runtime rules)

All three RI rules carry `analyte_canonical = "Fasting plasma glucose"` and `fasting_required = "YES"`:

| Rule ID | Type | Range | Source |
|---|---|---|---|
| RRV2-0040 | RI (T1, used by config) | 4.1–6.1 mmol/L | Vietnamese Medical Journal |
| RRV2-0060 | CDL (T2, filtered by config) | 5.6–6.9 mmol/L | CDC |
| RRV2-0061 | CDL (T2, filtered by config) | ≥7.0 mmol/L | CDC |

**All glucose rules explicitly require fasting.** No non-fasting/random glucose reference range exists in the repository.

### 1d. `data/reference/critical_thresholds.json`

```json
"Fasting plasma glucose": {
  "low": 55,  "low_operator": "<",
  "high": 450, "high_operator": ">",
  "unit": "mg/dL",
  "vmec_comparison_strategy": "CONVERT_INPUT_TO_SOURCE_UNIT",
  "vmec_conversion_scope": "CRITICAL_LAYER_ONLY"
}
```

The Critical Detector looks up by canonical analyte key (lowercase). The ARUP critical rule is keyed on `"Fasting plasma glucose"` — not on `"Glucose"`. The `source_analyte_label: "Glucose"` is provenance metadata from the ARUP document, not a runtime lookup key.

### 1e. `src/services/reference_repository.py`

`resolve_analyte(analyte: str) → str | None` (line 276):  
Returns the canonical analyte for any alias in `analyte_aliases`. Used by the RI checker, Critical Detector, and OCR gate.

`select_rule(analyte, unit, patient_gender, patient_age)` (line 218):  
Calls `resolve_analyte` first, then filters rules by `analyte_canonical`. No fasting gate exists in this path.

### 1f. `src/agents/nodes/reference_range_checker_node.py`

Line 114: `result = repository.select_rule(analyte=name, unit=unit, ...)` — passes raw `name` directly. No fasting-status check exists in the checker.

### 1g. `src/agents/nodes/critical_detector_node.py`

Line 230: `canonical_analyte = repository.resolve_analyte(name)` — same shared resolver.

**Fix 1 invariant (ACCEPTED, frozen):** If `resolve_analyte(name)` returns `None`, the Critical Detector **must not** fall back to any raw-name lookup. The current code at line 231–237:

```python
canonical_analyte = repository.resolve_analyte(name)
if not canonical_analyte:
    logger.debug(...)
    updated_indicators.append(new_ind)
    continue
```

This invariant is correct and must remain unchanged. **No raw-name critical alias fallback is proposed in Fix 2.**

### 1h. `src/services/ocr_review_gate.py`

Line 48: `canonical = repository.resolve_analyte(name)` — used to determine if an OCR-extracted indicator is "supported".

Currently: `"Glucose"` → `"Fasting plasma glucose"` → in `approved_analytes` → `supported = True`.  
After Fix 2: `"Glucose"` → `None` → not in `approved_analytes` → `supported = False` — OCR draft flagged as unsupported.

### 1i. `src/scripts/extract_explanation_reference_ranges.py`

Line 12: `ALIAS_MAP = {"Glucose": "Fasting plasma glucose", ...}` — build-time script alias for supplemental rule extraction. **This is a separate, build-time-only constant**, not part of the runtime RI pipeline. Its scope is isolated to data-generation scripts and does not need to change for Fix 2.

---

### Summary table — alias trace

| Raw label | Current canonical (RI) | Correct? | Risk |
|---|---|---|---|
| `"Fasting plasma glucose"` | Fasting plasma glucose | ✅ CORRECT | None |
| `"Fasting Blood Glucose"` | Fasting plasma glucose | ✅ CORRECT (explicit fasting) | None |
| `"Đường huyết lúc đói"` | Fasting plasma glucose | ✅ CORRECT (explicit fasting) | None |
| `"Glucose máu lúc đói"` | Fasting plasma glucose | ✅ CORRECT (explicit fasting) | None |
| `"Glucose"` | Fasting plasma glucose | ❌ UNSAFE | Applies fasting RI to unknown-fasting input |
| `"Đường huyết"` | Fasting plasma glucose | ❌ UNSAFE | Applies fasting RI to generic/non-specific input |

---

## Part 2 — Runtime consequence probes (read-only)

### Probe 2a: Input `name = "Glucose"`, `unit = "mmol/L"`, `patient_age = 35`, `patient_gender = "male"`

**Reference Range layer:**

1. `repository.resolve_analyte("Glucose")` → `"Fasting plasma glucose"` (via unsafe alias)
2. `select_rule(canonical="Fasting plasma glucose", unit="mmol/L", ...)` → finds `RRV2-0040` (RI, 4.1–6.1, Adult, mmol/L, `fasting_required=YES`)
3. **No fasting gate is applied.** Value is classified against `[4.1, 6.1]` mmol/L.

**Example:** `Glucose 5.2 mmol/L` → classified as `normal` using fasting plasma glucose RI (4.1–6.1). The system silently infers fasting status from the label `"Glucose"` alone.

**Was fasting context present?** NO. The `IndicatorInputSchema` fields are `name`, `value`, `unit` only. No fasting field exists in any input schema.

---

### Probe 2b: Input `name = "Fasting plasma glucose"`, `unit = "mmol/L"`, `patient_age = 35`, `patient_gender = "male"`

1. `repository.resolve_analyte("Fasting plasma glucose")` → `"Fasting plasma glucose"` (self-alias)
2. `select_rule` → `RRV2-0040` → classified against `[4.1, 6.1]` mmol/L.

**Consequence:** Correct — explicit FPG label → FPG RI rule applied. Fasting is asserted by the test name itself.

---

### Probe 2c: Input `name = "Fasting Blood Glucose"`, `unit = "mmol/L"`, `patient_age = 35`, `patient_gender = "male"`

1. `repository.resolve_analyte("Fasting Blood Glucose")` → `"Fasting plasma glucose"` (explicit fasting alias)
2. `select_rule` → `RRV2-0040` → classified against `[4.1, 6.1]` mmol/L.

**Consequence:** Correct — the alias name contains explicit fasting context.

---

### Probe 2d: Input `name = "Đường huyết"` (generic Vietnamese: "blood sugar"), `unit = "mmol/L"`

1. `repository.resolve_analyte("Đường huyết")` → `"Fasting plasma glucose"` (unsafe alias)
2. `select_rule` → `RRV2-0040` → classified against `[4.1, 6.1]` mmol/L.

**Consequence:** Same unsafe silent fasting inference as Probe 2a. `"Đường huyết"` is a generic term used on lab reports and by patients; it is not specific to fasting measurements.

---

## Part 3 — Fasting context support in current schema

**Inspection of all input schemas:**

`IndicatorInputSchema` (`src/models/schemas.py`, lines 80–99):
```python
name: str
value: float
unit: str
```

`AnalyzeRequest` (`src/models/schemas.py`, lines 102–134):
```python
patient_age: int
patient_gender: Literal["male", "female", "other"]
test_date: date
language: str
indicators: list[IndicatorInputSchema]
```

`OCRIndicatorDraft` (`src/models/ocr_schemas.py`, lines 13–79):
```python
name: str
value: float
unit: str
confidence: float
raw_text: str
needs_review: bool
supported: bool
unsupported_reason: str
```

No schema contains any field named `fasting`, `fasting_status`, `specimen_context`, `collection_condition`, `test_type`, or similar.

`fasting_required` exists in `reference_ranges.json` as a per-rule data field. It is not used as a filter in `select_rule` and is currently informational provenance only.

```
FASTING_CONTEXT_AVAILABLE = NO
```

The system cannot distinguish generic glucose from fasting plasma glucose based on any explicit input signal. The only differentiation available is the test **name string** submitted by the caller.

---

## Part 4 — V1 Policy evaluation

### Policy B — Create separate canonical "Glucose" analyte

**Requires:** A validated, provenance-backed non-fasting/random glucose reference interval.

**Evidence check:** The repository contains no random or non-fasting glucose RI rule. All three glucose rules in `reference_ranges.json` have `fasting_required = "YES"`.

**Verdict: POLICY B CANNOT BE IMPLEMENTED.** Must not be invented.

---

### Policy C — Require explicit fasting context field before resolving Glucose to FPG

**Requires:** A new schema field on `IndicatorInputSchema` or `AnalyzeRequest`.

**Evidence check:** No such field exists. Adding it would require API schema change, frontend change, and all existing caller updates. Not minimal.

**Verdict: POLICY C requires broad product redesign. Out of scope for V1.**

---

### Policy A — Remove generic "Glucose" and "Đường huyết" aliases for RI

**Unsafe aliases to remove from `analyte_aliases`:**

1. `"Glucose"` → `"Fasting plasma glucose"`
2. `"Đường huyết"` → `"Fasting plasma glucose"`

**Safe aliases to retain (explicit fasting context in the label):**

1. `"Fasting plasma glucose"` → `"Fasting plasma glucose"`
2. `"Fasting Blood Glucose"` → `"Fasting plasma glucose"`
3. `"Đường huyết lúc đói"` → `"Fasting plasma glucose"`
4. `"Glucose máu lúc đói"` → `"Fasting plasma glucose"`

**Verdict: POLICY A is the correct minimal V1 option.** Fail closed for generic inputs; preserve explicit fasting aliases.

---

## Part 5 — ADR-009 Glucose mapping clarification and V1 scope

### Clarification: Source-rule vs runtime-input mapping

ADR-009 records:
```
ARUP source analyte label: "Glucose"
VMEC canonical critical rule: "Fasting plasma glucose"
```

This is a **source-rule / canonical-data mapping** — describing how the ARUP source document's analyte label (`"Glucose"`) was mapped to the VMEC canonical analyte name (`"Fasting plasma glucose"`) when the critical registry was constructed. It appears as `source_analyte_label: "Glucose"` in `critical_thresholds.json` — a provenance field.

It does **not** mean that a raw user input of `"Glucose"` must automatically resolve to `"Fasting plasma glucose"` at runtime. The runtime critical registry key is `"Fasting plasma glucose"` (lowercase: `"fasting plasma glucose"`). The Critical Detector reaches this rule by resolving the submitted analyte name to the canonical `"Fasting plasma glucose"` via `repository.resolve_analyte()`.

### V1 critical evaluation path after Fix 2

After removing `"Glucose"` from `analyte_aliases`:

```
Explicit input: "Fasting plasma glucose" (or any retained explicit fasting alias)
  RI checker:         resolve_analyte → "Fasting plasma glucose" → FPG RI rule applied ✓
  Critical Detector:  resolve_analyte → "Fasting plasma glucose" → ARUP FPG critical rule ✓

Generic input: "Glucose"
  RI checker:         resolve_analyte → None → status = "unknown" ✓ (fail closed)
  Critical Detector:  resolve_analyte → None → Blocker 01 → evaluation skipped ✓
```

**Fix 1 invariant is fully preserved:** No raw-name fallback in the Critical Detector. The Blocker 01 logic at lines 231–237 of `critical_detector_node.py` remains unchanged.

**No `_CRITICAL_LAYER_ANALYTE_ALIASES` constant is added. No raw-name critical fallback is proposed.**

### V1 scope statement

VMEC-05 V1 does **not** guarantee Critical Detector evaluation for a raw generic `"Glucose"` label when fasting context is unknown. This is intentional fail-closed behavior.

It does **not** remove the ARUP Glucose critical rule from the `"Fasting plasma glucose"` canonical analyte. The rule remains active and functional for all inputs that resolve to `"Fasting plasma glucose"` (i.e., explicit fasting aliases).

The V1 demonstration of Glucose critical detection must use an explicit FPG-supported label/input:
- `"Fasting plasma glucose"`
- `"Fasting Blood Glucose"`
- `"Đường huyết lúc đói"`
- `"Glucose máu lúc đói"`

**Future work** may design a separate critical-evaluation state that can operate independently of RI classification without overwriting `status=unknown`. That future architecture is **out of scope for Fix 2**.

---

## Part 6 — OCR / API / manual entry impact

### Scenario: `Glucose 5.2 mmol/L` received (generic label, Policy A applied)

**Current behavior (before fix):**
- OCR: `resolve_analyte("Glucose")` → `"Fasting plasma glucose"` → in `approved_analytes` → `supported = True`
- RI checker: classified against FPG RI 4.1–6.1 mmol/L → `normal` (UNSAFE)
- Critical Detector: `resolve_analyte("Glucose")` → `"Fasting plasma glucose"` → Approved glucose conversion runs → `5.2 × 18.01559 = 93.68 mg/dL` → neither `< 55` nor `> 450` → not critical

**After Policy A fix:**
- OCR: `resolve_analyte("Glucose")` → `None` → `canonical not in approved_analytes` → `supported = False`
  - Draft marked as **unsupported** with reason "Chỉ số này hiện tại chưa được hỗ trợ."
- RI checker: `resolve_analyte("Glucose")` → `None` → `result.reason = "analyte_not_supported"` → `status = "unknown"`
  - No FPG RI range applied. `reference_low = None`, `reference_high = None`.
- Critical Detector: `resolve_analyte("Glucose")` → `None` → Blocker 01 fires → evaluation **skipped**
  - Additionally, if the pipeline runs in sequence, Blocker 02 also fires: upstream `status = "unknown"` → no escalation.
  - Final status: `unknown`, `is_critical = False`

**State:** Indicator preserved in output with `status = "unknown"`, `is_abnormal = False`, `is_critical = False`. Original name, value, unit unchanged.

**Frontend display:** Indicator shown with `status = "unknown"`, no reference range. May appear in `out_of_scope_indicators` list.

**History persistence:** Persisted with `status = "unknown"`. No RI classification recorded.

**This limitation is accepted for V1.**

---

### Scenario: `Fasting plasma glucose 5.2 mmol/L` or `Đường huyết lúc đói 5.2 mmol/L`

**After Policy A fix:** No behavioral change. Explicit fasting aliases remain in `analyte_aliases`. Both RI and Critical evaluations proceed normally.

---

## Part 7 — Test impact analysis

### Tests requiring update

| File | Test | Lines | Classification | Required action |
|---|---|---|---|---|
| `test_services/test_reference_repository.py` | `test_r05_alias_resolution` | 159–165 | Parametrized — includes `("Glucose", "Fasting plasma glucose")` | **UPDATE**: remove the `"Glucose"` parameter case |
| `test_services/test_reference_repository.py` | `test_t01_ri_preferred_over_cdl` | 467–477 | Sends `analyte="Glucose"` → expects `matched=True` | **REPLACE**: change input to `analyte="Fasting plasma glucose"` — the RI preference logic is still valid with the explicit name |
| `test_services/test_reference_repository.py` | `conftest.py / make_config` fixture | 19–25 | Includes `"Glucose": "Fasting plasma glucose"` in test alias map | **UPDATE**: remove `"Glucose"` entry from the test fixture alias map |
| `test_data/test_explanation_reference_sync.py` | `test_sync_02_alias_resolution` | 76 | Asserts `canonical_analyte("Glucose") == "Fasting plasma glucose"` | **UPDATE**: invert to assert `canonical_analyte("Glucose") is None`; or annotate as build-time only |
| `test_data/test_explanation_reference_sync.py` | `test_sync_02_alias_map_completeness` | 87 | Asserts `ALIAS_MAP["Glucose"] == "Fasting plasma glucose"` | **KEEP with annotation**: `ALIAS_MAP` in `extract_explanation_reference_ranges.py` is a build-time script constant, separate from the runtime RI config. Annotate the test to clarify this scope distinction. |

---

### New golden tests (design contract — for implementation after Human approval)

| Test ID | Scenario | Expected result | Notes |
|---|---|---|---|
| GFA-01 | `"Fasting plasma glucose"` → `repository.resolve_analyte` | Returns `"Fasting plasma glucose"` | Must continue to work |
| GFA-02 | `"Fasting Blood Glucose"` → `repository.resolve_analyte` | Returns `"Fasting plasma glucose"` | Must continue to work |
| GFA-03 | `"Đường huyết lúc đói"` → `repository.resolve_analyte` | Returns `"Fasting plasma glucose"` | Must continue to work |
| GFA-04 | `"Glucose"` → `repository.resolve_analyte` | Returns `None` | **New invariant** after Policy A |
| GFA-05 | `"Đường huyết"` → `repository.resolve_analyte` | Returns `None` | **New invariant** after Policy A |
| GFA-06 | `"Glucose", 5.2, "mmol/L"` → RI checker | `status = "unknown"`, `reference_low = None`, `reference_high = None`, `is_abnormal = False` | No FPG RI applied |
| GFA-07 | `"Glucose", 3.0, "mmol/L"` → full pipeline (RI + Critical) | RI: `status = "unknown"` → Critical: Blocker 01+02 → no critical alert, `status = "unknown"` | Upstream unknown invariant preserved end-to-end |
| GFA-08 | `"Fasting plasma glucose", 3.0, "mmol/L"` → full pipeline | RI: `status = "low"` (below 4.1) → Critical: `converted = 3.0 × 18.01559 = 54.05 mg/dL < 55` → `status = "critical_low"` | ARUP FPG critical rule functional via explicit FPG label |
| GFA-09 | `"Đường huyết lúc đói", 3.0, "mmol/L"` → full pipeline | Same as GFA-08 via retained explicit fasting alias | Explicit fasting aliases still reach ARUP critical rule |
| GFA-10 | No raw-name critical fallback test: `"Glucose"` → Critical Detector (standalone, no upstream indicators) | Blocker 01 fires (resolve_analyte returns None) → `is_critical = False`, no alert | Fix 1 invariant preserved; no `_CRITICAL_LAYER_ANALYTE_ALIASES` |
| GFA-11 | All other current-9 analytes | Unchanged behavior | `Potassium`, `WBC`, `HGB`, `HbA1c`, `LDL-C`, `HDL-C`, `Creatinine`, `RBC` unaffected |

> **Note on GFA-08 value:** `3.0 mmol/L × 18.01559 = 54.04677 mg/dL`. This is `< 55`, so the ARUP critical rule fires. The test implementation must call `glucose_mmol_l_to_mg_dl(3.0)` and verify the comparison, not hardcode the converted value.

---

## Part 8 — Minimal patch plan

### File 1: `data/reference/reference_checker_v2_config.json` — PRIMARY CHANGE

**Exact diff:**

```diff
   "analyte_aliases": {
     "WBC": "WBC",
     "Bạch cầu": "WBC",
     "Bạch cầu (WBC)": "WBC",
     "Số lượng bạch cầu": "WBC",
     "RBC": "RBC",
     "Hồng cầu": "RBC",
     "Hồng cầu (RBC)": "RBC",
     "Số lượng hồng cầu": "RBC",
     "HGB": "HGB",
     "Hemoglobin": "HGB",
     "Hemoglobin (HGB)": "HGB",
     "Huyết sắc tố": "HGB",
-    "Glucose": "Fasting plasma glucose",
-    "Đường huyết": "Fasting plasma glucose",
     "Đường huyết lúc đói": "Fasting plasma glucose",
     "Đường huyết lúc đói": "Fasting plasma glucose",
     "Glucose máu lúc đói": "Fasting plasma glucose",
     "Fasting Blood Glucose": "Fasting plasma glucose",
     "Fasting plasma glucose": "Fasting plasma glucose",
     ...
```

**Why:** Removes the two labels that carry no explicit fasting context. The remaining glucose aliases all contain an explicit fasting reference.

**Regression risk:** Medium — behavioral change for callers using `"Glucose"` or `"Đường huyết"`. Callers must use an explicit fasting label. OCR-extracted indicators labeled `"Glucose"` become unsupported.

**Critical Detector impact:** `resolve_analyte("Glucose")` → `None` → Blocker 01 → evaluation skipped. **This is correct and intentional** per the V1 scope statement. Fix 1 invariant is preserved.

---

### File 2: `src/agents/nodes/critical_detector_node.py` — NO CHANGE

No changes to the Critical Detector. The `_CRITICAL_LAYER_ANALYTE_ALIASES` constant previously proposed in an earlier draft **is removed** from this spec. Fix 1 Blocker 01 invariant (no raw-name fallback) is preserved without modification.

---

### File 3 (tests): `tests/test_services/test_reference_repository.py`

Update three locations per Part 7:
1. Remove `("Glucose", "Fasting plasma glucose")` from `test_r05_alias_resolution` parametrize.
2. Replace `analyte="Glucose"` with `analyte="Fasting plasma glucose"` in `test_t01_ri_preferred_over_cdl`.
3. Remove `"Glucose": "Fasting plasma glucose"` from the `make_config` test fixture.

---

### File 4 (tests): `tests/test_data/test_explanation_reference_sync.py`

Update one assertion per Part 7:
1. `test_sync_02_alias_resolution` line 76: replace or invert the `Glucose` assertion.
2. `test_sync_02_alias_map_completeness` line 87: annotate as build-time script scope, no code change needed.

---

### File 5 (tests): `tests/test_agents/test_critical_detector_node.py`

Add GFA-07 and GFA-10:
- GFA-07: full pipeline with generic `"Glucose"` → `status = "unknown"` preserved end-to-end.
- GFA-10: standalone Critical Detector with `"Glucose"` → Blocker 01 → no critical evaluation (Fix 1 preserved).

---

### File 6 (tests): `tests/test_integration/test_v2_reference_pipeline.py`

Add GFA-08 and GFA-09:
- GFA-08: `"Fasting plasma glucose"` at `3.0 mmol/L` → `critical_low` confirmed.
- GFA-09: `"Đường huyết lúc đói"` at `3.0 mmol/L` → same result via retained alias.

---

### Files NOT changed

| File | Reason |
|---|---|
| `src/agents/nodes/critical_detector_node.py` | No change; Fix 1 invariant preserved |
| `data/reference/critical_thresholds.json` | Not required — `"Fasting plasma glucose"` key unchanged |
| `data/reference/reference_ranges.json` | Reference range numbers unchanged |
| `data/reference/units_metric.csv` | No unit changes |
| `src/services/reference_repository.py` | No changes to `resolve_analyte` or `select_rule` |
| `src/agents/nodes/reference_range_checker_node.py` | No changes |
| `src/scripts/extract_explanation_reference_ranges.py` | Build-time `ALIAS_MAP` is separate from runtime config; may remain |
| All frontend, DB, history, RAG files | Out of scope |

---

## Mandatory final answers

```text
RECOMMENDED_V1_POLICY = A

GENERIC_GLUCOSE_RI_FAILS_CLOSED = YES
  "Glucose" removed from analyte_aliases.
  resolve_analyte("Glucose") → None → status = "unknown" → no FPG RI applied.

GENERIC_DUONG_HUYET_RI_FAILS_CLOSED = YES
  "Đường huyết" removed from analyte_aliases.
  resolve_analyte("Đường huyết") → None → status = "unknown" → no FPG RI applied.

RAW_NAME_CRITICAL_FALLBACK_PROPOSED = NO
  _CRITICAL_LAYER_ANALYTE_ALIASES is NOT proposed.
  Critical Detector canonicalization path is unchanged.

FIX1_NO_RAW_NAME_FALLBACK_PRESERVED = YES
  Blocker 01 logic at critical_detector_node.py lines 231–237 is unchanged.
  resolve_analyte returning None → critical evaluation skipped. No fallback.

UPSTREAM_UNKNOWN_INVARIANT_PRESERVED = YES
  Blocker 02 logic is unchanged.
  If RI returns status=unknown, Critical Detector will not escalate.

ARUP_FPG_CANONICAL_RULE_REMAINS_ACTIVE = YES
  critical_thresholds.json "Fasting plasma glucose" entry is unchanged.
  The ARUP critical rule (< 55 / > 450 mg/dL) is active and evaluated
  for all inputs that resolve to "Fasting plasma glucose".

EXPLICIT_FPG_CRITICAL_PATH_REMAINS_FUNCTIONAL = YES
  Inputs: "Fasting plasma glucose", "Fasting Blood Glucose",
  "Đường huyết lúc đói", "Glucose máu lúc đói"
  → resolve_analyte → "Fasting plasma glucose"
  → RI evaluated → Critical evaluated via approved Decimal conversion.

GENERIC_GLUCOSE_CRITICAL_E2E_SUPPORTED_IN_V1 = NO
  Generic "Glucose" → RI unknown → Blocker 02 → no critical evaluation.
  This is intentional fail-closed behavior.
  Future architecture may address this independently.

NUMERIC_5_2_CONVERSION_CORRECTED = YES
  5.2 mmol/L × 18.01559 = 93.681068 mg/dL
  This is neither < 55 nor > 450.
  The value does not trigger the ARUP critical rule.
  All glucose conversion examples in this document use mg/dL = mmol/L × 18.01559.

CRITICAL_THRESHOLD_CHANGE_REQUIRED = NO

REFERENCE_RANGE_NUMBER_CHANGE_REQUIRED = NO

CODE_CHANGED = NO
DATA_CHANGED = NO

READY_FOR_HUMAN_FIX2_POLICY_APPROVAL = YES
```
