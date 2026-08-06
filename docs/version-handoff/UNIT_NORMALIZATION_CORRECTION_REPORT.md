# UNIT NORMALIZATION CORRECTION REPORT

## Summary

A post-VERIFY data-integrity defect was identified in the V2 reference pipeline: the build script's
`normalize_unit()` function applied `.upper()` to the raw unit string before performing a
dictionary lookup. This caused the lowercase source unit `g/L` (mass per volume) to be
silently promoted to the uppercase key `G/L`, which then mapped to the count unit `10^9/L`.

Six accepted reference rules for HGB, MCHC, Albumin, and Total protein were affected.
The fix was applied in BONUS-TIP-008.

This correction was not part of the original TIP-006 verification scope. TIP-006 verified
the overall delivery; the normalization defect was detected by independent inspection of
the generated JSON artifacts.

---

## Detection

The defect was detected by inspecting `data/reference/reference_ranges_v2.json` and
observing that rules for HGB, MCHC, Albumin, and Total protein — all sourced from `g/L`
rows in the CSV — stored `unit_canonical=10^9/L` instead of the expected `g/L`.

Root cause was confirmed by reading `src/scripts/build_reference_config.py` lines 140–159
(original) and reproducing the faulty transformation.

---

## Root cause

**File:** `src/scripts/build_reference_config.py`

**Function:** `normalize_unit()` — lines 140–159 (original)

**Faulty transformation:**

```python
upper_text = text.upper()       # "g/L" → "G/L"
if upper_text in canonical_map: # "G/L" IS in the map
    return canonical_map[upper_text]  # → returns "10^9/L"  ← BUG
```

The canonical map used UPPERCASE keys because the lookup always applied `.upper()` first.
This made the map case-insensitive as a side effect — so `g/L`, `G/L`, and `g/l` all
resolved to `10^9/L`.

**The fix:** Replace the case-insensitive lookup with a case-sensitive `dict.get()` using
the actual source strings as keys. The canonical map now exactly mirrors the one in
`reference_repository.py` (which was already correct).

**Runtime repository:** `reference_repository.py`'s `normalize_unit()` was already
case-sensitive and did not have this defect. The repository was not modified for the fix.

---

## Affected records

All six records are in the 58-row accepted set. The quarantine set and source counts
are unchanged.

| Rule ID | Analyte | Sex | Old `unit_canonical` | New `unit_canonical` | Runtime-approved |
|---|---|---|---|---|---|
| RRV2-0005 | HGB | M | `10^9/L` | `g/L` | No — pending |
| RRV2-0006 | HGB | F | `10^9/L` | `g/L` | No — pending |
| RRV2-0013 | MCHC | M | `10^9/L` | `g/L` | No — outside approved set |
| RRV2-0014 | MCHC | F | `10^9/L` | `g/L` | No — outside approved set |
| RRV2-0052 | Total protein | A | `10^9/L` | `g/L` | No — outside approved set |
| RRV2-0053 | Albumin | A | `10^9/L` | `g/L` | No — outside approved set |

---

## Runtime impact

Before the fix, the runtime impact was partly contained by the approved-analyte whitelist:

- HGB was listed in `approved_analytes` in `reference_checker_v2_config.json`
- At runtime, `_find_unit_conflicts()` compared the HGB rule's `unit_canonical` (`10^9/L`)
  against `units_metric.csv` standardized unit (`g/L`)
- Because these did not match, HGB was demoted to `unit_conflict_analytes` and returned
  `unit_data_conflict` for any HGB lookup request
- MCHC, Albumin, and Total protein were not in `approved_analytes`, so they had no runtime
  normal-checker effect regardless of the stored `unit_canonical`
- The four approved analytes (WBC, RBC, Fasting plasma glucose, Creatinine) were not affected

After the fix, the wrong `unit_canonical` is corrected in the stored JSON. HGB's technical
conflict is now resolved. HGB has been moved to `pending_analytes` in
`reference_checker_v2_config.json` to ensure it remains non-approved until a human
medical/data owner review grants approval.

---

## Fix

**Modified file:** `src/scripts/build_reference_config.py`

**Change:** Replace the case-insensitive `.upper()` + map lookup with a case-sensitive
`canonical_map.get(text, text)` using the actual source string forms as keys.

Before:

```python
canonical_map = {
    ...
    "G/L": "10^9/L",    # uppercase key — worked for G/L display unit
    "T/L": "10^12/L",   # uppercase key — worked for T/L display unit
}
upper_text = text.upper()          # "g/L" → "G/L"  ← COLLIDES WITH G/L
if upper_text in canonical_map:
    return canonical_map[upper_text]   # BUG: g/L → "10^9/L"
return text
```

After:

```python
canonical_map = {
    "×10^9/L": "10^9/L",
    "10^9/L": "10^9/L",
    "×10^12/L": "10^12/L",
    "10^12/L": "10^12/L",
    "µmol/L": "umol/L",   # micro sign
    "μmol/L": "umol/L",   # Greek mu
    "umol/L": "umol/L",
    "G/L": "10^9/L",      # uppercase G/L display unit → count
    "T/L": "10^12/L",     # uppercase T/L display unit → count
}
return canonical_map.get(text, text)   # case-sensitive; g/L ≠ G/L
```

**Invariants preserved:**

| Input | Result |
|---|---|
| `normalize_unit("g/L")` | `"g/L"` (no longer collides) |
| `normalize_unit("G/L")` | `"10^9/L"` (display unit alias preserved) |
| `normalize_unit("T/L")` | `"10^12/L"` (display unit alias preserved) |
| `normalize_unit("×10^9/L")` | `"10^9/L"` (preserved) |
| `normalize_unit("µmol/L")` | `"umol/L"` (preserved, now using actual source form) |
| `normalize_unit("mmol/L")` | `"mmol/L"` (no alias, unchanged) |

---

## Generated artifact changes

The following files were regenerated by running `src/scripts/build_reference_config.py`:

| File | Change |
|---|---|
| `data/reference/reference_ranges_v2.json` | 6 rules: `unit_canonical` corrected from `10^9/L` to `g/L` |
| `data/reference/reference_ranges_v2.csv` | Same 6 rules updated |
| `data/reference/reference_build_report.json` | Regenerated timestamp and output SHA-256 values |
| `data/reference/quarantine_v2.csv` | Regenerated (no content change — quarantine is not affected) |

**Row counts unchanged:** input=80, accepted=58, quarantined=22, multiple-reason=2

**Source CSV unchanged:** `adult_outpatient_laboratory_reference_map.csv` was not modified.
Source SHA-256 was verified before and after the build.

**`units_metric.csv` unchanged:** The source-of-truth for expected units was not modified.

---

## HGB policy reassessment

| Field | Before fix | After fix |
|---|---|---|
| Source unit (`unit_machine`) | `g/L` | `g/L` (unchanged) |
| Unit-map standardized unit (`units_metric.csv`) | `g/L` | `g/L` (unchanged) |
| Stored `unit_canonical` | `10^9/L` (wrong) | `g/L` (correct) |
| Runtime `unit_conflict_analytes` | Yes — `{"10^9/L"} ≠ {"g/L"}` | No — `{"g/L"} == {"g/L"}` |
| `reference_checker_v2_config.json` placement | `approved_analytes` (blocked by runtime conflict) | `pending_analytes` (explicitly pending) |
| `select_rule` reason for HGB requests | `unit_data_conflict` | `analyte_not_approved` |
| Normal RI approval status | Not approved | Still not approved |

**HGB is NOT auto-approved.** The technical unit conflict is resolved. HGB has been explicitly
moved to `pending_analytes` in `reference_checker_v2_config.json`. Normal RI approval
requires a separate human decision by the medical and data owner.

MCHC, Albumin, and Total protein were not in the approved set before or after the fix.
Their `unit_canonical` is corrected, but they remain outside the normal-checker whitelist
and require separate approval decisions.

---

## Tests

The following new tests were added (fail before fix, pass after):

| Test | File | Covers |
|---|---|---|
| `test_unit_g_l_case_sensitive` | `test_build_reference_config.py` | Builder: `g/L` stays `g/L`, `G/L` stays `10^9/L` |
| `test_unit_t_l_case_sensitive` | `test_build_reference_config.py` | Builder: `T/L` → `10^12/L` |
| `test_unit_source_analytes_regenerate_with_g_l_canonical` | `test_build_reference_config.py` | All 6 affected rule IDs have `unit_canonical=g/L` after rebuild |
| `test_unit_wbc_rbc_canonical_unaffected_by_fix` | `test_build_reference_config.py` | WBC and RBC unaffected |
| `test_unit_g_l_not_mapped_to_count_unit` | `test_reference_repository.py` | Repository: `g/L` → `g/L` |
| `test_unit_G_L_uppercase_maps_to_count` | `test_reference_repository.py` | Repository: `G/L` → `10^9/L` |
| `test_unit_g_l_not_matched_as_wbc_unit` | `test_reference_repository.py` | `g/L` input does not match `10^9/L` WBC rule |

The following existing test was updated to reflect post-fix behavior:

| Test | Change |
|---|---|
| `test_u_wbc_09_hgb_remains_pending_after_unit_fix` (renamed) | Now checks: HGB not in `unit_conflict_analytes`, HGB in `pending_analytes`, reason=`analyte_not_approved` |
| `test_m04_hgb_blocker` | Now checks: `awaiting_medical_approval` in blockers, not `unit_data_conflict` |

---

## RAGAS impact

| Item | Status |
|---|---|
| RAGAS dataset changed | No — `eval/datasets/ragas_v2_baseline.jsonl` not modified |
| RAGAS results changed | No — `eval/results/ragas_v2_baseline.json` not modified |
| Live RAGAS calls | None |

The RAGAS baseline covers WBC, RBC, Fasting plasma glucose, and Creatinine — all approved
analytes whose `unit_canonical` was not affected by this bug. No re-evaluation is required.

---

## Protected-file integrity

| File | Modified |
|---|---|
| `src/agents/graph.py` | No |
| `src/agents/state.py` | No |
| `src/agents/nodes/analyzer_node.py` | No |
| `src/agents/nodes/critical_detector_node.py` | No |
| `data/reference/critical_thresholds.json` | No |
| `data/reference/units_metric.csv` | No |
| `adult_outpatient_laboratory_reference_map.csv` | No |
| `eval/datasets/ragas_v2_baseline.jsonl` | No |
| `eval/results/ragas_v2_baseline.json` | No |
| `requirements.txt` | No |

---

## Remaining decisions

The following items require human medical and data owner decisions before HGB or any other
affected analyte can be approved for normal RI classification:

1. **HGB** — Technical unit conflict resolved. Normal RI approval requires medical/data owner
   confirmation that the available RI ranges (sex-specific M and F, unit g/L) are appropriate
   for the target population and measurement context.

2. **MCHC** — `unit_canonical` corrected to `g/L`. MCHC is not in the approved-analyte
   whitelist. Requires separate normal-reference approval decision.

3. **Albumin** — `unit_canonical` corrected to `g/L`. Not in the approved-analyte whitelist.
   Requires separate approval decision.

4. **Total protein** — `unit_canonical` corrected to `g/L`. Not in the approved-analyte
   whitelist. Requires separate approval decision.

The four currently approved analytes (WBC, RBC, Fasting plasma glucose, Creatinine) are
unaffected and continue to operate correctly.
