from __future__ import annotations

import json

from scripts.run_response_quality_eval import generate_markdown_report_from_json


def _report(assistant_message: str) -> dict[str, object]:
    return {
        "timestamp": 1787000000.0,
        "total_cases": 1,
        "passed_cases": 1,
        "failed_cases": 0,
        "suites": [
            {
                "suite_name": "response_quality",
                "total_cases": 1,
                "passed_cases": 1,
                "failed_cases": 0,
                "pass_rate": 100.0,
                "cases": [
                    {
                        "case_id": "RQ-001",
                        "suite_name": "response_quality",
                        "category": "regression",
                        "description": "report identity",
                        "user_display": "Explain WBC",
                        "execution_layer": "E2E_API",
                        "fixture_provisioned": True,
                        "controlled_retrieval_injected": False,
                        "foreign_patient_fixture_created": False,
                        "assistant_text_generated": True,
                        "hard_result": "HARD_PASS",
                        "soft_result": "SOFT_NOT_EVALUATED",
                        "classification": "TRUE_EXECUTED_PASS",
                        "passed": True,
                        "failure_tags": [],
                        "failure_reasons": [],
                        "turns": [
                            {
                                "turn_index": 1,
                                "user_message": "Explain WBC",
                                "assistant_message": assistant_message,
                                "intent": "EXPLAIN_CURRENT_RESULT",
                                "status": "SUCCESS",
                                "reason_code": None,
                                "active_analyte": "WBC",
                                "workflow_selected": "get_indicator",
                                "data_type": "EXPLANATION",
                                "payload_type": "ExplanationDataPayload",
                                "trend_payload_present": False,
                                "hard_checks": [],
                                "soft_checks": [],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_json_snapshots_with_different_turns_produce_distinct_auditable_reports(tmp_path):
    first_json = tmp_path / "first.json"
    second_json = tmp_path / "second.json"
    first_json.write_text(json.dumps(_report("First response")), encoding="utf-8")
    second_json.write_text(json.dumps(_report("Second response")), encoding="utf-8")
    first_markdown = tmp_path / "first.md"
    second_markdown = tmp_path / "second.md"

    generate_markdown_report_from_json(first_json, first_markdown)
    generate_markdown_report_from_json(second_json, second_markdown)

    first = first_markdown.read_text(encoding="utf-8")
    second = second_markdown.read_text(encoding="utf-8")
    assert first != second
    assert "**Source JSON**: `first.json`" in first
    assert "**Source JSON**: `second.json`" in second
    assert "**Source SHA-256**" in first
    assert "Reconciled across 1 cases" in first
