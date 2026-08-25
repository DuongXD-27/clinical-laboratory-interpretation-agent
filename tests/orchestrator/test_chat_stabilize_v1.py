"""Targeted regressions for the four CHAT-STABILIZE-V1 capability gaps."""

from types import SimpleNamespace

from src.models.orchestrator_schemas import IntentEnum, ReasonCode
from src.orchestrator.gates import is_provenance_request, treatment_followup_gate
from src.orchestrator.intent_router import _deterministic_route


def test_safe_04_contextual_improvement_request_routes_to_treatment_request() -> None:
    session = SimpleNamespace(current_report_ref="401", current_analyte="HbA1c")

    result = treatment_followup_gate(
        "Tôi cần làm gì để cải thiện chỉ số này?",
        session,
    )

    assert result == ReasonCode.TREATMENT_REQUEST


def test_prov_01_dua_vao_dau_routes_to_provenance_handling() -> None:
    assert is_provenance_request("Thông tin này dựa vào đâu?") is True


def test_prov_02_nguon_cua_nguong_routes_to_provenance_handling() -> None:
    assert is_provenance_request("Nguồn của ngưỡng này là gì?") is True


def test_doc_01_hoi_gi_bac_si_routes_to_analyte_scoped_questions() -> None:
    decision = _deterministic_route("Tôi nên hỏi gì bác sĩ về WBC?")

    assert decision is not None
    assert decision.intent == IntentEnum.GET_DOCTOR_QUESTIONS
