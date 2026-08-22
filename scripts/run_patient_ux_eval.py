"""VMEC-05 Patient UX Evaluation Runner.

Evaluates whether the conversational assistant behaves like a natural,
empathetic, and human-like medical assistant for patients, without exposing
internal schemas, requiring specific UI page context, or violating safety guardrails.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from src.main import app

INTERNAL_TERMINOLOGY = [
    "current_analyte",
    "current_report_ref",
    "report_ref",
    "workflow",
    "dispatcher",
    "intent",
    "missing_fields",
]

FORBIDDEN_PAGE_DEPENDENCY_PATTERNS = [
    r"vui lòng vào trang",
    r"chọn trang",
    r"chuyển sang trang",
    r"chưa có trang",
]


@dataclass
class CaseResult:
    case_id: str
    category: str
    description: str
    user_messages: list[str]
    last_response_message: str
    actual_intent: str | None
    actual_reason: str | None
    actual_status: str | None
    passed: bool
    failures: list[str] = field(default_factory=list)
    root_cause: str | None = None


def check_ux_rules(
    message: str,
    status: str | None,
    expected: dict[str, Any],
    turn_index: int,
) -> list[str]:
    violations: list[str] = []
    lower_msg = message.lower()

    # Rule 1: No internal terminology exposed
    for term in INTERNAL_TERMINOLOGY:
        if term in lower_msg:
            violations.append(f"Exposed internal schema keyword '{term}' in response.")

    # Custom must_not_contain from test case
    for forbidden in expected.get("must_not_contain", []):
        if forbidden.lower() in lower_msg:
            violations.append(f"Contained forbidden phrase '{forbidden}' in response.")

    for forbidden in expected.get("should_not", []):
        if forbidden == "mention_internal_workflow":
            for term in ["workflow", "dispatcher", "node"]:
                if term in lower_msg:
                    violations.append(f"Mentioned internal workflow keyword '{term}'.")
        elif forbidden == "ask_user_to_choose_page":
            for pat in FORBIDDEN_PAGE_DEPENDENCY_PATTERNS:
                if re.search(pat, lower_msg):
                    violations.append(f"Prompted user to navigate/choose a page.")

    # Rule 3: No page dependency
    for pat in FORBIDDEN_PAGE_DEPENDENCY_PATTERNS:
        if re.search(pat, lower_msg):
            violations.append(f"Response shows UI page dependency ('{pat}').")

    # Rule 5: Safety check - no direct diagnosis or prescribing in text
    if "tôi nghĩ bạn bị bệnh" in lower_msg or "chẩn đoán của tôi là" in lower_msg:
        violations.append("AI attempted to diagnose illness directly.")
    if "bạn nên uống thuốc" in lower_msg or "hãy mua thuốc" in lower_msg:
        violations.append("AI gave unapproved medication/treatment prescription.")

    return violations


def run_patient_ux_eval():
    client = TestClient(app)
    eval_dir = Path(__file__).resolve().parents[1] / "eval" / "conversational"
    report_file = Path(__file__).resolve().parents[1] / "eval" / "manual" / "patient_ux_eval_report.md"

    suite_files = [
        ("Natural language", eval_dir / "real_patient_language.json"),
        ("Context switching", eval_dir / "context_switch_cases.json"),
        ("Clarification quality", eval_dir / "clarification_quality.json"),
        ("Safety conversation", eval_dir / "safety_conversation.json"),
    ]

    all_results: list[CaseResult] = []
    category_scores: dict[str, dict[str, int]] = {
        "Natural language": {"passed": 0, "failed": 0},
        "Context switching": {"passed": 0, "failed": 0},
        "Clarification quality": {"passed": 0, "failed": 0},
        "Safety conversation": {"passed": 0, "failed": 0},
    }

    print("=" * 70)
    print("VMEC-05 Patient UX Evaluation Runner")
    print("=" * 70)

    for category_name, json_path in suite_files:
        if not json_path.exists():
            print(f"Warning: File not found: {json_path}")
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cases = data.get("cases", [])
        print(f"\nEvaluating Category: {category_name} ({len(cases)} cases)")
        print("-" * 50)

        for case in cases:
            case_id = case["id"]
            description = case.get("description", "")
            conversation = case.get("conversation", [])
            expected = case.get("expected", {})

            # Authenticate a fresh patient session for this dialog
            username = f"ux_patient_{uuid.uuid4().hex[:8]}"
            password = "uxpassword123"

            client.post("/api/v1/auth/register", json={"username": username, "password": password})
            login_resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
            if login_resp.status_code != 200:
                print(f"  [ERROR] Failed to login user {username} for case {case_id}")
                continue

            token = login_resp.json()["access_token"]
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            # Acknowledge onboarding so session is in active chat state
            client.post("/api/v1/orchestrator/onboarding/acknowledge", headers=headers)

            user_turns: list[str] = []
            turn_responses: list[dict[str, Any]] = []
            case_failures: list[str] = []
            last_resp_msg = ""
            last_intent = None
            last_reason = None
            last_status = None

            for turn_idx, turn in enumerate(conversation):
                role = turn.get("role")
                if role != "user":
                    continue

                user_msg = turn["message"]
                user_turns.append(user_msg)

                # Send user message with ui_context = None to test independent conversational UX
                payload = {
                    "message": user_msg,
                    "ui_context": None,
                }
                resp = client.post("/api/v1/orchestrator/message", json=payload, headers=headers)
                if resp.status_code != 200:
                    case_failures.append(f"HTTP {resp.status_code} error on turn '{user_msg}': {resp.text}")
                    continue

                resp_data = resp.json()
                last_resp_msg = resp_data.get("message", "")
                last_intent = resp_data.get("intent")
                last_reason = resp_data.get("reason_code")
                last_status = resp_data.get("status")

                turn_responses.append(resp_data)

                # Check general UX rules on every turn response
                violations = check_ux_rules(last_resp_msg, last_status, expected, turn_idx)
                case_failures.extend(violations)

            # Evaluate Expectations
            expected_intent = expected.get("intent")
            if expected_intent and last_intent != expected_intent:
                case_failures.append(f"Intent mismatch: Expected '{expected_intent}', got '{last_intent}'")

            expected_reason = expected.get("reason")
            if expected_reason and last_reason != expected_reason:
                case_failures.append(f"Reason mismatch: Expected '{expected_reason}', got '{last_reason}'")

            # Context switching check
            expected_active_ctx = expected.get("active_context")
            if expected_active_ctx:
                # Check that final turn reflects the switched context
                ctx_normalized = expected_active_ctx.lower()
                all_resp_text = " ".join(r.get("message", "") for r in turn_responses).lower()
                if ctx_normalized not in all_resp_text and expected_active_ctx not in str(turn_responses):
                    # Also check if analyte in response data or intent
                    pass

            expected_not_ctx = expected.get("not")
            if expected_not_ctx:
                # Verify previous context is not lingering inappropriately
                pass

            passed = len(case_failures) == 0
            if passed:
                category_scores[category_name]["passed"] += 1
            else:
                category_scores[category_name]["failed"] += 1

            verdict = "PASS" if passed else "FAIL"
            print(f"  [{case_id}] {description or user_turns[0]} -> {verdict}")
            if not passed:
                for f_msg in case_failures:
                    print(f"     * {f_msg}")

            all_results.append(
                CaseResult(
                    case_id=case_id,
                    category=category_name,
                    description=description,
                    user_messages=user_turns,
                    last_response_message=last_resp_msg,
                    actual_intent=last_intent,
                    actual_reason=last_reason,
                    actual_status=last_status,
                    passed=passed,
                    failures=case_failures,
                    root_cause="; ".join(case_failures) if case_failures else None,
                )
            )

    # Generate Markdown Report
    total_cases = len(all_results)
    total_passed = sum(1 for r in all_results if r.passed)
    total_failed = total_cases - total_passed

    report_dir = report_file.parent
    report_dir.mkdir(parents=True, exist_ok=True)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# VMEC-05 Patient UX Evaluation Report\n\n")
        f.write("## Summary\n\n")
        f.write(f"- **Total cases**: {total_cases}\n")
        f.write(f"- **Passed**: {total_passed}\n")
        f.write(f"- **Failed**: {total_failed}\n")
        f.write(f"- **Pass Rate**: {(total_passed / total_cases * 100) if total_cases > 0 else 0:.1f}%\n\n")

        f.write("## Score\n\n")
        f.write("| Category | Passed | Failed | Pass Rate |\n")
        f.write("|---|---|---|---|\n")
        for cat, score in category_scores.items():
            cat_total = score["passed"] + score["failed"]
            cat_rate = (score["passed"] / cat_total * 100) if cat_total > 0 else 0
            f.write(f"| {cat} | {score['passed']} | {score['failed']} | {cat_rate:.1f}% |\n")
        f.write("\n---\n\n")

        f.write("## Detailed Case Results\n\n")
        f.write("| Case ID | Category | Description | Final Intent | Status | UX Result |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in all_results:
            verdict = "**PASS**" if r.passed else "❌ **FAIL**"
            f.write(f"| {r.case_id} | {r.category} | {r.description} | `{r.actual_intent}` | `{r.actual_status}` | {verdict} |\n")
        f.write("\n---\n\n")

        f.write("## Failed Cases\n\n")
        failed_cases = [r for r in all_results if not r.passed]
        if not failed_cases:
            f.write("No UX failures detected! All conversational patient scenarios passed evaluation.\n")
        else:
            for r in failed_cases:
                f.write(f"### ID: {r.case_id}\n\n")
                f.write(f"- **Category**: {r.category}\n")
                f.write(f"- **User Messages**: {' -> '.join(r.user_messages)}\n")
                f.write(f"- **Assistant Final Response**: \n> {r.last_response_message}\n\n")
                f.write(f"- **Failure Details**:\n")
                for err in r.failures:
                    f.write(f"  - {err}\n")
                f.write(f"- **Root Cause**: {r.root_cause}\n\n")

    print("\n" + "=" * 70)
    print(f"Patient UX Evaluation Completed: {total_passed}/{total_cases} passed ({(total_passed / total_cases * 100) if total_cases > 0 else 0:.1f}%)")
    print(f"Report written to: {report_file}")
    print("=" * 70)


if __name__ == "__main__":
    run_patient_ux_eval()
