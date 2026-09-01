# OCR Evaluation Report — LumiLab

**Run timestamp:** 2026-08-31 16:01:09 UTC  
**Test images:** `ocr_eval/png/` (20 PNG files)  
**Ground truth:** `ocr_eval/mock_data.json`  
**OCR engine:** Gemini Vision (primary) / OpenRouter (fallback)  
**Value tolerance:** ±1% relative  

---

## 1. Executive Summary

| # | Metric | Value | Threshold | Status |
|---|--------|-------|-----------|--------|
| 1 | **Analyte Precision** | 100.0% | ≥ 90% | ✅ PASS |
| 2 | **Analyte Recall** | 100.0% | ≥ 85% | ✅ PASS |
| 3 | **Analyte F1-score** | 100.0% | ≥ 87% | ✅ PASS |
| 4 | **Value Accuracy** | 100.0% | ≥ 90% | ✅ PASS |
| 5 | **Unit Accuracy** | 94.4% | ≥ 95% | ⚠️ WARN |
| 6 | **Reference Range Accuracy** | 99.8% | ≥ 90% | ✅ PASS |
| 7 | **Complete Record Accuracy** | 94.4% | ≥ 80% | ✅ PASS |
| 8 | **Critical OCR Error Rate** | 0.0% | = 0% | ✅ PASS |
| 9 | **False Positive Analyte Rate** | 0.0% | ≤ 5% | ✅ PASS |
| 10 | **Report Success Rate** | 100.0% | ≥ 95% | ✅ PASS |
| 11 | **Mean Latency** | 6,903 ms | ≤ 10 000 ms | ✅ PASS |
| 12 | **P95 Latency** | 9,434 ms | ≤ 15 000 ms | ✅ PASS |

> **Overall: 11/12 metrics passed their target threshold.**

---

## 2. Metric Definitions & Computation

All metrics are computed across the **matched indicator pairs** (OCR row that successfully
resolved to a supported canonical analyte present in the golden dataset).

| # | Metric | Formula | Notes |
|---|--------|---------|-------|
| 1 | Analyte Precision | matched / total_ocr_rows | Of all rows OCR returned, how many mapped to a known golden analyte |
| 2 | Analyte Recall | matched / 35 per report | Of all 35 golden analytes, how many did OCR detect |
| 3 | Analyte F1 | 2·P·R / (P+R) | Harmonic mean of Precision and Recall |
| 4 | Value Accuracy | val_ok_rows / matched | OCR value within ±1 % of golden value_numeric |
| 5 | Unit Accuracy | unit_ok_rows / matched | normalize(OCR.unit) == golden.unit_canonical |
| 6 | Reference Range Accuracy | flag_ok / RI_ONE_SIDED_rows | Recomputed flag from OCR value matches golden flag (RI + ONE_SIDED_LIMIT only) |
| 7 | Complete Record Accuracy | complete_rows / matched | Name matched **AND** value OK **AND** unit OK |
| 8 | Critical OCR Error Rate | critical_rows / matched | Decimal shift (≥10×) OR dangerous unit swap (g/L↔g/dL, mmol/L↔mg/dL, …) |
| 9 | False Positive Analyte Rate | phantom_rows / total_ocr_rows | OCR hallucinated a row not in the golden analyte set |
| 10 | Report Success Rate | successful_api_calls / 20 | API returned parseable structured output |
| 11 | Mean Latency | mean(t_total_ms) | End-to-end: preprocess + OCR per report |
| 12 | P95 Latency | 95th_pct(t_total_ms) | Tail latency; target ≤ 15 000 ms |

---

## 3. Detailed Results

### 3.1 Analyte Detection (Metrics 1–3)

- Total golden analyte slots: **700** (20 reports × 35 indicators)
- Total OCR rows returned:    **700**
- Successfully matched rows:  **700**
- Phantom (unresolved) rows:  **0**
- Missing (not found by OCR): **0**

| Metric | Value |
|--------|-------|
| Analyte Precision | 100.00% (700/700) |
| Analyte Recall    | 100.00% (700/700) |
| Analyte F1-score  | 100.00% |

### 3.2 Value Accuracy (Metric 4)

- Tolerance: ±1 % relative (absolute floor 0.001)
- Correct:   **700 / 700** matched rows  →  100.00%
- Incorrect: **0** rows

### 3.3 Unit Accuracy (Metric 5)

- Correct:   **661 / 700**  →  94.43%
- Incorrect: **39** rows

### 3.4 Reference Range Accuracy (Metric 6)

- Applicable rows (RI + ONE_SIDED_LIMIT): **580**
- Correct flag:   **579 / 580**  →  99.83%
- Incorrect flag: **1** rows

### 3.5 Complete Record Accuracy (Metric 7)

- Complete (name matched + value OK + unit OK): **661 / 700**  →  94.43%

### 3.6 Critical OCR Error Rate (Metric 8)

Critical errors are **decimal shifts** (OCR value is ≥10× off: e.g. 1.7 read as 17) or **dangerous unit swaps** (g/L↔g/dL, mmol/L↔mg/dL, 10⁹/L↔10¹²/L) that would change clinical interpretation.

- Critical errors found: **0** / 700 matched rows  →  0.00%

> ✅ No critical errors detected.

### 3.7 False Positive Analyte Rate (Metric 9)

- Phantom rows (OCR hallucinated / unresolvable): **0** / 700  →  0.00%

### 3.8 Confidence Calibration

Value accuracy broken down by OCR self-reported confidence bucket:

| Confidence bucket | OCR rows | Value-correct rows | Accuracy |
|-------------------|---------|--------------------|----------|
| [0.0–0.5) | 0 | 0 | — |
| [0.5–0.7) | 0 | 0 | — |
| [0.7–0.9) | 0 | 0 | — |
| [0.9–1.0] | 700 | 700 | 100.0% |

> A well-calibrated model shows monotonically increasing accuracy as confidence rises.

---

## 4. Per-Report Breakdown

| Report | Scenario | OCR rows | Matched | Phantom | Missing | Val OK | Unit OK | Complete | Total (ms) |
|--------|----------|----------|---------|---------|---------|--------|---------|----------|------------|
| OCR-GOLDEN-001 | normal_male_baseline | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 7,130 |
| OCR-GOLDEN-002 | normal_female_baseline | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,747 |
| OCR-GOLDEN-003 | iron_deficiency_anemia | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,472 |
| OCR-GOLDEN-004 | chronic_disease_anemia_hypoalb | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 6,072 |
| OCR-GOLDEN-005 | acute_bacterial_infection | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 6,344 |
| OCR-GOLDEN-006 | severe_dyslipidemia | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 10,378 |
| OCR-GOLDEN-007 | mixed_lipid_disorder | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 7,449 |
| OCR-GOLDEN-008 | prediabetes_metabolic | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 9,434 |
| OCR-GOLDEN-009 | diabetes_type2_with_complicati | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,572 |
| OCR-GOLDEN-010 | alcoholic_hepatitis_liver_dysf | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 8,319 |
| OCR-GOLDEN-011 | chronic_kidney_disease_stage3 | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,773 |
| OCR-GOLDEN-012 | gout_metabolic_syndrome | 35 | 35 | 0 | 0 | 35/35 | 34/35 | 34/35 | 6,394 |
| OCR-GOLDEN-013 | electrolyte_imbalance_hyponatr | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 6,701 |
| OCR-GOLDEN-014 | pancytopenia_thrombocytopenia | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 6,194 |
| OCR-GOLDEN-015 | CRITICAL_hyperkalemia_acute_ki | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 8,049 |
| OCR-GOLDEN-016 | CRITICAL_severe_microcytic_ane | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 8,987 |
| OCR-GOLDEN-017 | multi_system_chronic_disease | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,819 |
| OCR-GOLDEN-018 | multi_system_geriatric | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,476 |
| OCR-GOLDEN-019 | boundary_values_at_lower_limit | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,207 |
| OCR-GOLDEN-020 | boundary_values_at_lower_limit | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 7,543 |

---

## 5. Latency Profile (Metrics 11–12)

| Percentile | Latency |
|------------|---------|
| Min        | 5,207 ms |
| P50        | 6,344 ms |
| P95        | 9,434 ms |
| P99        | 10,378 ms |
| Max        | 10,378 ms |
| Mean       | 6,903 ms |

**Per-report latency breakdown:**

| Report | Preprocess (ms) | OCR API (ms) | Total (ms) |
|--------|----------------|--------------|------------|
| OCR-GOLDEN-001 | 457 | 6,672 | 7,130 |
| OCR-GOLDEN-002 | 438 | 5,308 | 5,747 |
| OCR-GOLDEN-003 | 444 | 5,028 | 5,472 |
| OCR-GOLDEN-004 | 450 | 5,622 | 6,072 |
| OCR-GOLDEN-005 | 456 | 5,887 | 6,344 |
| OCR-GOLDEN-006 | 454 | 9,923 | 10,378 |
| OCR-GOLDEN-007 | 461 | 6,988 | 7,449 |
| OCR-GOLDEN-008 | 450 | 8,983 | 9,434 |
| OCR-GOLDEN-009 | 455 | 5,116 | 5,572 |
| OCR-GOLDEN-010 | 456 | 7,862 | 8,319 |
| OCR-GOLDEN-011 | 457 | 5,315 | 5,773 |
| OCR-GOLDEN-012 | 456 | 5,937 | 6,394 |
| OCR-GOLDEN-013 | 455 | 6,246 | 6,701 |
| OCR-GOLDEN-014 | 462 | 5,732 | 6,194 |
| OCR-GOLDEN-015 | 462 | 7,587 | 8,049 |
| OCR-GOLDEN-016 | 454 | 8,533 | 8,987 |
| OCR-GOLDEN-017 | 460 | 5,359 | 5,819 |
| OCR-GOLDEN-018 | 478 | 4,997 | 5,476 |
| OCR-GOLDEN-019 | 443 | 4,764 | 5,207 |
| OCR-GOLDEN-020 | 465 | 7,077 | 7,543 |

---

## 7. Recommendations

1. **Unit Accuracy thấp** — Thêm unit normalisation layer ở server-side trước khi so sánh, hoặc chuẩn hoá alias trong system prompt.

---

*Report generated by `ocr_eval/run_eval.py`. Do not edit manually — re-run the script to refresh.*