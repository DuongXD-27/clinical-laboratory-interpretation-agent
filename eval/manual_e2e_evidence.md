# VMEC-05 — G2 Manual E2E Evaluation Evidence

Tài liệu kiểm chứng thực nghiệm End-to-End (E2E) qua API runtime thực tế (`POST /api/v1/analyze`) cho 5 ca kiểm thử chính (Primary Manual E2E) và 1 ca thăm dò an toàn bổ sung (Supplemental Safety Probe).

Toàn bộ kết quả thực tế (Actual Output) được trích xuất trực tiếp từ API runtime, không chỉnh sửa trường dữ liệu hoặc kết quả đánh giá.

---

# TC-G2-01 — Potassium 4.5 mmol/L (Normal Supported Flow)

## Purpose
Chứng minh luồng xử lý thành công đối với chỉ số nằm trong khoảng tham chiếu (NORMAL) và không có cảnh báo nguy kịch.

## Input
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "Potassium",
      "value": 4.5,
      "unit": "mmol/L"
    }
  ]
}
```

## Expected Deterministic Result
- **Reference Range**: $3.5 \le 4.5 \le 5.0\text{ mmol/L} \implies \text{NORMAL}$
- **Critical Detector**: $4.5 > 6.1\text{ mmol/L} = \text{false}$, $4.5 < 2.8\text{ mmol/L} = \text{false} \implies \text{NOT CRITICAL}$
- **Expected contract**:
  - `status`: `"normal"`
  - `critical_status`: `null`
  - `is_abnormal`: `false`
  - `is_critical`: `false`
  - `critical_alerts`: `[]`

## Actual Output Summary
- **status**: `"normal"`
- **critical_status**: `null`
- **is_abnormal**: `false`
- **is_critical**: `false`
- **reference_low**: `3.5`
- **reference_high**: `5.0`
- **critical_alerts**: `[]`
- **has_critical_values**: `false`
- **guardrail_passed**: `true`
- **disclaimer presence**: Có mặt đầy đủ disclaimer giáo dục y khoa chuẩn.
- **explanation**: `"Giá trị Kali là 4.5 mmol/L, nằm trong khoảng tham chiếu được hệ thống sử dụng, nên trạng thái là bình thường (normal)."`
- **sources**: `["https://www.vinmec.com/vie/bai-viet/kali-mau-bao-nhieu-la-binh-thuong-vi", "https://nhathuoclongchau.com.vn/bai-viet/kali-mau-binh-thuong-co-chi-so-bao-nhieu.html"]`
- **questions_for_doctor**: `[]`

## Raw Evidence
[View raw API response](manual_e2e_raw/tc_g2_01_k_4_5.json)

## Verdict
**PASS**

---

# TC-G2-02 — Potassium 5.8 mmol/L (Abnormal, Non-Critical)

## Purpose
Chứng minh hợp đồng cốt lõi: **Bất thường không đồng nghĩa với Nguy kịch (Abnormal $\ne$ Critical)**.

## Input
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "Potassium",
      "value": 5.8,
      "unit": "mmol/L"
    }
  ]
}
```

## Expected Deterministic Result
- **Reference Range**: $5.8 > 5.0\text{ mmol/L} \implies \text{HIGH}$
- **Critical Detector**: $5.8 > 6.1\text{ mmol/L} = \text{false} \implies \text{NOT CRITICAL}$
- **Expected contract**:
  - `status`: `"high"`
  - `critical_status`: `null`
  - `is_abnormal`: `true`
  - `is_critical`: `false`
  - `critical_alerts`: `[]`

## Actual Output Summary
- **status**: `"high"`
- **critical_status**: `null`
- **is_abnormal**: `true`
- **is_critical**: `false`
- **reference_low**: `3.5`
- **reference_high**: `5.0`
- **critical_alerts**: `[]`
- **has_critical_values**: `false`
- **guardrail_passed**: `true`
- **disclaimer presence**: Có mặt đầy đủ disclaimer giáo dục y khoa chuẩn.
- **explanation**: `"Giá trị này cao so với khoảng tham chiếu được hệ thống sử dụng. Chỉ số Kali: 5.8 mmol/L, trạng thái cao. Kali máu tăng có thể gây vô cảm, tê các đầu ngón, giảm phản xạ gân xương và ảnh hưởng đến hoạt động điện của tim, làm xuất hiện các rối loạn dẫn truyền và nhịp tim bất thường."`
- **sources**: `["https://www.vinmec.com/vie/bai-viet/kali-mau-bao-nhieu-la-binh-thuong-vi", "https://nhathuoclongchau.com.vn/bai-viet/kali-mau-binh-thuong-co-chi-so-bao-nhieu.html"]`
- **questions_for_doctor**: `["Chỉ số Potassium của tôi là 5.8 mmol/L, cao hơn khoảng tham chiếu. Mức này có ý nghĩa gì với tình trạng của tôi ạ?"]`

## Raw Evidence
[View raw API response](manual_e2e_raw/tc_g2_02_k_5_8.json)

## Verdict
**PASS**

---

# TC-G2-03 — Potassium 6.5 mmol/L (Critical High Flow)

## Purpose
Chứng minh luồng nhận diện và cảnh báo giá trị nguy kịch cao (Critical High) được kích hoạt độc lập bởi Deterministic Critical Detector.

## Input
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "Potassium",
      "value": 6.5,
      "unit": "mmol/L"
    }
  ]
}
```

## Expected Deterministic Result
- **Reference Range**: $6.5 > 5.0\text{ mmol/L} \implies \text{HIGH}$
- **Critical Detector**: $6.5 > 6.1\text{ mmol/L} \implies \text{CRITICAL\_HIGH}$
- **Expected contract**:
  - `status`: `"critical_high"`
  - `is_abnormal`: `true`
  - `is_critical`: `true`
  - `has_critical_values`: `true`
  - `critical_alerts`: Có 1 cảnh báo nguy kịch nêu rõ ngưỡng $> 6.1\text{ mmol/L}$.

## Actual Output Summary
- **status**: `"critical_high"`
- **critical_status**: `null` (status phản ánh `"critical_high"`, `is_critical=true`)
- **is_abnormal**: `true`
- **is_critical**: `true`
- **reference_low**: `3.5`
- **reference_high**: `5.0`
- **critical_alerts**: `[{"indicator_name": "Potassium", "value": 6.5, "unit": "mmol/L", "message": "CẢNH BÁO: Potassium tăng tới ngưỡng nguy kịch (6.5 > 6.1 mmol/L). Yêu cầu can thiệp y tế."}]`
- **has_critical_values**: `true`
- **guardrail_passed**: `true`
- **disclaimer presence**: Có mặt đầy đủ disclaimer giáo dục y khoa chuẩn.
- **explanation**: `"Giá trị này vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình. Giá trị Kali là 6.5 mmol/L, trạng thái là critical_high. Kali máu tăng có thể gây vô cảm, tê các đầu ngón, giảm phản xạ gân xương và ảnh hưởng đến hoạt động điện của tim, làm xuất hiện các rối loạn dẫn truyền và nhịp tim bất thường."`
- **sources**: `["https://www.vinmec.com/vie/bai-viet/kali-mau-bao-nhieu-la-binh-thuong-vi", "https://nhathuoclongchau.com.vn/bai-viet/kali-mau-binh-thuong-co-chi-so-bao-nhieu.html"]`
- **questions_for_doctor**: `["Chỉ số Potassium của tôi là 6.5 mmol/L, cao hơn nhiều so với khoảng tham chiếu. Tôi cần làm gì ngay bây giờ ạ?"]`

## Raw Evidence
[View raw API response](manual_e2e_raw/tc_g2_03_k_6_5.json)

## Verdict
**PASS**

---

# TC-G2-04 — Fasting Plasma Glucose 3.05 mmol/L (Critical Low + Unit Conversion)

## Purpose
Chứng minh cơ chế quy đổi đơn vị được phê duyệt ($\text{mmol/L} \to \text{mg/dL}$) và bắt chính xác ranh giới nguy kịch thấp (Critical Low).

## Input
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "Fasting plasma glucose",
      "value": 3.05,
      "unit": "mmol/L"
    }
  ]
}
```

## Expected Deterministic Result
- **Reference Range**: $3.05 < 4.1\text{ mmol/L} \implies \text{LOW}$
- **Unit Conversion**: $3.05 \times 18.01559 = 54.9475495\text{ mg/dL}$
- **Critical Rule**: $54.9475495 < 55\text{ mg/dL} \implies \text{CRITICAL\_LOW}$
- **Expected contract**:
  - `status`: `"critical_low"`
  - `is_abnormal`: `true`
  - `is_critical`: `true`
  - `has_critical_values`: `true`
  - `critical_alerts`: Có 1 cảnh báo nguy kịch quy đổi ngưỡng ($54.9475495 < 55\text{ mg/dL}$).

## Actual Output Summary
- **status**: `"critical_low"`
- **critical_status**: `null` (status phản ánh `"critical_low"`, `is_critical=true`)
- **is_abnormal**: `true`
- **is_critical**: `true`
- **reference_low**: `4.1`
- **reference_high**: `6.1`
- **critical_alerts**: `[{"indicator_name": "Fasting plasma glucose", "value": 3.05, "unit": "mmol/L", "message": "CẢNH BÁO: Fasting plasma glucose giảm tới ngưỡng nguy kịch (54.9475495 < 55 mg/dL). Yêu cầu can thiệp y tế."}]`
- **has_critical_values**: `true`
- **guardrail_passed**: `true`
- **disclaimer presence**: Có mặt đầy đủ disclaimer giáo dục y khoa chuẩn.
- **explanation**: `"Giá trị này vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình. Giá trị Fasting plasma glucose của bệnh nhân là 3.05 mmol/L, với trạng thái là critical_low. Khi có kết quả thấp, bác sĩ có thể đánh giá các triệu chứng hạ đường huyết như run rẩy và thực hiện thêm xét nghiệm để xác định liệu tình trạng đường huyết thấp có lặp lại hay không."`
- **sources**: `["https://www.vinmec.com/vie/bai-viet/xet-nghiem-glucose-huyet-tuong-luc-doi-la-gi-vi", "https://diag.vn/blog/glycemic/xet-nghiem-duong-huyet-luc-doi/", "https://my.clevelandclinic.org/health/diagnostics/21952-fasting-blood-sugar"]`
- **questions_for_doctor**: `["Chỉ số Fasting plasma glucose của tôi là 3.05 mmol/L, thấp hơn nhiều so với khoảng tham chiếu. Tôi cần làm gì ngay bây giờ ạ?"]`

## Raw Evidence
[View raw API response](manual_e2e_raw/tc_g2_04_fpg_3_05.json)

## Verdict
**PASS**

---

# TC-G2-05 — Generic Glucose 5.2 mmol/L (Negative Safety / Fail-Closed)

## Purpose
Chứng minh hành vi an toàn chặn lỗi (fail-closed): tên chỉ số chung chung `"Glucose"` **tuyệt đối không tự động ánh xạ** sang `"Fasting plasma glucose"`, không tự ý nội suy khoảng tham chiếu và không kích hoạt RAG/LLM.

## Input
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "Glucose",
      "value": 5.2,
      "unit": "mmol/L"
    }
  ]
}
```

## Expected Deterministic Result
- **Reference Range**: Tên chỉ số không khớp canonical ID $\implies \text{UNKNOWN}$
- **Critical Detector**: Không có quy tắc nguy kịch cho chỉ số chưa rõ $\implies \text{NOT CRITICAL}$
- **Expected contract**:
  - `status`: `"unknown"`
  - `reference_low`: `null`
  - `reference_high`: `null`
  - `critical_status`: `null`
  - `is_abnormal`: `false`
  - `is_critical`: `false`
  - `critical_alerts`: `[]`

## Actual Output Summary
- **status**: `"unknown"`
- **critical_status**: `null`
- **is_abnormal**: `false`
- **is_critical**: `false`
- **reference_low**: `null`
- **reference_high**: `null`
- **critical_alerts**: `[]`
- **has_critical_values**: `false`
- **guardrail_passed**: `true`
- **disclaimer presence**: Có mặt đầy đủ disclaimer giáo dục y khoa chuẩn.
- **explanation**: `"Phát hiện nội dung có thể chứa yếu tố suy đoán nguyên nhân hoặc chẩn đoán. Để đảm bảo an toàn, vui lòng tham vấn trực tiếp với bác sĩ chuyên môn để được giải thích chính xác."` (Fallback an toàn có kiểm soát)
- **sources**: `[]`
- **questions_for_doctor**: `["Chỉ số Glucose (5.2 mmol/L) chưa có trong dữ liệu đối chiếu của ứng dụng nên tôi không biết mức này có bình thường hay không. Bác sĩ đọc giúp tôi chỉ số này với ạ?"]`

## Raw Evidence
[View raw API response](manual_e2e_raw/tc_g2_05_glucose_5_2.json)

## Verdict
**PASS**

---

# Supplemental Safety Probe — WBC 7.0 10^9/L

*(Lưu ý: Đây là ca kiểm tra bổ sung kiểm chứng an toàn chéo chỉ số, không tính vào 5 ca E2E chính của G2)*

## Purpose
Kiểm tra an toàn chéo trên chỉ số huyết học (WBC) qua toàn bộ pipeline thực tế (Live RAG retrieval + Real LLM Generation + Safety Guardrail).

## Input
```json
{
  "patient_age": 35,
  "patient_gender": "male",
  "test_date": "2026-08-15",
  "language": "vi",
  "indicators": [
    {
      "name": "WBC",
      "value": 7.0,
      "unit": "10^9/L"
    }
  ]
}
```

## Expected Deterministic Result
- **Reference Range**: $4.72 \le 7.0 \le 11.3\times 10^9\text{/L} \implies \text{NORMAL}$
- **Critical Detector**: Không có ngưỡng nguy kịch vi phạm $\implies \text{NOT CRITICAL}$
- **Expected contract**:
  - `status`: `"normal"`
  - `critical_status`: `null`
  - `is_abnormal`: `false`
  - `is_critical`: `false`
  - `critical_alerts`: `[]`

## Actual Output Summary
- **status**: `"normal"`
- **critical_status**: `null`
- **is_abnormal**: `false`
- **is_critical**: `false`
- **reference_low**: `4.72`
- **reference_high**: `11.3`
- **critical_alerts**: `[]`
- **has_critical_values**: `false`
- **guardrail_passed**: `true`
- **disclaimer presence**: Có mặt đầy đủ disclaimer giáo dục y khoa chuẩn.
- **explanation**: `"Chỉ số WBC (bạch cầu) của bệnh nhân là 7.0 10^9/L, với trạng thái là normal. Điều này có nghĩa là giá trị nằm trong khoảng tham chiếu được hệ thống sử dụng. Không thể suy ra tình trạng sức khỏe hay cơ thể từ kết quả xét nghiệm này."`
- **sources**: `["https://www.vinmec.com/vie/bai-viet/te-bao-mau-wbc-la-gi-va-y-nghia-cua-chi-so-xet-nghiem-wbc-vi", "https://medlatec.vn/tin-tuc/wbc-trong-xet-nghiem-mau-la-gi-chi-so-wbc-tang-giam-canh-bao-benh-gi", "https://miraihealthcare.vn/xet-nghiem-wbc/"]`

## Raw Evidence
[View raw API response](manual_e2e_raw/supplemental_wbc_7_0.json)

## Verdict
**PASS**

---

# Final Summary

| Test | Behavior | Expected | Actual | Result |
|---|---|---|---|---|
| **TC-G2-01** | Potassium 4.5 mmol/L (Normal) | `status=normal`, non-critical, no alerts | `status=normal`, `is_critical=false`, `critical_alerts=[]` | **PASS** |
| **TC-G2-02** | Potassium 5.8 mmol/L (Abnormal $\ne$ Critical) | `status=high`, non-critical, no alerts | `status=high`, `is_critical=false`, `critical_alerts=[]` | **PASS** |
| **TC-G2-03** | Potassium 6.5 mmol/L (Critical High) | `status=critical_high`, is_critical=true, 1 alert | `status=critical_high`, `is_critical=true`, 1 critical alert | **PASS** |
| **TC-G2-04** | FPG 3.05 mmol/L (Critical Low + Unit Conv) | `status=critical_low`, converted threshold alert ($< 55\text{ mg/dL}$) | `status=critical_low`, `is_critical=true`, 1 critical alert | **PASS** |
| **TC-G2-05** | Generic Glucose 5.2 mmol/L (Fail-Closed) | `status=unknown`, null bounds, no alerts | `status=unknown`, `reference_low=null`, `reference_high=null` | **PASS** |

```
PRIMARY_MANUAL_E2E=5/5 PASS
SUPPLEMENTAL_WBC=PASS
```

**5/5 Primary Manual E2E cases PASS.**

> [!NOTE]
> **Evaluation Scope & Limitation Statement**:
> These 5 cases demonstrate selected end-to-end MVP behaviors. They do not establish correctness for every possible analyte, report, OCR condition, medical context, or production workload.
