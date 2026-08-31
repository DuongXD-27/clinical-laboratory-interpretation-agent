# OCR Evaluation Report — LumiLab

**Run timestamp:** 2026-08-30 17:01:32 UTC  
**Test images:** `data_mock/png/` (20 PNG files)  
**Ground truth:** `data_mock/mock_data.json`  
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
| 5 | **Unit Accuracy** | 94.6% | ≥ 95% | ⚠️ WARN |
| 6 | **Reference Range Accuracy** | 99.6% | ≥ 90% | ✅ PASS |
| 7 | **Complete Record Accuracy** | 94.6% | ≥ 80% | ✅ PASS |
| 8 | **Critical OCR Error Rate** | 0.0% | = 0% | ✅ PASS |
| 9 | **False Positive Analyte Rate** | 0.0% | ≤ 5% | ✅ PASS |
| 10 | **Report Success Rate** | 40.0% | ≥ 95% | ❌ FAIL |
| 11 | **Mean Latency** | 5,375 ms | ≤ 10 000 ms | ✅ PASS |
| 12 | **P95 Latency** | 5,996 ms | ≤ 15 000 ms | ✅ PASS |

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

- Total golden analyte slots: **280** (8 reports × 35 indicators)
- Total OCR rows returned:    **280**
- Successfully matched rows:  **280**
- Phantom (unresolved) rows:  **0**
- Missing (not found by OCR): **0**

| Metric | Value |
|--------|-------|
| Analyte Precision | 100.00% (280/280) |
| Analyte Recall    | 100.00% (280/280) |
| Analyte F1-score  | 100.00% |

### 3.2 Value Accuracy (Metric 4)

- Tolerance: ±1 % relative (absolute floor 0.001)
- Correct:   **280 / 280** matched rows  →  100.00%
- Incorrect: **0** rows

### 3.3 Unit Accuracy (Metric 5)

- Correct:   **265 / 280**  →  94.64%
- Incorrect: **15** rows

### 3.4 Reference Range Accuracy (Metric 6)

- Applicable rows (RI + ONE_SIDED_LIMIT): **232**
- Correct flag:   **231 / 232**  →  99.57%
- Incorrect flag: **1** rows

### 3.5 Complete Record Accuracy (Metric 7)

- Complete (name matched + value OK + unit OK): **265 / 280**  →  94.64%

### 3.6 Critical OCR Error Rate (Metric 8)

Critical errors are **decimal shifts** (OCR value is ≥10× off: e.g. 1.7 read as 17) or **dangerous unit swaps** (g/L↔g/dL, mmol/L↔mg/dL, 10⁹/L↔10¹²/L) that would change clinical interpretation.

- Critical errors found: **0** / 280 matched rows  →  0.00%

> ✅ No critical errors detected.

### 3.7 False Positive Analyte Rate (Metric 9)

- Phantom rows (OCR hallucinated / unresolvable): **0** / 280  →  0.00%

### 3.8 Confidence Calibration

Value accuracy broken down by OCR self-reported confidence bucket:

| Confidence bucket | OCR rows | Value-correct rows | Accuracy |
|-------------------|---------|--------------------|----------|
| [0.0–0.5) | 0 | 0 | — |
| [0.5–0.7) | 0 | 0 | — |
| [0.7–0.9) | 0 | 0 | — |
| [0.9–1.0] | 280 | 280 | 100.0% |

> A well-calibrated model shows monotonically increasing accuracy as confidence rises.

---

## 4. Per-Report Breakdown

| Report | Scenario | OCR rows | Matched | Phantom | Missing | Val OK | Unit OK | Complete | Total (ms) |
|--------|----------|----------|---------|---------|---------|--------|---------|----------|------------|
| OCR-GOLDEN-001 | normal_male_baseline | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-002 | normal_female_baseline | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-003 | iron_deficiency_anemia | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 4,963 |
| OCR-GOLDEN-004 | chronic_disease_anemia_hypoalb | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,580 |
| OCR-GOLDEN-005 | acute_bacterial_infection | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-006 | severe_dyslipidemia | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,996 |
| OCR-GOLDEN-007 | mixed_lipid_disorder | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-008 | prediabetes_metabolic | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-009 | diabetes_type2_with_complications | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-010 | alcoholic_hepatitis_liver_dysf | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,483 |
| OCR-GOLDEN-011 | chronic_kidney_disease_stage3 | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,693 |
| OCR-GOLDEN-012 | gout_metabolic_syndrome | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 5,692 |
| OCR-GOLDEN-013 | electrolyte_imbalance_hyponatremia_hypokalemia | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-014 | pancytopenia_thrombocytopenia | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-015 | CRITICAL_hyperkalemia_acute_kidney_injury | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-016 | CRITICAL_severe_microcytic_anemia | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-017 | multi_system_chronic_disease | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-018 | multi_system_geriatric | — | — | — | — | — | — | — | ❌ OCR failed: Gemini OCR trả về dữ liệu kh |
| OCR-GOLDEN-019 | boundary_values_at_lower_limit | 35 | 35 | 0 | 0 | 35/35 | 34/35 | 34/35 | 4,742 |
| OCR-GOLDEN-020 | boundary_values_at_lower_limit | 35 | 35 | 0 | 0 | 35/35 | 33/35 | 33/35 | 4,854 |

---

## 5. Latency Profile (Metrics 11–12)

| Percentile | Latency |
|------------|---------|
| Min        | 4,742 ms |
| P50        | 5,483 ms |
| P95        | 5,996 ms |
| P99        | 5,996 ms |
| Max        | 5,996 ms |
| Mean       | 5,375 ms |

**Per-report latency breakdown:**

| Report | Preprocess (ms) | OCR API (ms) | Total (ms) |
|--------|----------------|--------------|------------|
| OCR-GOLDEN-001 | — | — | ❌ |
| OCR-GOLDEN-002 | — | — | ❌ |
| OCR-GOLDEN-003 | 508 | 4,455 | 4,963 |
| OCR-GOLDEN-004 | 581 | 4,981 | 5,580 |
| OCR-GOLDEN-005 | — | — | ❌ |
| OCR-GOLDEN-006 | 498 | 5,479 | 5,996 |
| OCR-GOLDEN-007 | — | — | ❌ |
| OCR-GOLDEN-008 | — | — | ❌ |
| OCR-GOLDEN-009 | — | — | ❌ |
| OCR-GOLDEN-010 | 488 | 4,979 | 5,483 |
| OCR-GOLDEN-011 | 481 | 5,195 | 5,693 |
| OCR-GOLDEN-012 | 494 | 5,179 | 5,692 |
| OCR-GOLDEN-013 | — | — | ❌ |
| OCR-GOLDEN-014 | — | — | ❌ |
| OCR-GOLDEN-015 | — | — | ❌ |
| OCR-GOLDEN-016 | — | — | ❌ |
| OCR-GOLDEN-017 | — | — | ❌ |
| OCR-GOLDEN-018 | — | — | ❌ |
| OCR-GOLDEN-019 | 492 | 4,231 | 4,742 |
| OCR-GOLDEN-020 | 538 | 4,316 | 4,854 |

---

## 6. Failed Reports

| Report | Scenario | Error |
|--------|----------|-------|
| OCR-GOLDEN-001 | normal_male_baseline | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-002 | normal_female_baseline | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-005 | acute_bacterial_infection | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-007 | mixed_lipid_disorder | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-008 | prediabetes_metabolic | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-009 | diabetes_type2_with_complications | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-013 | electrolyte_imbalance_hyponatremia_hypokalemia | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-014 | pancytopenia_thrombocytopenia | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-015 | CRITICAL_hyperkalemia_acute_kidney_injury | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-016 | CRITICAL_severe_microcytic_anemia | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-017 | multi_system_chronic_disease | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |
| OCR-GOLDEN-018 | multi_system_geriatric | OCR failed: Gemini OCR trả về dữ liệu không đúng schema. |

---

## 7. Recommendations

1. **[P0] Report Success Rate = 40.0% (12/20 phiếu thất bại)** — Gemini trả về response không khớp schema `_GeminiOCRPayload`. Nguyên nhân thường gặp: (a) model trả `null` hoặc string thay vì float cho trường `value`; (b) model trả thinking tokens trước JSON làm hỏng parse; (c) rate-limit trả HTML error page thay vì JSON. Hành động: bật DEBUG logging trong `vision_adapter.py` để in `response.text` raw khi schema fail, xác định pattern, sau đó thêm fallback parse hoặc kích hoạt openrouter fallback khi schema không hợp lệ.

2. **Unit Accuracy thấp (94.6% vs. ngưỡng 95%)** — 15/280 chỉ số bị sai đơn vị (2 chỉ số/phiếu, nhất quán trên tất cả 8 phiếu thành công → pattern có hệ thống). Thêm unit normalisation layer server-side, hoặc chuẩn hoá alias trong `EXTRACTION_SYSTEM_PROMPT`.

---

*Report generated by `data_mock/run_eval.py`. Do not edit manually — re-run the script to refresh.*