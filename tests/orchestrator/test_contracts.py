from __future__ import annotations

from typing import Any, Union, get_args, get_origin

import pytest
from pydantic import TypeAdapter, ValidationError

from src.models.db import ROLE_DOCTOR, ROLE_PATIENT
from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    BlockedPayload,
    ConfirmOcrAction,
    DataType,
    DoctorQuestionsPayload,
    ExplanationDataPayload,
    HistorySummaryPayload,
    IntentEnum,
    NeedsInputPayload,
    OrchestratorRequest,
    OrchestratorResponse,
    OrchestratorRole,
    OrchestratorSessionContext,
    ReasonCode,
    ResponseStatus,
    SuggestedAction,
    SuggestedActionType,
    TrendDataPayload,
    UIContext,
)
from src.services.auth import ROLE_GUEST


def _minimal_blocked_response(**updates):
    payload = {
        "intent": "UNSUPPORTED_OR_UNSAFE",
        "status": "blocked",
        "message": "Tôi không thể hỗ trợ yêu cầu này.",
        "data_type": "blocked",
        "data": {
            "data_type": "blocked",
            "safety_notice": "Không hỗ trợ nội dung này.",
        },
    }
    payload.update(updates)
    return payload


def test_ac1_intent_enum_has_exactly_eight_members():
    # APP_HELP added deliberately for the App Help RAG feature (Phase 2,
    # data/app_how_to_use/) — a frozen-contract update, not a drift.
    assert [member.name for member in IntentEnum] == [
        "UNSUPPORTED_OR_UNSAFE",
        "ANALYZE_REPORT",
        "EXPLAIN_CURRENT_RESULT",
        "VIEW_HISTORY",
        "ANALYZE_TREND",
        "GET_DOCTOR_QUESTIONS",
        "SAFE_GENERAL",
        "APP_HELP",
    ]


def test_response_status_has_exact_contract_values():
    assert [member.value for member in ResponseStatus] == [
        "success",
        "needs_input",
        "blocked",
        "error",
    ]


def test_ac2_invalid_intent_value_is_rejected():
    with pytest.raises(ValidationError):
        OrchestratorResponse.model_validate(_minimal_blocked_response(intent="DIAGNOSE"))


def test_ac3_data_discriminator_rejects_mismatched_payload_shape():
    with pytest.raises(ValidationError):
        OrchestratorResponse.model_validate(
            _minimal_blocked_response(
                data_type="trend",
                data={
                    "data_type": "trend",
                    "report_ref": "report-1",
                    "test_date": "2026-08-19",
                    "summary": "summary",
                    "status": "NORMAL",
                    "has_critical_values": False,
                    "result_count": 1,
                },
            )
        )


def test_data_type_has_exact_contract_values():
    assert [member.value for member in DataType] == [
        "analysis",
        "explanation",
        "history_summary",
        "trend",
        "doctor_questions",
        "blocked",
        "needs_input",
    ]


def _strip_annotated(annotation):
    if get_origin(annotation) is not None and str(get_origin(annotation)) == "<class 'typing.Annotated'>":
        return get_args(annotation)[0]
    return annotation


def _union_members(annotation):
    inner = _strip_annotated(annotation)
    if get_origin(inner) in {Union, getattr(__import__("types"), "UnionType")}:
        return get_args(inner)
    return ()


def test_ac4_response_data_is_closed_discriminated_union_without_escape_hatches():
    data_field = OrchestratorResponse.model_fields["data"]
    assert data_field.discriminator == "data_type"
    assert data_field.annotation is not dict
    assert data_field.annotation is not Any

    members = _union_members(data_field.annotation)
    assert set(members) == {
        AnalysisDataPayload,
        ExplanationDataPayload,
        HistorySummaryPayload,
        TrendDataPayload,
        DoctorQuestionsPayload,
        BlockedPayload,
        NeedsInputPayload,
    }
    for member in members:
        assert member.model_config.get("extra") != "allow"


def test_ac5_unknown_suggested_action_is_rejected():
    with pytest.raises(ValidationError):
        TypeAdapter(SuggestedAction).validate_python({"action": "OPEN_URL"})


@pytest.mark.parametrize("bad_field", ["url", "href", "patient_id"])
@pytest.mark.parametrize(
    "payload",
    [
        {"action": "OPEN_REPORT", "report_ref": "report-1"},
        {"action": "VIEW_ABNORMAL"},
        {"action": "VIEW_HISTORY"},
        {"action": "VIEW_TREND", "analyte_id": "potassium"},
        {"action": "VIEW_DOCTOR_QUESTIONS"},
        {"action": "CONFIRM_OCR", "review_ref": "review.token"},
        {"action": "RETRY"},
    ],
)
def test_ac6_suggested_actions_reject_navigation_and_identity_fields(payload, bad_field):
    with pytest.raises(ValidationError):
        TypeAdapter(SuggestedAction).validate_python({**payload, bad_field: "x"})


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "OPEN_REPORT", "report_ref": "javascript:alert"},
        {"action": "VIEW_ABNORMAL", "report_ref": "javascript:alert"},
        {"action": "VIEW_TREND", "analyte_id": "javascript:alert"},
        {"action": "VIEW_DOCTOR_QUESTIONS", "report_ref": "javascript:alert"},
        {"action": "CONFIRM_OCR", "review_ref": "javascript:alert"},
    ],
)
def test_ac6_suggested_actions_reject_executable_string_values(payload):
    with pytest.raises(ValidationError):
        TypeAdapter(SuggestedAction).validate_python(payload)


def test_req_u02_no_action_variant_declares_free_form_payload():
    def annotation_contains_free_form_payload(annotation) -> bool:
        pydantic_module = __import__("pydantic")
        typing_module = __import__("typing")
        origin = get_origin(annotation)
        forbidden = {
            dict,
            getattr(typing_module, "Dict"),
            Any,
            object,
            pydantic_module.JsonValue,
        }
        if annotation in forbidden or origin in forbidden:
            return True
        if isinstance(annotation, type) and issubclass(annotation, pydantic_module.BaseModel):
            return annotation.model_config.get("extra") == "allow"
        return any(annotation_contains_free_form_payload(arg) for arg in get_args(annotation))

    variants = _union_members(SuggestedAction)
    assert len(variants) == 7
    for variant in variants:
        assert variant.model_config.get("extra") == "forbid"
        for field in variant.model_fields.values():
            assert not annotation_contains_free_form_payload(field.annotation)


def test_ac7_request_rejects_pending_ocr_review():
    with pytest.raises(ValidationError):
        OrchestratorRequest.model_validate(
            {"message": "hello", "pending_ocr_review": False}
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"user_role": "PATIENT"},
        {"onboarding_acknowledged": True},
        {"patient_id": 123},
    ],
)
def test_ac8_request_rejects_server_authority_fields(extra):
    with pytest.raises(ValidationError):
        OrchestratorRequest.model_validate({"message": "hello", **extra})


def test_ac9_reason_code_has_exact_contract_members():
    assert [member.name for member in ReasonCode] == [
        "EMERGENCY_INPUT_SAFETY",
        "ONBOARDING_REQUIRED",
        "OCR_REVIEW_REQUIRED",
        "OCR_CONFIRM_INVALID",
        "MEDICAL_DIAGNOSIS_REQUEST",
        "MEDICAL_CAUSE_REQUEST",
        "TREATMENT_REQUEST",
        "PERSONAL_MEDICAL_ADVICE",
        "UNSUPPORTED_ANALYTE",
        "UNSUPPORTED_CAPABILITY",
        "AMBIGUOUS_CONTEXT",
        "AUTH_EXPIRED",
        "REPORT_NOT_FOUND_OR_UNAUTHORIZED",
        "DB_UNAVAILABLE",
        "LLM_UNAVAILABLE",
        "RAG_UNAVAILABLE",
        "TREND_INSUFFICIENT_POINTS",
        "TREND_UNIT_INCONSISTENT",
        "UNKNOWN_INTENT",
        "OUT_OF_SCOPE",
        "SENSITIVE_SYSTEM_REQUEST",
        "GUARDRAIL_BLOCKED",
        "INTERNAL_WORKFLOW_ERROR",
    ]


def test_ac10_orchestrator_role_only_includes_guest_and_patient_constants():
    assert [member.name for member in OrchestratorRole] == ["GUEST", "PATIENT"]
    assert OrchestratorRole.GUEST.value == ROLE_GUEST
    assert OrchestratorRole.PATIENT.value == ROLE_PATIENT
    assert all(member.value != ROLE_DOCTOR for member in OrchestratorRole)


def test_ac11_session_context_excludes_forbidden_fields_and_pending_ocr_is_server_only():
    forbidden = {"patient_id", "user_id", "token", "chat_history", "ocr_drafts"}
    assert forbidden.isdisjoint(OrchestratorSessionContext.model_fields)

    context = OrchestratorSessionContext.from_server(
        session_id="guest-session",
        user_role=OrchestratorRole.GUEST,
        pending_ocr_review=True,
        transient_ui_context=UIContext(screen="analysis"),
    )
    assert context.pending_ocr_review is True
    assert context.model_dump()["pending_ocr_review"] is True

    with pytest.raises(ValidationError):
        OrchestratorSessionContext.model_validate(
            {
                "session_id": "guest-session",
                "user_role": ROLE_GUEST,
                "pending_ocr_review": False,
            }
        )


def test_req_s02_session_context_declares_all_required_fields():
    required = {
        "session_id",
        "user_role",
        "onboarding_acknowledged",
        "current_report_ref",
        "current_analyte",
        "last_intent",
        "pending_ocr_review",
        "transient_ui_context",
        "conversation_state",
        "response_style",
    }
    declared = set(OrchestratorSessionContext.model_fields) | set(
        OrchestratorSessionContext.model_computed_fields
    )
    assert declared == required

    # REQ-C03: pending_ocr_review must remain derived, not client-settable.
    assert "pending_ocr_review" not in OrchestratorSessionContext.model_fields
    assert "pending_ocr_review" in OrchestratorSessionContext.model_computed_fields


def test_ac12_confirm_ocr_action_carries_only_review_reference():
    assert set(ConfirmOcrAction.model_fields) == {"action", "review_ref"}
    forbidden_fragments = ("indicator", "value", "unit", "draft", "analyte")
    assert not any(
        fragment in field_name
        for field_name in ConfirmOcrAction.model_fields
        for fragment in forbidden_fragments
    )


def test_all_seven_suggested_action_variants_are_present():
    assert [member.name for member in SuggestedActionType] == [
        "OPEN_REPORT",
        "VIEW_ABNORMAL",
        "VIEW_HISTORY",
        "VIEW_TREND",
        "VIEW_DOCTOR_QUESTIONS",
        "CONFIRM_OCR",
        "RETRY",
    ]
