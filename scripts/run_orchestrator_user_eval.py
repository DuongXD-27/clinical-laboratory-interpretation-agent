import json
import os
import sys
import uuid

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from src.main import app


def run_eval():
    client = TestClient(app)
    golden_file = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "../eval/manual/orchestrator_user_behavior/orchestrator_golden_cases.json"
        )
    )
    report_file = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../eval/manual/orchestrator_user_behavior/report_after_fix.md")
    )

    with open(golden_file, encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]

    results = []
    passed = 0
    failed = 0

    # Separated metrics
    intent_matched = 0

    safety_cases = 0
    safety_matched = 0

    workflow_executed = 0

    print(f"Running evaluation against {len(cases)} cases...")
    print("-" * 50)

    for case in cases:
        user_msg = case["user_message"]
        ui_ctx = case.get("context", {})

        # Authenticate as a new PATIENT to isolate sessions
        username = f"eval_user_{uuid.uuid4().hex[:8]}"
        password = "evalpassword"

        # Register
        client.post("/api/v1/auth/register", json={"username": username, "password": password})

        # Login
        login_resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        if login_resp.status_code != 200:
            print(f"Failed to login user {username}")
            continue
        token = login_resp.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Acknowledge onboarding
        client.post("/api/v1/orchestrator/onboarding/acknowledge", headers=headers)

        print(f"Processing case {case['id']}...")
        payload = {"message": user_msg, "ui_context": ui_ctx}

        resp = client.post("/api/v1/orchestrator/message", json=payload, headers=headers)

        actual_intent = None
        actual_reason = None

        if resp.status_code == 200:
            resp_data = resp.json()
            actual_intent = resp_data.get("intent")
            actual_reason = resp_data.get("reason_code")
        else:
            actual_intent = f"HTTP_{resp.status_code}"

        expected_intent = case["expected"].get("intent")
        expected_reason = case["expected"].get("reason_code")

        # 1. Intent Accuracy
        is_intent_match = actual_intent == expected_intent
        if is_intent_match:
            intent_matched += 1

        # 2. Safety Reason Accuracy
        is_safety_case = expected_reason is not None
        is_safety_match = True

        if is_safety_case:
            safety_cases += 1
            is_safety_match = actual_reason == expected_reason
            if is_safety_match:
                safety_matched += 1

        # 3. Workflow Execution Outcome
        # We consider workflow executed if it didn't hit a block (actual_reason is null)
        is_workflow_executed = actual_reason is None
        if is_workflow_executed:
            workflow_executed += 1

        # Overall PASS:
        # If expected_reason is null, we do not fail just because actual_reason has a runtime block.
        if is_safety_case:
            is_pass = is_intent_match and is_safety_match
        else:
            is_pass = is_intent_match

        if is_pass:
            passed += 1
            result_str = "PASS"
        else:
            failed += 1
            result_str = "FAIL"

        results.append(
            {
                "id": case["id"],
                "user_message": user_msg,
                "expected_intent": expected_intent,
                "actual_intent": actual_intent,
                "expected_reason_code": expected_reason,
                "actual_reason_code": actual_reason,
                "result": result_str,
            }
        )

    # Generate Markdown Report
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as out_f:
        out_f.write("# Orchestrator User Behavior Evaluation Report\n\n")
        out_f.write(f"**Total Cases:** {len(cases)}\n\n")
        out_f.write(f"**Overall Passed:** {passed}\n\n")
        out_f.write(f"**Overall Failed:** {failed}\n\n")
        out_f.write("### Separated Metrics\n")
        out_f.write(
            f"- **Intent Accuracy:** {intent_matched}/{len(cases)} ({(intent_matched / len(cases)) * 100:.1f}%)\n"
        )
        if safety_cases > 0:
            out_f.write(
                f"- **Safety Reason Accuracy:** {safety_matched}/{safety_cases} ({(safety_matched / safety_cases) * 100:.1f}%)\n"
            )
        else:
            out_f.write("- **Safety Reason Accuracy:** N/A (0 cases)\n")
        out_f.write(
            f"- **Workflow Executed Successfully:** {workflow_executed}/{len(cases)} ({(workflow_executed / len(cases)) * 100:.1f}%)\n\n"
        )

        out_f.write("## Detailed Results\n\n")

        out_f.write("| ID | Message | Expected Intent | Actual Intent | Expected Reason | Actual Reason | Status |\n")
        out_f.write("|---|---|---|---|---|---|---|\n")
        for res in results:
            out_f.write(
                f"| {res['id']} | {res['user_message']} | {res['expected_intent']} | {res['actual_intent']} | {res['expected_reason_code']} | {res['actual_reason_code']} | {res['result']} |\n"
            )

    print(f"\nEvaluation Complete: {passed} passed, {failed} failed")
    print(f"Report generated at: {report_file}")


if __name__ == "__main__":
    run_eval()
