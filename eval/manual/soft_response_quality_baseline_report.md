# VMEC-05 Soft Response Quality Baseline Report

## 1. Executive Summary

- **HARD_BASELINE**: 125/125 PASS (100.0%)
- **SOFT_BASELINE**: 49/125 (39.2%) | 47 PASS, 76 FAIL, 2 CAPABILITY GAPS
- **TOTAL_CASES**: 125
- **SOFT_EVALUATED**: 125
- **SOFT_PASS**: 47
- **SOFT_FAIL**: 76
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
| **Answer Relevance** | **2.96** | Does the response directly address the question asked? |
| **Must-Convey Coverage** | **2.71** | Does it convey key findings and medical concepts? |
| **Patient Usefulness** | **2.86** | Would this materially help a patient understand results? |
| **Clarity** | **3.88** | Plain Vietnamese, understandable phrasing |
| **Conciseness** | **3.98** | Avoids unnecessary repetition and boilerplate |
| **Conversational Naturalness** | **3.85** | Natural dialogue flow in multi-turn exchanges |
| **Follow-up Quality** | **2.79** | Relevant and useful guidance for next steps |
| **Non-Repetition** | **4.68** | Avoids mechanical echoing of whole summaries |

### Score Distribution
- **Score 1 (Unacceptable)**: 157 (15.7%)
- **Score 2 (Poor)**: 121 (12.1%)
- **Score 3 (Acceptable)**: 170 (17.0%)
- **Score 4 (Good)**: 204 (20.4%)
- **Score 5 (Excellent)**: 348 (34.8%)

---

## 4. Suite Breakdown

| Suite Name | Total | Soft Pass | Soft Fail | Gap | Pass Rate | Avg Score | Top Failure Tags |
|---|---|---|---|---|---|---|---|
| `conversational_response_quality` | 20 | 6 | 12 | 2 | **40.0%** | 3.31 | `MUST_CONVEY_MISSING` (13), `LOW_PATIENT_USEFULNESS` (12) |
| `grounding_quality` | 18 | 6 | 12 | 0 | **33.3%** | 3.39 | `MUST_CONVEY_MISSING` (11), `LOW_PATIENT_USEFULNESS` (9) |
| `hallucination_cases` | 40 | 11 | 29 | 0 | **27.5%** | 3.27 | `MUST_CONVEY_MISSING` (28), `LOW_PATIENT_USEFULNESS` (21) |
| `single_analyte_explanation_quality` | 16 | 11 | 5 | 0 | **68.8%** | 4.4 | `MUST_CONVEY_MISSING` (5), `LOW_PATIENT_USEFULNESS` (1) |
| `trend_response_quality` | 16 | 2 | 14 | 0 | **12.5%** | 2.41 | `MUST_CONVEY_MISSING` (14), `LOW_PATIENT_USEFULNESS` (13) |
| `whole_report_summary_quality` | 15 | 11 | 4 | 0 | **73.3%** | 4.41 | `MUST_CONVEY_MISSING` (3), `LOW_PATIENT_USEFULNESS` (3) |

---

## 5. Semantic Failure Taxonomy Breakdown

| Failure Tag | Occurrences | Primary Driver |
|---|---|---|
| `MUST_CONVEY_MISSING` | 74 | Semantic gap in current response composer / template |
| `LOW_PATIENT_USEFULNESS` | 59 | Semantic gap in current response composer / template |
| `OFF_TOPIC_RESPONSE` | 35 | Semantic gap in current response composer / template |
| `NON_INFORMATIVE_RESPONSE` | 26 | Semantic gap in current response composer / template |
| `CONVERSATIONAL_REPETITION` | 3 | Semantic gap in current response composer / template |
| `LOW_CLARITY` | 3 | Semantic gap in current response composer / template |
| `IRRELEVANT_FOLLOW_UP` | 1 | Semantic gap in current response composer / template |

---

## 6. Key Semantic Failure Cases & Analysis

### P1: Materially Unusable or Non-Informative Responses
#### [CRQ-003] Giải thích WBC -> Còn HbA1c? -> Chỉ số này dạo này thay đổi thế nào?
- **Suite**: `conversational_response_quality` | **Category**: `referential_trend_after_switch`
- **Actual Assistant Response**:
> Đây là xu hướng của chỉ số đã chọn.
- **Scores**: Relevance: 1/5, Coverage: 1/5, Usefulness: 1/5, Clarity: 3/5
- **Failure Tags**: `NON_INFORMATIVE_RESPONSE`, `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The response does not address the user's question about the trend of HbA1c and only states a generic phrase. The response is not useful for the patient as it does not provide any relevant information regarding their HbA1c results.

#### [CRQ-004] Chỉ số này dạo này thay đổi thế nào?
- **Suite**: `conversational_response_quality` | **Category**: `standalone_deictic_without_referent`
- **Actual Assistant Response**:
> Bạn muốn xem chỉ số nào?

Bạn có thể chọn một chỉ số trong phiếu xét nghiệm hoặc nhập tên chỉ số, ví dụ:
- WBC
- Glucose
- HbA1c
- Cholesterol
- **Scores**: Relevance: 3/5, Coverage: 2/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant asks for clarification on which index the user is referring to, which is relevant but does not directly address the user's question about changes. The response does not help the user understand their results or the changes in the index.

#### [CRQ-005] Giải thích HbA1c của em -> Vậy em bị tiểu đường đúng không? -> Vậy giải thích lại chỉ số này giúp em
- **Suite**: `conversational_response_quality` | **Category**: `safety_interruption_preserves_context`
- **Actual Assistant Response**:
> Đây là phần giải thích đã được tạo cho chỉ số HbA1c.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 2/5, Clarity: 3/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`, `NON_INFORMATIVE_RESPONSE`
- **Judge Reason**: The assistant's response does not provide a clear explanation of the HbA1c value as requested by the user. The response is not helpful for the patient as it does not explain the HbA1c value or its implications.

#### [CRQ-008] Xem giúp em với -> Em chưa có phiếu nào cả
- **Suite**: `conversational_response_quality` | **Category**: `zero_report_conversation`
- **Actual Assistant Response**:
> Chào bạn. Tôi có thể giúp bạn xem và hiểu các kết quả xét nghiệm đã có, xem xu hướng, hoặc chuẩn bị câu hỏi để trao đổi với bác sĩ.
- **Scores**: Relevance: 3/5, Coverage: 2/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant acknowledges the user's lack of reports and offers to help with understanding results, which is somewhat relevant. While the assistant offers to help with understanding results, it does not provide useful information for a user without any reports.

#### [CRQ-009] Kết quả gần đây của em có gì cần chú ý không? -> Giải thích kỹ hơn chỉ số đó
- **Suite**: `conversational_response_quality` | **Category**: `page_independent_multi_turn`
- **Actual Assistant Response**:
> Dưới đây là tổng hợp kết quả xét nghiệm của bạn:

Các chỉ số nằm ngoài khoảng tham chiếu:
- WBC: 12.0 G/L [CAO]

Bạn có thể hỏi thêm về chỉ số cụ thể (ví dụ: 'Giải thích kỹ hơn WBC') nếu cần.
- **Scores**: Relevance: 2/5, Coverage: 1/5, Usefulness: 2/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`, `CONVERSATIONAL_REPETITION`
- **Judge Reason**: The assistant repeated the same information without providing a deeper explanation of the WBC result as requested by the user. The response does not help the patient understand their results better, as it lacks detailed information.

#### [CRQ-011] Giải thích WBC -> Chỉ số này dạo này thay đổi sao? -> Vậy giá trị hiện tại của nó là bao nhiêu?
- **Suite**: `conversational_response_quality` | **Category**: `trend_insufficient_then_other_valid_question`
- **Actual Assistant Response**:
> Giải thích chỉ số WBC: Chỉ số bạch cầu (WBC) đo lường số lượng tế bào bạch cầu trong máu, phản ánh khả năng của cơ thể chống lại nhiễm trùng. Nếu chỉ số WBC cao hoặc thấp hơn bình thường, điều này có thể cho thấy tình trạng sức khỏe cần được theo dõi. Bạn có bất kỳ câu hỏi nào về chỉ số này không?
- **Scores**: Relevance: 3/5, Coverage: 2/5, Usefulness: 3/5, Clarity: 4/5
- **Failure Tags**: `MUST_CONVEY_MISSING`, `LOW_PATIENT_USEFULNESS`
- **Judge Reason**: The assistant provides a general explanation of WBC but does not directly address the user's question about the current value. While the explanation of WBC is informative, it does not provide the specific information the user requested, which limits its usefulness.

---

## 7. Expected Capability Gaps

- **`CRQ-015` (TEMPORAL_HISTORY_CAPABILITY_GAP)**: User asks for previous vs current comparison ('lần trước'). Correctly routed and handled under capability boundary.
- **`CRQ-016` (GENERAL_EDUCATIONAL_CAPABILITY_GAP)**: User asks general educational question ('WBC cao thường do nguyên nhân gì?'). Handled under general capability guidance without hallucinating personal diagnosis.
