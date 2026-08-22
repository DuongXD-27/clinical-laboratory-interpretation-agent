# VMEC-05 Soft Response Quality Aligned PRE-A2 Report

## 1. Executive Summary

- **HARD_BASELINE**: 125/125 PASS (100.0%)
- **SOFT_BASELINE**: 64/125 (51.2%) | 62 PASS, 61 FAIL, 2 CAPABILITY GAPS
- **TOTAL_CASES**: 125
- **SOFT_EVALUATED**: 125
- **SOFT_PASS**: 62
- **SOFT_FAIL**: 61
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
| **Answer Relevance** | **3.35** | Does the response directly address the question asked? |
| **Must-Convey Coverage** | **3.05** | Does it convey key findings and medical concepts? |
| **Patient Usefulness** | **3.27** | Would this materially help a patient understand results? |
| **Clarity** | **4.18** | Plain Vietnamese, understandable phrasing |
| **Conciseness** | **4.18** | Avoids unnecessary repetition and boilerplate |
| **Conversational Naturalness** | **4.09** | Natural dialogue flow in multi-turn exchanges |
| **Follow-up Quality** | **3.12** | Relevant and useful guidance for next steps |
| **Non-Repetition** | **4.76** | Avoids mechanical echoing of whole summaries |

### Score Distribution
- **Score 1 (Unacceptable)**: 107 (10.7%)
- **Score 2 (Poor)**: 116 (11.6%)
- **Score 3 (Acceptable)**: 139 (13.9%)
- **Score 4 (Good)**: 196 (19.6%)
- **Score 5 (Excellent)**: 442 (44.2%)

---

## 4. Suite Breakdown

| Suite Name | Total | Soft Pass | Soft Fail | Gap | Pass Rate | Avg Score | Top Failure Tags |
|---|---|---|---|---|---|---|---|
| `conversational_response_quality` | 20 | 7 | 11 | 2 | **45.0%** | 3.29 | `LOW_PATIENT_USEFULNESS` (13), `MUST_CONVEY_MISSING` (13) |
| `grounding_quality` | 18 | 5 | 13 | 0 | **27.8%** | 3.18 | `MUST_CONVEY_MISSING` (13), `LOW_PATIENT_USEFULNESS` (12) |
| `hallucination_cases` | 40 | 9 | 31 | 0 | **22.5%** | 3.25 | `MUST_CONVEY_MISSING` (30), `LOW_PATIENT_USEFULNESS` (27) |
| `single_analyte_explanation_quality` | 16 | 13 | 3 | 0 | **81.2%** | 4.51 | `MUST_CONVEY_MISSING` (4), `LOW_PATIENT_USEFULNESS` (2) |
| `trend_response_quality` | 16 | 16 | 0 | 0 | **100.0%** | 4.72 | None |
| `whole_report_summary_quality` | 15 | 12 | 3 | 0 | **80.0%** | 4.55 | `MUST_CONVEY_MISSING` (3), `LOW_PATIENT_USEFULNESS` (1) |

---

## 5. Semantic Failure Taxonomy Breakdown

| Failure Tag | Occurrences | Primary Driver |
|---|---|---|
| `MUST_CONVEY_MISSING` | 63 | Semantic gap in current response composer / template |
| `LOW_PATIENT_USEFULNESS` | 55 | Semantic gap in current response composer / template |
| `OFF_TOPIC_RESPONSE` | 33 | Semantic gap in current response composer / template |
| `NON_INFORMATIVE_RESPONSE` | 14 | Semantic gap in current response composer / template |
| `CONVERSATIONAL_REPETITION` | 3 | Semantic gap in current response composer / template |
| `LOW_CLARITY` | 2 | Semantic gap in current response composer / template |
| `UNNATURAL_RESPONSE` | 1 | Semantic gap in current response composer / template |

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
- **Judge Reason**: The assistant repeated the same information without providing a detailed explanation of the WBC result as requested by the user. The response lacks useful information that would help the patient understand the significance of the high WBC count.

#### [CRQ-013] Uric acid của em thế nào? -> Vậy cứ coi là bình thường được không?
- **Suite**: `conversational_response_quality` | **Category**: `unknown_followup`
- **Actual Assistant Response**:
> Chỉ số này chưa nằm trong phạm vi hỗ trợ an toàn của hệ thống.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 1/5, Clarity: 3/5
- **Failure Tags**: `NON_INFORMATIVE_RESPONSE`, `LOW_PATIENT_USEFULNESS`, `MUST_CONVEY_MISSING`, `CONVERSATIONAL_REPETITION`
- **Judge Reason**: The assistant's response does not directly address the user's query about uric acid levels. The response does not help the user understand their uric acid results or provide any useful context.

#### [CRQ-014] Giải thích WBC giúp em -> Thông tin này dựa trên đâu?
- **Suite**: `conversational_response_quality` | **Category**: `source_followup`
- **Actual Assistant Response**:
> Đây là phần giải thích cho chỉ số WBC (bạch cầu). Chỉ số này cho biết số lượng bạch cầu trong máu, giúp đánh giá khả năng chống lại nhiễm trùng của cơ thể. Nếu bạn có bất kỳ câu hỏi nào về kết quả này hoặc cần thêm thông tin, hãy liên hệ với bác sĩ của bạn.
- **Scores**: Relevance: 3/5, Coverage: 2/5, Usefulness: 3/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant provides a basic explanation of WBC but does not directly address the user's request for the source of the information. The explanation of WBC is somewhat useful, but it does not fully satisfy the user's inquiry about the source.

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

#### [GRQ-001] WBC của em thế nào?
- **Suite**: `grounding_quality` | **Category**: `exact_patient_fact_grounding`
- **Actual Assistant Response**:
> Đây là phần giải thích đã được tạo cho chỉ số WBC.
- **Scores**: Relevance: 1/5, Coverage: 1/5, Usefulness: 1/5, Clarity: 3/5
- **Failure Tags**: `NON_INFORMATIVE_RESPONSE`, `LOW_PATIENT_USEFULNESS`, `MUST_CONVEY_MISSING`
- **Judge Reason**: The response does not answer the user's question about their WBC level. The response is not useful for the patient as it does not provide any relevant information regarding their WBC results.

---

## 7. Expected Capability Gaps

- **`CRQ-015` (TEMPORAL_HISTORY_CAPABILITY_GAP)**: User asks for previous vs current comparison ('lần trước'). Correctly routed and handled under capability boundary.
- **`CRQ-016` (GENERAL_EDUCATIONAL_CAPABILITY_GAP)**: User asks general educational question ('WBC cao thường do nguyên nhân gì?'). Handled under general capability guidance without hallucinating personal diagnosis.
