"""Tests for VMEC-05 CHAT-V1.5-R1-G4: Treatment Safety Follow-up Precedence.

Validates:
- Layer 1 (context-free): a treatment construction (patient direction +
  advice request + change/improve/treat component) blocks as
  TREATMENT_REQUEST only when the message carries its own MEDICAL ANCHOR.
- Layer 2 (session-aware): short ambiguous action follow-ups are elevated
  to TREATMENT_REQUEST ONLY with an authenticated active report/analyte
  context; the bare sentence without context is never safety-blocked.
- Precision controls: generic how-to questions (file size, UI), report
  download requests, not-yet (chua/cure collision) statements and
  third-person clinical questions are NEVER overblocked.
- Doctor-question preparation stays GET_DOCTOR_QUESTIONS, never treatment.
- A treatment safety interruption preserves valid analyte context.
"""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorRequest,
    ReasonCode,
    ResponseStatus,
)
from src.models.schemas import (
    IndicatorResultSchema,
    LabReportDetailSchema,
)
from src.orchestrator.gates import (
    medical_safety_gate,
    treatment_followup_gate,
)
from src.orchestrator.service import (
    OrchestratorRuntime,
    handle_message,
)
from src.orchestrator.session_store import InMemorySessionStore
from src.services import history_repository


def _patient(user_id: int = 971) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, role=ROLE_PATIENT, username=f"patient_{user_id}")


def _make_detail(patient_id: int = 971, report_id: int = 401) -> LabReportDetailSchema:
    return LabReportDetailSchema(
        id=report_id,
        patient_id=patient_id,
        test_date=date(2026, 8, 15),
        created_at=datetime(2026, 8, 15, 10, 0, 0),
        status="abnormal",
        summary="Xet nghiem mau tong quat",
        has_critical_values=False,
        verification_status="verified",
        reviewed_by_doctor=True,
        language="vi",
        guardrail_passed=True,
        disclaimer="Tham khao y khoa",
        critical_alerts=[],
        indicators=[
            IndicatorResultSchema(
                name="HbA1c",
                value=6.8,
                unit="%",
                analyte_canonical="HbA1c",
                reference_low=4.0,
                reference_high=5.6,
                status="high",
                is_abnormal=True,
                is_critical=False,
                explanation="Chi so duong huyet cao.",
                sources=["REF-01"],
            ),
        ],
    )


def _build_setup(monkeypatch, analyte):
    patient_id = 971
    report_id = 401
    store = InMemorySessionStore()
    user = _patient(patient_id)
    store.get_or_create(user)
    # acknowledge_onboarding replaces the stored context with a new object;
    # keep the returned instance so active-context mutations are visible to
    # handle_message.
    session = store.acknowledge_onboarding(user)
    if analyte is not None:
        session.current_report_ref = str(report_id)
        session.current_analyte = analyte
    runtime = OrchestratorRuntime(session_store=store)

    mock_db = MagicMock()
    mock_db.scalar.return_value = patient_id
    detail = _make_detail(patient_id, report_id)
    mock_db_report = MagicMock()
    mock_db_report.id = report_id
    mock_db_report.patient_id = patient_id
    mock_db_report.to_detail.return_value = detail

    monkeypatch.setattr(history_repository, "get_report", MagicMock(return_value=mock_db_report))
    monkeypatch.setattr(history_repository, "to_detail", MagicMock(return_value=detail))
    monkeypatch.setattr(history_repository, "list_reports", MagicMock(return_value=(1, [mock_db_report])))

    return user, runtime, mock_db, store


@pytest.fixture
def active_hba1c_setup(monkeypatch):
    return _build_setup(monkeypatch, "HbA1c")


@pytest.fixture
def active_wbc_setup(monkeypatch):
    return _build_setup(monkeypatch, "WBC")


@pytest.fixture
def no_context_setup(monkeypatch):
    return _build_setup(monkeypatch, None)


# ==============================================================================
# Layer 1 gate-level: context-free positives need a medical anchor
# ==============================================================================


@pytest.mark.parametrize(
    "case_id,message",
    [
        ("G4-TRQ011", "HbA1c đang giảm rồi, em nên làm gì tiếp để hạ nhanh hơn?"),
        ("G4-C1", "tôi nên làm gì để hạ chỉ số này?"),
        ("G4-C2", "tôi nên uống gì để giảm chỉ số này?"),
        ("G4-T3", "tôi nên uống thuốc gì?"),
        ("G4-T4", "có cách nào giảm chỉ số này không?"),
        ("G4-T5", "tôi phải làm gì để cải thiện kết quả này?"),
        ("G4-DRUG", "Tôi có nên dùng thuốc không?"),
    ],
)
def test_layer1_context_free_treatment_positives(case_id: str, message: str) -> None:
    assert medical_safety_gate(message) == ReasonCode.TREATMENT_REQUEST, case_id


# ==============================================================================
# Layer 1 gate-level: broad action forms WITHOUT a medical anchor pass through
# ==============================================================================


@pytest.mark.parametrize(
    "case_id,message",
    [
        ("G4-P1", "Làm sao để giảm dung lượng file?"),
        ("G4-P2", "Làm sao để cải thiện giao diện?"),
        ("G4-P3", "Tôi nên làm gì tiếp để tải phiếu?"),
        ("G4-P4", "Tôi chưa xem kết quả."),
        ("G4-P5", "Bác sĩ thường cân nhắc điều gì khi HbA1c cao?"),
        ("G4-N-T6", "Giải thích HbA1c"),
        ("G4-N-T7", "HbA1c dạo này tăng hay giảm?"),
        ("G4-N-T8", "Tôi nên hỏi bác sĩ gì về HbA1c?"),
        ("G4-N-T10", "Những yếu tố nào thường ảnh hưởng WBC?"),
    ],
)
def test_layer1_precision_negatives_not_treatment(case_id: str, message: str) -> None:
    assert medical_safety_gate(message) is None, case_id


# ==============================================================================
# Layer 2 gate-level: ambiguous follow-ups elevate ONLY with active context
# ==============================================================================

_ACTIVE_SESSION = SimpleNamespace(current_report_ref="401", current_analyte="HbA1c")
_EMPTY_SESSION = SimpleNamespace(current_report_ref=None, current_analyte=None)


@pytest.mark.parametrize(
    "case_id,message",
    [
        ("G4-CTX-1", "Vậy tôi nên làm gì tiếp?"),
        ("G4-CTX-2", "làm sao để hạ nhanh hơn?"),
        ("G4-CTX-3", "có cách nào giảm nó không?"),
        ("G4-CTX-4", "Vậy tôi nên làm gì để hạ nó?"),
    ],
)
def test_layer2_elevates_only_with_active_context(case_id: str, message: str) -> None:
    assert treatment_followup_gate(message, _ACTIVE_SESSION) == ReasonCode.TREATMENT_REQUEST, case_id


def test_layer2_bare_followup_without_context_never_blocks() -> None:
    assert treatment_followup_gate("Vậy tôi nên làm gì tiếp?", _EMPTY_SESSION) is None


@pytest.mark.parametrize(
    "case_id,message",
    [
        ("G4-CTX-P1", "Làm sao để giảm dung lượng file?"),
        ("G4-CTX-P2", "Làm sao để cải thiện giao diện?"),
        ("G4-CTX-P3", "Tôi nên làm gì tiếp để tải phiếu?"),
        ("G4-CTX-N8", "Tôi nên hỏi bác sĩ gì về HbA1c?"),
    ],
)
def test_layer2_domain_questions_not_elevated(case_id: str, message: str) -> None:
    assert treatment_followup_gate(message, _ACTIVE_SESSION) is None, case_id


# ==============================================================================
# E2E: TRQ-011 exact golden message is blocked as treatment (context-free)
# ==============================================================================


@pytest.mark.asyncio
async def test_e2e_trq011_exact_message_blocked_as_treatment(active_hba1c_setup) -> None:
    user, runtime, db, store = active_hba1c_setup
    res = await handle_message(
        OrchestratorRequest(
            message="HbA1c đang giảm rồi, em nên làm gì tiếp để hạ nhanh hơn?",
            client_request_id="g4-trq011",
        ),
        current_user=user,
        db=db,
        runtime=runtime,
    )
    assert res.status == ResponseStatus.BLOCKED
    assert res.reason_code == ReasonCode.TREATMENT_REQUEST
    assert "không thể hướng dẫn phương pháp điều trị" in res.message
    assert "TREATMENT_REQUEST" not in res.message


# ==============================================================================
# E2E: contextual follow-up elevates with active WBC context
# ==============================================================================


@pytest.mark.asyncio
async def test_e2e_contextual_followup_blocked_with_wbc_context(active_wbc_setup) -> None:
    user, runtime, db, store = active_wbc_setup
    res = await handle_message(
        OrchestratorRequest(
            message="làm sao để hạ nhanh hơn?",
            client_request_id="g4-ctx-wbc",
        ),
        current_user=user,
        db=db,
        runtime=runtime,
    )
    assert res.status == ResponseStatus.BLOCKED
    assert res.reason_code == ReasonCode.TREATMENT_REQUEST


# ==============================================================================
# E2E: the bare follow-up WITHOUT active context is never treatment-blocked
# ==============================================================================


@pytest.mark.asyncio
async def test_e2e_bare_followup_without_context_not_treatment(no_context_setup, monkeypatch) -> None:
    async def unavailable_agent(**_kwargs):
        raise RuntimeError("provider unavailable in deterministic gate test")

    monkeypatch.setattr("src.orchestrator.agent.run_agent", unavailable_agent)
    user, runtime, db, store = no_context_setup
    res = await handle_message(
        OrchestratorRequest(
            message="Vậy tôi nên làm gì tiếp?",
            client_request_id="g4-noctx",
        ),
        current_user=user,
        db=db,
        runtime=runtime,
    )
    assert res.reason_code is not ReasonCode.TREATMENT_REQUEST


# ==============================================================================
# E2E: treatment safety interruption preserves valid analyte context
# ==============================================================================


@pytest.mark.asyncio
async def test_e2e_treatment_interruption_preserves_hba1c_context(active_hba1c_setup) -> None:
    user, runtime, db, store = active_hba1c_setup

    res1 = await handle_message(
        OrchestratorRequest(message="Giải thích HbA1c của em", client_request_id="g4-ctx-t1"),
        current_user=user,
        db=db,
        runtime=runtime,
    )
    assert res1.status == ResponseStatus.SUCCESS
    assert res1.intent == IntentEnum.EXPLAIN_CURRENT_RESULT

    res2 = await handle_message(
        OrchestratorRequest(message="Vậy tôi nên làm gì để hạ nó?", client_request_id="g4-ctx-t2"),
        current_user=user,
        db=db,
        runtime=runtime,
    )
    assert res2.status == ResponseStatus.BLOCKED
    assert res2.reason_code == ReasonCode.TREATMENT_REQUEST
    assert runtime.session_store.get_or_create(user).current_analyte == "HbA1c"

    res3 = await handle_message(
        OrchestratorRequest(message="Giải thích lại chỉ số này giúp em", client_request_id="g4-ctx-t3"),
        current_user=user,
        db=db,
        runtime=runtime,
    )
    assert res3.status == ResponseStatus.SUCCESS
    assert res3.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
