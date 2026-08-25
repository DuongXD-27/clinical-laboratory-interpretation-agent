"""Routing precedence audit for APP_HELP reconciliation (APP-HELP-RAG final check).

Runs the 12 mandated probes through the REAL deterministic router
(``_deterministic_route``) on the reconciled branch and prints
INPUT / ACTUAL_INTENT / EXPECTED_INTENT / PASS-FAIL per case.

Medical semantic questions must stay on medical/current-result intents;
explicit app navigation questions must route to APP_HELP; neither side may
steal from the other. Cases whose deterministic router returns None fall
through to the LLM fallback in production (recorded as LLM_FALLBACK).
"""

from __future__ import annotations

from src.models.orchestrator_schemas import IntentEnum
from src.orchestrator.intent_router import _deterministic_route

# (input, expected_intent)
PROBES = [
    # --- medical semantic questions must remain medical/current-result ---
    ("WBC là gì?", IntentEnum.EXPLAIN_CURRENT_RESULT),
    ("WBC có cao không?", IntentEnum.EXPLAIN_CURRENT_RESULT),
    ("Giải thích WBC của tôi", IntentEnum.EXPLAIN_CURRENT_RESULT),
    ("Nguồn của ngưỡng này?", None),  # provenance follow-up handled upstream of routing
    ("Tôi nên làm gì để cải thiện chỉ số này?", None),  # treatment-safety gate upstream of routing
    ("Hỏi gì bác sĩ về WBC?", IntentEnum.GET_DOCTOR_QUESTIONS),
    # --- explicit HOW-TO-USE-APP questions must route APP_HELP ---
    ("Làm thế nào để tải ảnh phiếu?", IntentEnum.APP_HELP),
    ("Tải phiếu ở đâu?", IntentEnum.APP_HELP),
    ("Câu hỏi cho bác sĩ ở đâu?", IntentEnum.APP_HELP),
    ("Cảnh báo khẩn cấp nghĩa là gì?", IntentEnum.APP_HELP),
    ("Xem lịch sử kết quả ở đâu?", IntentEnum.APP_HELP),
    ("Xem xu hướng HbA1c như thế nào?", IntentEnum.APP_HELP),
]


def main() -> int:
    failures = 0
    print(f"{'INPUT':<45} {'ACTUAL':<24} {'EXPECTED':<24} RESULT")
    print("-" * 105)
    for message, expected in PROBES:
        route = _deterministic_route(message)
        actual = route.intent if route is not None else None
        label = actual.value if actual is not None else "LLM_FALLBACK"
        expected_label = expected.value if expected is not None else "NON-APP_HELP (gated upstream)"
        ok = actual == expected if expected is not None else actual != IntentEnum.APP_HELP
        if not ok:
            failures += 1
        status = "PASS" if ok else "FAIL"
        print(f"{message:<45} {label:<24} {expected_label:<24} {status}")
    print("-" * 105)
    print(f"TOTAL={len(PROBES)} PASS={len(PROBES) - failures} FAIL={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
