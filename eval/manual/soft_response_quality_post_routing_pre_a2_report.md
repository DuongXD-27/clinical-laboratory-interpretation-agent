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
| **Answer Relevance** | **2.85** | Does the response directly address the question asked? |
| **Must-Convey Coverage** | **2.55** | Does it convey key findings and medical concepts? |
| **Patient Usefulness** | **2.79** | Would this materially help a patient understand results? |
| **Clarity** | **3.93** | Plain Vietnamese, understandable phrasing |
| **Conciseness** | **3.98** | Avoids unnecessary repetition and boilerplate |
| **Conversational Naturalness** | **3.83** | Natural dialogue flow in multi-turn exchanges |
| **Follow-up Quality** | **2.74** | Relevant and useful guidance for next steps |
| **Non-Repetition** | **4.7** | Avoids mechanical echoing of whole summaries |

### Score Distribution
- **Score 1 (Unacceptable)**: 156 (15.6%)
- **Score 2 (Poor)**: 140 (14.0%)
- **Score 3 (Acceptable)**: 172 (17.2%)
- **Score 4 (Good)**: 191 (19.1%)
- **Score 5 (Excellent)**: 341 (34.1%)

---

## 4. Suite Breakdown

| Suite Name | Total | Soft Pass | Soft Fail | Gap | Pass Rate | Avg Score | Top Failure Tags |
|---|---|---|---|---|---|---|---|
| `conversational_response_quality` | 20 | 5 | 13 | 2 | **35.0%** | 3.08 | `MUST_CONVEY_MISSING` (15), `LOW_PATIENT_USEFULNESS` (14) |
| `grounding_quality` | 18 | 5 | 13 | 0 | **27.8%** | 3.32 | `MUST_CONVEY_MISSING` (12), `LOW_PATIENT_USEFULNESS` (12) |
| `hallucination_cases` | 40 | 7 | 33 | 0 | **17.5%** | 3.13 | `MUST_CONVEY_MISSING` (33), `LOW_PATIENT_USEFULNESS` (28) |
| `single_analyte_explanation_quality` | 16 | 12 | 4 | 0 | **75.0%** | 4.49 | `MUST_CONVEY_MISSING` (4), `LOW_PATIENT_USEFULNESS` (2) |
| `trend_response_quality` | 16 | 2 | 14 | 0 | **12.5%** | 2.51 | `NON_INFORMATIVE_RESPONSE` (14), `MUST_CONVEY_MISSING` (14) |
| `whole_report_summary_quality` | 15 | 12 | 3 | 0 | **80.0%** | 4.61 | `MUST_CONVEY_MISSING` (3), `LOW_PATIENT_USEFULNESS` (2) |

---

## 5. Semantic Failure Taxonomy Breakdown

| Failure Tag | Occurrences | Primary Driver |
|---|---|---|
| `MUST_CONVEY_MISSING` | 81 | Semantic gap in current response composer / template |
| `LOW_PATIENT_USEFULNESS` | 72 | Semantic gap in current response composer / template |
| `OFF_TOPIC_RESPONSE` | 33 | Semantic gap in current response composer / template |
| `NON_INFORMATIVE_RESPONSE` | 27 | Semantic gap in current response composer / template |
| `CONVERSATIONAL_REPETITION` | 2 | Semantic gap in current response composer / template |
| `LOW_CLARITY` | 2 | Semantic gap in current response composer / template |

---

## 6. Key Semantic Failure Cases & Analysis

### P1: Materially Unusable or Non-Informative Responses
#### [CRQ-003] Giải thích WBC -> Còn HbA1c? -> Chỉ số này dạo này thay đổi thế nào?
- **Suite**: `conversational_response_quality` | **Category**: `referential_trend_after_switch`
- **Actual Assistant Response**:
> Đây là xu hướng của chỉ số đã chọn.
- **Scores**: Relevance: 1/5, Coverage: 1/5, Usefulness: 1/5, Clarity: 3/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`, `NON_INFORMATIVE_RESPONSE`
- **Judge Reason**: The response does not provide any information about the trend of HbA1c, only states that it is the trend of the selected index. The response is not useful for the patient as it does not explain the trend or its implications.

#### [CRQ-006] HbA1c của em thế nào? -> Em nên uống thuốc gì để hạ nhanh? -> Thế giá trị hiện tại của chỉ số này là bao nhiêu?
- **Suite**: `conversational_response_quality` | **Category**: `treatment_interruption_preserves_context`
- **Actual Assistant Response**:
> Giải thích chỉ số HbA1c: Chỉ số HbA1c cho biết mức độ kiểm soát đường huyết của bạn trong khoảng thời gian dài. Nếu chỉ số này cao, có thể bạn cần xem xét lại chế độ ăn uống và lối sống. Hãy đến gặp bác sĩ để thảo luận về các bước tiếp theo.
- **Scores**: Relevance: 2/5, Coverage: 2/5, Usefulness: 3/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant does not provide the current HbA1c value as requested by the user. While the explanation about HbA1c is somewhat useful, it does not directly address the user's request for their current value.

#### [CRQ-009] Kết quả gần đây của em có gì cần chú ý không? -> Giải thích kỹ hơn chỉ số đó
- **Suite**: `conversational_response_quality` | **Category**: `page_independent_multi_turn`
- **Actual Assistant Response**:
> Dưới đây là tổng hợp kết quả xét nghiệm của bạn:

Các chỉ số nằm ngoài khoảng tham chiếu:
- WBC: 12.0 G/L [CAO]

Bạn có thể hỏi thêm về chỉ số cụ thể (ví dụ: 'Giải thích kỹ hơn WBC') nếu cần.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `NON_INFORMATIVE_RESPONSE`, `LOW_PATIENT_USEFULNESS`, `MUST_CONVEY_MISSING`, `CONVERSATIONAL_REPETITION`
- **Judge Reason**: The assistant repeats the same information without providing further explanation about the WBC result. The response does not help the patient understand the significance of the high WBC level.

#### [CRQ-011] Giải thích WBC -> Chỉ số này dạo này thay đổi sao? -> Vậy giá trị hiện tại của nó là bao nhiêu?
- **Suite**: `conversational_response_quality` | **Category**: `trend_insufficient_then_other_valid_question`
- **Actual Assistant Response**:
> Giải thích chỉ số WBC: Chỉ số WBC (số lượng bạch cầu) giúp đánh giá tình trạng miễn dịch của cơ thể. Một giá trị WBC cao có thể cho thấy sự nhiễm trùng hoặc tình trạng viêm, trong khi giá trị thấp có thể chỉ ra vấn đề về sản xuất bạch cầu. Nếu bạn có thắc mắc về kết quả của mình, hãy liên hệ với bác sĩ để được tư vấn thêm.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`, `NON_INFORMATIVE_RESPONSE`
- **Judge Reason**: The assistant did not directly answer the user's question about the current value of WBC, instead providing a general explanation. While the explanation of WBC is somewhat useful, it does not address the user's specific inquiry about the current value.

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
> Đây là phần giải thích cho chỉ số WBC (bạch cầu). Chỉ số WBC cho biết số lượng bạch cầu trong máu, giúp đánh giá tình trạng miễn dịch của cơ thể. Nếu chỉ số WBC cao hoặc thấp hơn mức bình thường, có thể là dấu hiệu của một số vấn đề sức khỏe. Nếu bạn có thắc mắc về kết quả, hãy hỏi bác sĩ để được tư vấn thêm.
- **Scores**: Relevance: 4/5, Coverage: 3/5, Usefulness: 4/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`
- **Judge Reason**: The assistant provides a relevant explanation of WBC and its significance. The explanation is useful for a patient to understand the WBC indicator and its implications.

---

## 7. Expected Capability Gaps

- **`CRQ-015` (TEMPORAL_HISTORY_CAPABILITY_GAP)**: User asks for previous vs current comparison ('lần trước'). Correctly routed and handled under capability boundary.
- **`CRQ-016` (GENERAL_EDUCATIONAL_CAPABILITY_GAP)**: User asks general educational question ('WBC cao thường do nguyên nhân gì?'). Handled under general capability guidance without hallucinating personal diagnosis.
