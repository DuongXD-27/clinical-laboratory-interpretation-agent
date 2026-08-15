# VMEC-05 — Phase 2B Patch B
# Deterministic Glucose Unit Conversion Contract

**Role:** Senior Backend/Data Engineer + Numerical Safety Auditor  
**Date:** 2026-08-14  
**Mode:** Read-only design / verification — no production code, data, config, tests, or frontend changed  
**Governance authority:** ADR-009 (ACCEPTED) — ARUP `CORP-APPEND-0104A` Rev.46 April 2026  

---

## Frozen governance inputs

```
ARUP source rule (Glucose, >30 days to adult):
  LOW:  < 55 mg/dL   (strict operator)
  HIGH: > 450 mg/dL  (strict operator)

VMEC canonical mapping (Critical layer only):
  ARUP "Glucose" → VMEC "Fasting plasma glucose"

Scope: CRITICAL_LAYER_ONLY
Does not legitimize generic Glucose→FPG in Reference Range checker.
```

---

## Part 1 — Current numeric data-flow audit

### Entry point: API layer

File: `src/api/routes.py`, lines 49–52.

```python
"raw_indicators": [
    indicator.model_dump()
    for indicator in request.indicators
],
```

`IndicatorInputSchema` (file: `src/models/schemas.py`, line 89):

```python
value: float = Field(..., allow_inf_nan=False, ...)
```

**Type at API boundary:** `float` (Python `float`, IEEE 754 double precision, 64-bit).

Pydantic coerces the JSON number into Python `float` before `.model_dump()` is called.
The dict value is therefore a Python `float` from this point onward in the graph state.

---

### Node 1: `reference_range_checker_node`

File: `src/agents/nodes/reference_range_checker_node.py`.

```python
numeric_value = _parse_value(val)      # line 109
# def _parse_value(value) -> Decimal | None:
#     return Decimal(str(value))       # line 35
```

**Type:** The RI checker converts the input `float` to `Decimal` via `Decimal(str(value))` immediately.
All RI boundary arithmetic uses `Decimal` throughout — `_parse_rule_bound`, `_classify`.

However, the raw `val` (Python `float`) is stored **as-is** back into `assessment["value"]` (line 140 and surrounding block). The IndicatorAssessment dict's `value` key retains the original `float`.

---

### AgentState transit

`IndicatorAssessment.value: float` (file: `src/agents/state.py`, line 24).

The IndicatorAssessment TypedDict declares `value: float`. The dict written by the reference checker preserves the original `float` value — NOT the `Decimal` it used for internal classification.

---

### Node 2: `detect_critical_values_node`

File: `src/agents/nodes/critical_detector_node.py`.

```python
val = new_ind.get("value")             # line 179 — Python float
numeric_val = _parse_numeric(val)      # line 183

# def _parse_numeric(val: Any) -> float | None:
#     return float(val)               # line 63
```

**Type:** `float`. The critical detector currently calls `float(val)` to parse the indicator value. All existing critical comparisons operate on Python `float`.

Threshold values loaded from `critical_thresholds.json` are also parsed via `_parse_numeric` → `float(threshold_raw)` (line 106).

---

### Summary table: numeric type at each step

| Step | Value from | Type in code | Notes |
|---|---|---|---|
| HTTP JSON body | Client JSON | JSON number | Structured by Pydantic |
| `IndicatorInputSchema.value` | Pydantic field | `float` | `allow_inf_nan=False` enforced |
| `raw_indicators[*]["value"]` | `.model_dump()` | `float` | Plain Python dict |
| RI checker `_parse_value(val)` | `Decimal(str(float))` | `Decimal` | Used internally for RI classify |
| `assessment["value"]` stored | original `float` | `float` | Decimal NOT written back to state |
| Critical detector `_parse_numeric(val)` | `float(val)` | `float` | Existing code: explicit cast to float |
| Threshold from JSON | `float(threshold_raw)` | `float` | Existing code: JSON `number` → Python `float` |
| `_compare_critical(value, threshold, op)` | both `float` | `float` vs `float` | Existing code: IEEE 754 comparison |

**Prior to Patch B, all critical comparisons are Python `float` vs `float`.**

---

### Existing conversion helpers

The only mg/dL → mmol/L conversion in the repository is:

File: `src/scripts/extract_explanation_reference_ranges.py`, lines 83–89.

```python
_HDL_CONVERSION_FACTOR = Decimal("0.0259")

def convert_mgdl_to_mmol(value_mgdl: float) -> float:
    """Convert mg/dL to mmol/L using factor 0.0259, rounded ROUND_HALF_UP to 2 decimal places."""
    result = _HDL_CONVERSION_FACTOR * Decimal(str(value_mgdl))
    return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
```

This function:
- Uses factor `0.0259`, which is the HDL-C / cholesterol conversion factor, NOT the glucose conversion factor.
- Rounds to 2 decimal places — hardcoded.
- Lives in a **build-time script** (`src/scripts/`), not a runtime utility.
- Is NOT importable or reusable by runtime nodes without moving or extracting it.

**This function must NOT be reused for glucose.** Glucose requires a different factor (see Part 2).

There is no runtime conversion utility for Glucose mg/dL ↔ mmol/L anywhere in the codebase.

---

### Interaction: upstream `status=unknown` and conversion

The Critical Detector's Blocker 02 (Fix 1):

```python
if has_upstream_indicators and current_status == "unknown":
    # skip critical evaluation
    updated_indicators.append(new_ind)
    continue
```

If a glucose measurement in mg/dL enters the Reference Range checker, the RI checker calls `repository.select_rule(unit="mg/dL")`. The repository normalizes `mg/dL` and looks for a matching RI rule. The RI rules for "Fasting plasma glucose" are stored in `mmol/L` (verified: `units_metric.csv` row: `Fasting Blood Glucose,mmol/L`). The unit does not match, so `select_rule` returns `matched=False`, `reason="unit_not_supported"`, and the checker produces `status="unknown"`.

**Consequence:** In the end-to-end graph, a glucose measurement submitted as mg/dL → RI returns `unknown` → Blocker 02 fires → Critical Detector does NOT evaluate it → critical evaluation does not run.

Patch B must distinguish:
1. **Standalone Critical Detector unit behavior:** same normalized units (e.g. `mg/dL` input vs `mg/dL` threshold) can be evaluated directly; approved conversions execute deterministically.
2. **End-to-end graph behavior:** upstream `status=unknown` remains fail-closed.

Patch B will NOT silently expand Reference Range unit support.

---

## Part 2 — Conversion authority verification

### Source authority

**Primary technical authority:**  
NIST Chemistry WebBook — D-Glucose (α-D-Glucose)  
URL: https://webbook.nist.gov/cgi/cbook.cgi?ID=C492626  
CAS Registry Number: 492-62-6  
Formula: C₆H₁₂O₆  
**Molecular weight (molar mass): 180.1559 g/mol**

*Note on Authority Scope:* NIST provides the molecular weight of glucose. NIST does not publish the VMEC clinical conversion rule itself. The mg/dL ↔ mmol/L conversion relationship is derived deterministically by dimensional analysis from this molecular weight.

---

### Conversion derivation

Blood glucose concentration unit conversion is a direct unit-dimensional derivation:

```
mg/dL = mg per deciliter = mg per 0.1 L

1 mmol/L = 1 millimole per liter
         = MW_glucose mg per liter / 1000
         = MW_glucose mg per 10 dL

Therefore:
  value_mg_dl = value_mmol_l × (MW_glucose / 10)
  value_mg_dl = value_mmol_l × (180.1559 / 10)
  value_mg_dl = value_mmol_l × 18.01559

Inversely:
  value_mmol_l = value_mg_dl ÷ 18.01559
```

---

### Exact factor and precision

```
NIST Molecular Weight:
  180.1559 g/mol

Exact conversion factor (mmol/L → mg/dL):
  18.01559  (i.e. 180.1559 / 10)

Decimal representations:
  Decimal("180.1559") / Decimal("10") = Decimal("18.01559")
```

Common clinical literature approximations (e.g. `÷ 18`, `× 0.0555`, `÷ 18.02`) introduce unnecessary rounding. VMEC-05 Patch B establishes the full-precision NIST-derived constant `180.1559` via Decimal arithmetic.

---

## Part 3 — Strategy comparison

### Strategy A — Convert ARUP threshold into VMEC unit (mmol/L)

Concept:
```
55 mg/dL → X mmol/L   (pre-convert at registry build time or load time)
450 mg/dL → Y mmol/L  (pre-convert)

Then compare:  input_mmol_L < X  or  input_mmol_L > Y
```

**Risk analysis:**

Exact mathematical source-boundary equivalents:
- `55 / 18.01559 ≈ 3.052911395075043... mmol/L`
- `450 / 18.01559 ≈ 24.9783659597049... mmol/L`

If these values are rounded into fixed decimals (such as `3.05` or `24.98`), quantization errors alter the exact boundary semantics. Furthermore, the operational registry loses the literal integers `55` and `450` written in the ARUP document.

**Verdict on Strategy A:** Does not preserve ARUP source literals in the operational registry.

---

### Strategy B — Preserve ARUP threshold literal, convert input into source unit

Concept:
```
critical_thresholds.json:
  "low":           55,    unit: "mg/dL",   low_operator:  "<"
  "high":          450,   unit: "mg/dL",   high_operator: ">"

Input: 3.050 mmol/L
  → convert to mg/dL: 3.050 × 18.01559 = 54.94754950 mg/dL
  → compare: Decimal("54.94754950") < Decimal("55") → True → critical_low

Input: 3.053 mmol/L
  → convert to mg/dL: 3.053 × 18.01559 = 55.00159627 mg/dL
  → compare: Decimal("55.00159627") < Decimal("55") → False → NOT critical low
```

**Mechanics:**
- ARUP source literals `55` and `450` are stored unchanged as integers/Decimals with unit `mg/dL`.
- When an input in `mmol/L` is received, the Critical Detector converts the input value to `mg/dL` using Decimal arithmetic without quantization.
- The comparison is executed in `mg/dL` directly against `Decimal("55")` and `Decimal("450")`.
- The Patch A unit-safety invariant is strictly preserved: numeric comparison is executed in a single unit (`mg/dL`).

---

### Boundary preservation verification

**Low side rule: `< 55 mg/dL` (strict, ARUP)**  
*Exact mathematical boundary equivalent:* `55 / 18.01559 ≈ 3.052911395075043 mmol/L`

| Input (unit) | Exact converted value (mg/dL) | Comparison against Decimal("55") | Critical? | Expected? |
|---|---|---|---|---|
| `54.99 mg/dL` (direct) | `54.99` | `54.99 < 55` | **YES** | YES (below 55) |
| `55.00 mg/dL` (direct) | `55.00` | `55.00 < 55` | **NO** | NO (exact boundary — strict `<`) ✓ |
| `55.01 mg/dL` (direct) | `55.01` | `55.01 < 55` | **NO** | NO (above 55) |
| `3.050 mmol/L` | `54.94754950` | `54.94754950 < 55` | **YES** | YES (below boundary) ✓ |
| `3.053 mmol/L` | `55.00159627` | `55.00159627 < 55` | **NO** | NO (above boundary) ✓ |
| `3.054 mmol/L` | `55.01961186` | `55.01961186 < 55` | **NO** | NO (above boundary) ✓ |
| `3.055 mmol/L` | `55.03762745` | `55.03762745 < 55` | **NO** | NO (above boundary) ✓ |

**High side rule: `> 450 mg/dL` (strict, ARUP)**  
*Exact mathematical boundary equivalent:* `450 / 18.01559 ≈ 24.9783659597049 mmol/L`

| Input (unit) | Exact converted value (mg/dL) | Comparison against Decimal("450") | Critical? | Expected? |
|---|---|---|---|---|
| `449.99 mg/dL` (direct) | `449.99` | `449.99 > 450` | **NO** | NO (below 450) |
| `450.00 mg/dL` (direct) | `450.00` | `450.00 > 450` | **NO** | NO (exact boundary — strict `>`) ✓ |
| `450.01 mg/dL` (direct) | `450.01` | `450.01 > 450` | **YES** | YES (above 450) ✓ |
| `24.97 mmol/L` | `449.84928230` | `449.84928230 > 450` | **NO** | NO (below boundary) ✓ |
| `24.99 mmol/L` | `450.20959410` | `450.20959410 > 450` | **YES** | YES (above boundary) ✓ |

**Verdict:** Strategy B preserves ARUP source literals exactly, ensures mathematical boundary correctness, and prevents threshold corruption.

---

## Part 4 — Boundary preservation (strict operator invariants)

**Key invariant from ADR-009:**
- `exact 55 mg/dL → NOT critical low`
- `exact 450 mg/dL → NOT critical high`
- Strict operators must NOT be encoded through threshold shifts (e.g. NO `54.99` or `450.01`).

Under Strategy B with Decimal comparison:

```python
# Low comparison
converted_mg_dl < Decimal("55")
# Decimal("55.00") < Decimal("55") -> False (NOT critical low) ✓

# High comparison
converted_mg_dl > Decimal("450")
# Decimal("450.00") > Decimal("450") -> False (NOT critical high) ✓
```

Strict operators `<` and `>` operate on exact Decimal values without threshold manipulation.

---

## Part 5 — Decimal comparison policy

### Software safety rationale

The conversion path should avoid unnecessary binary-float round trips because exact deterministic boundary behavior is the primary software safety requirement.

### Numeric pipeline specification for approved conversion path

1. **Input reception:** Read `value` from indicator state (e.g. `val = ind["value"]`).
2. **Decimal parsing:** Parse input into Decimal:
   ```python
   input_dec = Decimal(str(val))
   ```
3. **Deterministic conversion (no intermediate float casting, no pre-comparison rounding):**
   ```python
   GLUCOSE_MW_NIST = Decimal("180.1559")
   value_mg_dl = input_dec * GLUCOSE_MW_NIST / Decimal("10")
   ```
4. **Source threshold representation:**
   Parse source threshold literals as exact Decimals:
   ```python
   thresh_low = Decimal(str(thresholds["low"]))    # Decimal("55")
   thresh_high = Decimal(str(thresholds["high"]))  # Decimal("450")
   ```
5. **Direct Decimal comparison:**
   Execute Patch A operator logic directly on Decimal operands:
   ```python
   if low_operator == "<":
       is_crit_low = value_mg_dl < thresh_low
   if high_operator == ">":
       is_crit_high = value_mg_dl > thresh_high
   ```
6. **State & presentation preservation:**
   The original numeric value and unit in `AgentState` / `IndicatorAssessment` / `CriticalAlert` remain unmodified (the patient's original `mmol/L` measurement is preserved for display).

*Scope note:* This Decimal comparison policy applies to the approved unit conversion path in the Critical Detector. It does not redesign the API schemas or global AgentState.

---

## Part 6 — Direction of conversion

### V1 Policy

**Patch B supports: `mmol/L` input → `mg/dL` conversion for Critical comparison.**

- **Critical layer scope:** Converts VMEC canonical unit (`mmol/L`) to ARUP source unit (`mg/dL`) solely for critical evaluation.
- **Reference Range layer scope:** Remains `mmol/L` only. Does not change Reference Range rules.
- **Unsupported units:** Fail closed.

---

## Part 7 — Shared conversion location

### Dedicated utility specification

**Location:** `src/services/measurement_conversion.py` (new module)

```python
from decimal import Decimal

# Molecular weight from NIST Chemistry WebBook (CAS 492-62-6, C6H12O6)
GLUCOSE_MW_NIST = Decimal("180.1559")

def glucose_mmol_l_to_mg_dl(value_mmol_l: float | str | Decimal) -> Decimal:
    """Convert glucose concentration from mmol/L to mg/dL via NIST molecular weight.

    Calculation: value_mmol_l * 180.1559 / 10

    Returns:
        Decimal: Exact converted value in mg/dL without pre-comparison quantization.
    """
    return Decimal(str(value_mmol_l)) * GLUCOSE_MW_NIST / Decimal("10")
```

---

## Part 8 — Target critical record shape for Patch C

```json
"Fasting plasma glucose": {
  "low":           55,
  "low_operator":  "<",
  "high":          450,
  "high_operator": ">",
  "unit":          "mg/dL",

  "source_id":              "SRC-CRIT-ARUP-REV46",
  "source_title":           "CRITICAL VALUES LIST",
  "source_document_id":     "CORP-APPEND-0104A",
  "source_revision":        "46",
  "source_date":            "2026-04",
  "source_url":             "https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf",
  "source_page":            1,
  "source_literal":         "< 55 or > 450 mg/dL",
  "source_analyte_label":   "Glucose",
  "population_context":     ">30 days to adult",
  "qualifier":              null,

  "vmec_canonical_unit":         "mmol/L",
  "vmec_comparison_strategy":    "CONVERT_INPUT_TO_SOURCE_UNIT",
  "vmec_conversion_function":    "glucose_mmol_l_to_mg_dl",
  "vmec_conversion_authority":   "NIST-CAS-492-62-6-MW-180.1559",
  "vmec_conversion_scope":       "CRITICAL_LAYER_ONLY"
}
```

---

## Part 9 — Test contract

### Test group 1: Source-unit direct path (standalone detector, mg/dL input vs mg/dL threshold)

| Test ID | Input (mg/dL) | Threshold (mg/dL) | Expected status | Notes |
|---|---|---|---|---|
| GC-SRC-01 | `54.99` | `< 55` | `critical_low` | Just below 55 |
| GC-SRC-02 | `55.00` | `< 55` | `normal` / not critical | Exact boundary (`<` strict) |
| GC-SRC-03 | `55.01` | `< 55` | `normal` / not critical | Just above 55 |
| GC-SRC-04 | `449.99` | `> 450` | `normal` / not critical | Just below 450 |
| GC-SRC-05 | `450.00` | `> 450` | `normal` / not critical | Exact boundary (`>` strict) |
| GC-SRC-06 | `450.01` | `> 450` | `critical_high` | Just above 450 |

---

### Test group 2: mmol/L conversion path (canonical VMEC unit vs ARUP literal thresholds)

Conversion: `value_mg_dl = Decimal(str(val)) * Decimal("180.1559") / Decimal("10")`  
Source thresholds: `Decimal("55")`, `Decimal("450")`

| Test ID | Input (mmol/L) | Exact converted value (mg/dL) | Expected status | Notes |
|---|---|---|---|---|
| GC-CONV-01 | `3.050` | `54.94754950` | `critical_low` | Converted < 55 |
| GC-CONV-02 | `3.053` | `55.00159627` | `normal` / not critical | Converted > 55 |
| GC-CONV-03 | `3.054` | `55.01961186` | `normal` / not critical | Converted > 55 |
| GC-CONV-04 | `3.055` | `55.03762745` | `normal` / not critical | Converted > 55 |
| GC-CONV-05 | `24.97` | `449.84928230` | `normal` / not critical | Converted < 450 |
| GC-CONV-06 | `24.99` | `450.20959410` | `critical_high` | Converted > 450 |

---

### Test group 3: Conversion function unit tests (`measurement_conversion.py`)

| Test ID | Input (mmol/L) | Expected result (Decimal) |
|---|---|---|
| GC-FN-01 | `1.0` | `Decimal("18.01559")` |
| GC-FN-02 | `0.0` | `Decimal("0")` |
| GC-FN-03 | `3.050` | `Decimal("54.94754950")` |
| GC-FN-04 | `24.99` | `Decimal("450.20959410")` |

---

### Test group 4 & 5: Unit safety and fail-closed behavior

| Test ID | Scenario | Standalone Detector Behavior | End-to-End Pipeline Behavior | Expected Result |
|---|---|---|---|---|
| GC-SAFE-01 | Glucose `27.8 g/L` vs threshold `mg/dL` (unsupported unit, no conversion) | Fail closed | RI unknown → Critical skipped | **No critical alert** (no raw cross-unit comparison) |
| GC-SAFE-02 | Glucose `3.050 mmol/L` vs threshold `mg/dL` (approved conversion) | Converts to `54.94754950 mg/dL` | Evaluated against RI, then evaluated for critical | **critical_low** alert |
| GC-SAFE-03 | Glucose `55.0 mg/dL` vs threshold `mg/dL` (same unit) | Direct comparison allowed | RI unknown (`unit_not_supported`) → Critical skipped | Standalone: **not critical**; E2E: **status=unknown** |

---

### Test group 6: Upstream unknown preservation

| Test ID | Scenario | Expected |
|---|---|---|
| GC-UNK-01 | Glucose `50.0 mg/dL` input → RI returns `status=unknown` → Critical Detector | Critical evaluation skipped, status remains `unknown` (Blocker 02 preserved) |
| GC-UNK-02 | Glucose `3.050 mmol/L` input → RI returns `low` → Critical Detector | Critical Detector escalates to `critical_low` |

---

### Test group 7 & 8: Invariants preserved

- `reference_ranges.json` and RI classification logic unchanged.
- `reference_checker_v2_config.json` generic `Glucose → Fasting plasma glucose` alias unchanged.

---

## Part 10 — Implementation impact

| File | Type | Role in Patch B |
|---|---|---|
| `src/services/measurement_conversion.py` | [NEW] | Implements `glucose_mmol_l_to_mg_dl` using `GLUCOSE_MW_NIST = Decimal("180.1559")` |
| `src/agents/nodes/critical_detector_node.py` | [MODIFY] | Implements Decimal conversion and comparison for records with conversion strategy |
| `tests/test_services/test_measurement_conversion.py` | [NEW] | Tests for conversion function |
| `tests/test_agents/test_critical_detector_node.py` | [MODIFY] | Adds test groups GC-SRC, GC-CONV, GC-SAFE |

*Note:* `data/reference/critical_thresholds.json` threshold migration is deferred to Patch C.

---

## Part 11 — Frozen contract: GLUCOSE-CONV-01

```text
GLUCOSE-CONV-01 CONTRACT SPECIFICATION:

1. Source rule literals:
   - Low:  Decimal("55"),  Operator: "<"
   - High: Decimal("450"), Operator: ">"
   - Unit: "mg/dL"

2. Input canonical unit:
   - "mmol/L"

3. Conversion authority:
   - NIST Chemistry WebBook (CAS 492-62-6, α-D-Glucose, MW = 180.1559 g/mol)
   - URL: https://webbook.nist.gov/cgi/cbook.cgi?ID=C492626

4. Conversion formula:
   - value_mg_dl = Decimal(str(value_mmol_l)) * Decimal("180.1559") / Decimal("10")

5. Comparison arithmetic:
   - Direct Decimal comparison (converted_mg_dl < Decimal("55") / converted_mg_dl > Decimal("450"))
   - No quantization or rounding before comparison.

6. Threshold conversion:
   - NO (Thresholds remain literal 55 and 450 mg/dL).

7. Input converted to source unit:
   - YES (Strategy B).

8. Upstream unknown fail-closed:
   - PRESERVED.
```

---

## Mandatory final answers

```text
NIST_EXACT_SOURCE_URL_CORRECTED = YES
NUMERIC_EXAMPLES_RECALCULATED = YES
THREE_POINT_LOW_BOUNDARY_LOGIC_CORRECT = YES
THREE_POINT_HIGH_BOUNDARY_LOGIC_CORRECT = YES
GC_SAFE_01_CONTRADICTION_REMOVED = YES
DECIMAL_USED_THROUGH_FINAL_COMPARISON = YES
SOURCE_THRESHOLDS_REMAIN_55_AND_450 = YES
STRATEGY_B_UNCHANGED = YES
CODE_CHANGED = NO
DATA_CHANGED = NO
READY_FOR_HUMAN_GLUCOSE_CONV_01_APPROVAL = YES
```
