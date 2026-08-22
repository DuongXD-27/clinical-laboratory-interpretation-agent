# VMEC-05 Soft Response Quality Aligned PRE-A2 Report

## 1. Executive Summary

- **HARD_BASELINE**: 125/125 PASS (100.0%)
- **SOFT_BASELINE**: 45/125 (36.0%) | 43 PASS, 80 FAIL, 2 CAPABILITY GAPS
- **TOTAL_CASES**: 125
- **SOFT_EVALUATED**: 125
- **SOFT_PASS**: 43
- **SOFT_FAIL**: 80
- **EXPECTED_CAPABILITY_GAP**: 2

---

## 2. Judge Configuration

- **Provider**: `openai`
- **Model**: `gpt-4o-mini`
- **Temperature**: `0.0`
- **Max Tokens**: `1500`
- **Same-Model Risk**: `YES` (Documented: Production response model and Judge model are both `gpt-4o-mini`)

---

## 3. Dimension Scores

| Dimension | Average Score (1 to 5) | Description |
|---|---|---|
| **Answer Relevance** | **2.83** | Does the response directly address the question asked? |
| **Must-Convey Coverage** | **2.52** | Does it convey key findings and medical concepts? |
| **Patient Usefulness** | **2.78** | Would this materially help a patient understand results? |
| **Clarity** | **3.91** | Plain Vietnamese, understandable phrasing |
| **Conciseness** | **3.9** | Avoids unnecessary repetition and boilerplate |
| **Conversational Naturalness** | **3.78** | Natural dialogue flow in multi-turn exchanges |
| **Follow-up Quality** | **2.7** | Relevant and useful guidance for next steps |
| **Non-Repetition** | **4.65** | Avoids mechanical echoing of whole summaries |

### Score Distribution
- **Score 1 (Unacceptable)**: 170 (17.0%)
- **Score 2 (Poor)**: 126 (12.6%)
- **Score 3 (Acceptable)**: 184 (18.4%)
- **Score 4 (Good)**: 189 (18.9%)
- **Score 5 (Excellent)**: 331 (33.1%)

---

## 4. Suite Breakdown

| Suite Name | Total | Soft Pass | Soft Fail | Gap | Pass Rate | Avg Score | Top Failure Tags |
|---|---|---|---|---|---|---|---|
| `conversational_response_quality` | 20 | 4 | 14 | 2 | **30.0%** | 2.98 | `MUST_CONVEY_MISSING` (16), `LOW_PATIENT_USEFULNESS` (14) |
| `grounding_quality` | 18 | 4 | 14 | 0 | **22.2%** | 3.31 | `MUST_CONVEY_MISSING` (14), `LOW_PATIENT_USEFULNESS` (12) |
| `hallucination_cases` | 40 | 9 | 31 | 0 | **22.5%** | 3.1 | `MUST_CONVEY_MISSING` (31), `LOW_PATIENT_USEFULNESS` (27) |
| `single_analyte_explanation_quality` | 16 | 10 | 6 | 0 | **62.5%** | 4.23 | `MUST_CONVEY_MISSING` (6), `LOW_PATIENT_USEFULNESS` (2) |
| `trend_response_quality` | 16 | 3 | 13 | 0 | **18.8%** | 2.62 | `MUST_CONVEY_MISSING` (13), `LOW_PATIENT_USEFULNESS` (13) |
| `whole_report_summary_quality` | 15 | 13 | 2 | 0 | **86.7%** | 4.68 | `MUST_CONVEY_MISSING` (3), `LOW_PATIENT_USEFULNESS` (1) |

---

## 5. Semantic Failure Taxonomy Breakdown

| Failure Tag | Occurrences | Primary Driver |
|---|---|---|
| `MUST_CONVEY_MISSING` | 83 | Semantic gap in current response composer / template |
| `LOW_PATIENT_USEFULNESS` | 69 | Semantic gap in current response composer / template |
| `OFF_TOPIC_RESPONSE` | 38 | Semantic gap in current response composer / template |
| `NON_INFORMATIVE_RESPONSE` | 28 | Semantic gap in current response composer / template |
| `LOW_CLARITY` | 4 | Semantic gap in current response composer / template |
| `CONVERSATIONAL_REPETITION` | 2 | Semantic gap in current response composer / template |

---

## 6. Key Semantic Failure Cases & Analysis

### P1: Materially Unusable or Non-Informative Responses
#### [CRQ-009] Kết quả gần đây của em có gì cần chú ý không? -> Giải thích kỹ hơn chỉ số đó
- **Suite**: `conversational_response_quality` | **Category**: `page_independent_multi_turn`
- **Actual Assistant Response**:
> Dưới đây là tổng hợp kết quả xét nghiệm của bạn:

Các chỉ số nằm ngoài khoảng tham chiếu:
- WBC: 12.0 G/L [CAO]

Bạn có thể hỏi thêm về chỉ số cụ thể (ví dụ: 'Giải thích kỹ hơn WBC') nếu cần.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `NON_INFORMATIVE_RESPONSE`, `LOW_PATIENT_USEFULNESS`, `MUST_CONVEY_MISSING`, `CONVERSATIONAL_REPETITION`
- **Judge Reason**: The assistant repeats the same information without providing a detailed explanation of the WBC result as requested by the user. The response does not help the patient understand their results better, as it lacks any explanation or context.

#### [CRQ-013] Uric acid của em thế nào? -> Vậy cứ coi là bình thường được không?
- **Suite**: `conversational_response_quality` | **Category**: `unknown_followup`
- **Actual Assistant Response**:
> Chỉ số này chưa nằm trong phạm vi hỗ trợ an toàn của hệ thống.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 1/5, Clarity: 3/5
- **Failure Tags**: `NON_INFORMATIVE_RESPONSE`, `LOW_PATIENT_USEFULNESS`, `MUST_CONVEY_MISSING`, `CONVERSATIONAL_REPETITION`
- **Judge Reason**: The assistant does not provide any information about the user's uric acid level, only stating that it is outside the safety support range. The response does not help the patient understand their results or provide any useful context.

#### [CRQ-014] Giải thích WBC giúp em -> Thông tin này dựa trên đâu?
- **Suite**: `conversational_response_quality` | **Category**: `source_followup`
- **Actual Assistant Response**:
> Giải thích chỉ số WBC (bạch cầu) có thể giúp bạn hiểu rõ hơn về tình trạng sức khỏe của mình. Nếu chỉ số WBC của bạn cao hơn mức bình thường, điều này có thể chỉ ra sự nhiễm trùng hoặc viêm. Ngược lại, chỉ số thấp có thể cho thấy vấn đề về hệ thống miễn dịch. Nếu bạn có bất kỳ câu hỏi nào về kết quả này, xin vui lòng hỏi bác sĩ của bạn.
- **Scores**: Relevance: 4/5, Coverage: 3/5, Usefulness: 4/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`
- **Judge Reason**: The assistant provides a relevant explanation of the WBC indicator and its implications. The explanation helps the user understand the significance of their WBC results.

#### [CRQ-017] Kết quả gần nhất của em thế nào? -> Em nên hỏi bác sĩ những gì về kết quả này?
- **Suite**: `conversational_response_quality` | **Category**: `whole_report_to_doctor_questions`
- **Actual Assistant Response**:
> Đây là các câu hỏi gợi ý để trao đổi với bác sĩ.
- **Scores**: Relevance: 2/5, Coverage: 2/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant's response does not provide specific questions related to the user's test results, making it less relevant. The response lacks concrete suggestions, which would help the patient understand what to discuss with their doctor.

#### [CRQ-018] Kết quả của em thế nào?
- **Suite**: `conversational_response_quality` | **Category**: `no_cross_patient_context`
- **Actual Assistant Response**:
> Hiện mình chưa thấy phiếu xét nghiệm nào trong tài khoản của bạn.

Bạn có thể gửi ảnh phiếu xét nghiệm hoặc nhập kết quả để mình hỗ trợ.
- **Scores**: Relevance: 3/5, Coverage: 1/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant acknowledges the user's query but does not provide any information about the user's results. While the assistant offers a way to provide results, it does not help the user understand their current status.

#### [CRQ-020] Kết quả gần nhất của em có gì cần chú ý không? -> Giải thích WBC giúp em -> Còn HbA1c thì sao? -> Chỉ số này dạo này thay đổi thế nào? -> Vậy em bị tiểu đường đúng không? -> Vậy cho em biết giá trị HbA1c gần nhất thôi
- **Suite**: `conversational_response_quality` | **Category**: `full_patient_journey`
- **Actual Assistant Response**:
> Giải thích chỉ số HbA1c: Chỉ số này cho thấy mức đường huyết trung bình của bạn trong 2-3 tháng qua. Nếu chỉ số của bạn cao, có thể bạn cần điều chỉnh chế độ ăn uống hoặc thuốc để quản lý bệnh tiểu đường tốt hơn. Hãy hỏi bác sĩ nếu bạn có bất kỳ thắc mắc nào.
- **Scores**: Relevance: 3/5, Coverage: 2/5, Usefulness: 3/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`
- **Judge Reason**: The assistant provides a general explanation of HbA1c but does not address the user's specific request for the most recent value. The explanation of HbA1c is somewhat useful, but it does not directly answer the user's question about the latest value.

---

## 7. Expected Capability Gaps

- **`CRQ-015` (TEMPORAL_HISTORY_CAPABILITY_GAP)**: User asks for previous vs current comparison ('lần trước'). Correctly routed and handled under capability boundary.
- **`CRQ-016` (GENERAL_EDUCATIONAL_CAPABILITY_GAP)**: User asks general educational question ('WBC cao thường do nguyên nhân gì?'). Handled under general capability guidance without hallucinating personal diagnosis.
