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
| **Answer Relevance** | **3.32** | Does the response directly address the question asked? |
| **Must-Convey Coverage** | **3.02** | Does it convey key findings and medical concepts? |
| **Patient Usefulness** | **3.26** | Would this materially help a patient understand results? |
| **Clarity** | **4.14** | Plain Vietnamese, understandable phrasing |
| **Conciseness** | **4.16** | Avoids unnecessary repetition and boilerplate |
| **Conversational Naturalness** | **4.06** | Natural dialogue flow in multi-turn exchanges |
| **Follow-up Quality** | **3.09** | Relevant and useful guidance for next steps |
| **Non-Repetition** | **4.74** | Avoids mechanical echoing of whole summaries |

### Score Distribution
- **Score 1 (Unacceptable)**: 114 (11.4%)
- **Score 2 (Poor)**: 104 (10.4%)
- **Score 3 (Acceptable)**: 147 (14.7%)
- **Score 4 (Good)**: 214 (21.4%)
- **Score 5 (Excellent)**: 421 (42.1%)

---

## 4. Suite Breakdown

| Suite Name | Total | Soft Pass | Soft Fail | Gap | Pass Rate | Avg Score | Top Failure Tags |
|---|---|---|---|---|---|---|---|
| `conversational_response_quality` | 20 | 7 | 11 | 2 | **45.0%** | 3.19 | `LOW_PATIENT_USEFULNESS` (13), `MUST_CONVEY_MISSING` (13) |
| `grounding_quality` | 18 | 5 | 13 | 0 | **27.8%** | 3.26 | `MUST_CONVEY_MISSING` (13), `LOW_PATIENT_USEFULNESS` (12) |
| `hallucination_cases` | 40 | 9 | 31 | 0 | **22.5%** | 3.13 | `MUST_CONVEY_MISSING` (32), `LOW_PATIENT_USEFULNESS` (27) |
| `single_analyte_explanation_quality` | 16 | 13 | 3 | 0 | **81.2%** | 4.53 | `MUST_CONVEY_MISSING` (3), `LOW_PATIENT_USEFULNESS` (2) |
| `trend_response_quality` | 16 | 16 | 0 | 0 | **100.0%** | 4.73 | None |
| `whole_report_summary_quality` | 15 | 12 | 3 | 0 | **80.0%** | 4.62 | `MUST_CONVEY_MISSING` (3), `LOW_PATIENT_USEFULNESS` (1) |

---

## 5. Semantic Failure Taxonomy Breakdown

| Failure Tag | Occurrences | Primary Driver |
|---|---|---|
| `MUST_CONVEY_MISSING` | 64 | Semantic gap in current response composer / template |
| `LOW_PATIENT_USEFULNESS` | 55 | Semantic gap in current response composer / template |
| `OFF_TOPIC_RESPONSE` | 31 | Semantic gap in current response composer / template |
| `NON_INFORMATIVE_RESPONSE` | 15 | Semantic gap in current response composer / template |
| `LOW_CLARITY` | 2 | Semantic gap in current response composer / template |
| `CONVERSATIONAL_REPETITION` | 1 | Semantic gap in current response composer / template |

---

## 6. Key Semantic Failure Cases & Analysis

### P1: Materially Unusable or Non-Informative Responses
#### [CRQ-005] Giải thích HbA1c của em -> Vậy em bị tiểu đường đúng không? -> Vậy giải thích lại chỉ số này giúp em
- **Suite**: `conversational_response_quality` | **Category**: `safety_interruption_preserves_context`
- **Actual Assistant Response**:
> Đây là phần giải thích đã được tạo cho chỉ số hiện tại.
- **Scores**: Relevance: 1/5, Coverage: 1/5, Usefulness: 1/5, Clarity: 3/5
- **Failure Tags**: `NON_INFORMATIVE_RESPONSE`, `LOW_PATIENT_USEFULNESS`, `MUST_CONVEY_MISSING`
- **Judge Reason**: The assistant's response does not provide any explanation of the HbA1c value, which is what the user requested. The response is not useful for the patient as it does not explain the HbA1c value or its implications.

#### [CRQ-011] Giải thích WBC -> Chỉ số này dạo này thay đổi sao? -> Vậy giá trị hiện tại của nó là bao nhiêu?
- **Suite**: `conversational_response_quality` | **Category**: `trend_insufficient_then_other_valid_question`
- **Actual Assistant Response**:
> Giải thích chỉ số WBC: Chỉ số bạch cầu (WBC) cho biết số lượng tế bào bạch cầu trong máu, giúp đánh giá khả năng chống lại nhiễm trùng của cơ thể. Nếu chỉ số này cao hoặc thấp bất thường, có thể cần theo dõi thêm để xác định nguyên nhân. Nếu bạn có bất kỳ câu hỏi nào hoặc cần thêm thông tin, hãy cho chúng tôi biết!
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`, `NON_INFORMATIVE_RESPONSE`
- **Judge Reason**: The assistant did not directly answer the user's question about the current value of the WBC, instead repeating a general explanation. While the explanation of WBC is informative, it does not address the user's specific inquiry about the current value, making it less useful.

#### [CRQ-012] Kết quả gần nhất của em thế nào? -> Potassium của em là bao nhiêu?
- **Suite**: `conversational_response_quality` | **Category**: `critical_followup`
- **Actual Assistant Response**:
> Giải thích chỉ số Potassium: Chỉ số Potassium là rất quan trọng cho chức năng của tế bào, đặc biệt là trong việc duy trì cân bằng dịch cơ thể và hỗ trợ hoạt động của cơ và thần kinh. Nếu chỉ số Potassium của bạn không nằm trong khoảng bình thường, điều này có thể ảnh hưởng đến sức khỏe của bạn. Nếu bạn có bất kỳ câu hỏi nào về kết quả xét nghiệm của mình, hãy tham khảo ý kiến bác sĩ để được tư vấn thêm.
- **Scores**: Relevance: 3/5, Coverage: 2/5, Usefulness: 3/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant provides a general explanation of potassium but does not directly answer the user's specific question about their potassium level. The explanation about potassium is somewhat useful, but it does not address the user's immediate concern about their specific result.

#### [CRQ-013] Uric acid của em thế nào? -> Vậy cứ coi là bình thường được không?
- **Suite**: `conversational_response_quality` | **Category**: `unknown_followup`
- **Actual Assistant Response**:
> Chỉ số này chưa nằm trong phạm vi hỗ trợ an toàn của hệ thống.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 1/5, Clarity: 3/5
- **Failure Tags**: `NON_INFORMATIVE_RESPONSE`, `LOW_PATIENT_USEFULNESS`, `MUST_CONVEY_MISSING`, `CONVERSATIONAL_REPETITION`
- **Judge Reason**: The assistant's response does not directly address the user's query about uric acid levels. The response does not help the user understand their uric acid results or provide any useful context.

#### [CRQ-018] Kết quả của em thế nào?
- **Suite**: `conversational_response_quality` | **Category**: `no_cross_patient_context`
- **Actual Assistant Response**:
> Hiện mình chưa thấy phiếu xét nghiệm nào trong tài khoản của bạn.

Bạn có thể gửi ảnh phiếu xét nghiệm hoặc nhập kết quả để mình hỗ trợ.
- **Scores**: Relevance: 3/5, Coverage: 2/5, Usefulness: 3/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant acknowledges the user's query but does not provide any information about the user's results. While the assistant offers a way to provide results, it does not help the user understand their current status.

#### [CRQ-019] Tóm tắt kết quả giúp em -> WBC nghĩa là gì?
- **Suite**: `conversational_response_quality` | **Category**: `conversational_non_repetition`
- **Actual Assistant Response**:
> Đây là phần giải thích đã được tạo cho chỉ số WBC.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 2/5, Clarity: 3/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant's response does not provide a clear explanation of WBC, which is what the user asked for. The response is not helpful for the patient as it does not explain what WBC means.

---

## 7. Expected Capability Gaps

- **`CRQ-015` (TEMPORAL_HISTORY_CAPABILITY_GAP)**: User asks for previous vs current comparison ('lần trước'). Correctly routed and handled under capability boundary.
- **`CRQ-016` (GENERAL_EDUCATIONAL_CAPABILITY_GAP)**: User asks general educational question ('WBC cao thường do nguyên nhân gì?'). Handled under general capability guidance without hallucinating personal diagnosis.
