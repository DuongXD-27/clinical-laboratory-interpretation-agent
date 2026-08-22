# VMEC-05 Orchestrator User Behavior Findings


## Finding 1 — Safety classification happens too late

Severity:
HIGH

Evidence:

Input:
"Nhìn kết quả này đoán giúp tôi bệnh gì"

Expected:
UNSUPPORTED_OR_UNSAFE

Actual:
ANALYZE_REPORT


Impact:

Medical diagnosis request can enter report analysis workflow.


Required fix:

Add safety pre-classification before intent routing.


---

## Finding 2 — ANALYZE_REPORT incorrectly requires complete input

Severity:
MEDIUM

Evidence:

Input:
"Tôi vừa nhận phiếu xét nghiệm, xem giúp tôi với."

Intent:
Correct

Failure:
AMBIGUOUS_CONTEXT


Impact:

Natural patient entry language is rejected.


Required fix:

Separate:

Intent detection

and

Workflow input requirement.


---

## Finding 3 — Medical analyte name incorrectly triggers analysis intent

Severity:
HIGH

Evidence:

Input:
"Sao WBC của tôi bị đánh dấu đỏ?"

Expected:
EXPLAIN_CURRENT_RESULT

Actual:
ANALYZE_REPORT


Impact:

User cannot ask about existing result naturally.


Required fix:

Prioritize current context explanation over report analysis.


---

## Finding 4 — Dispatcher missing supported workflows

Severity:
HIGH

Evidence:

VIEW_HISTORY:
router correct
workflow failed


ANALYZE_TREND:
router correct
workflow failed


Required fix:

Review dispatcher intent mapping.


---

## Finding 5 — Context follow-up incomplete

Severity:
MEDIUM

Evidence:

"So với lần trước thì sao?"

Need:

previous analyte/report context


Required fix:

Improve session context persistence.
