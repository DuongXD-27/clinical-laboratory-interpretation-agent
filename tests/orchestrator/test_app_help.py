"""Routing + dispatch tests for the APP_HELP intent (yeu-cau-vu.txt AH-01..AH-12).

Routing-level cases (AH-01..AH-05, negative controls AH-06..AH-09) exercise
``_deterministic_route`` directly, mirroring ``test_safe_general.py``'s
pattern. Dispatch-level cases (AH-10..AH-12) exercise
``_dispatch_app_help`` with a stubbed retriever so no real embedding
provider/Chroma collection is needed in unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.models.orchestrator_schemas import IntentEnum, ResponseStatus
from src.orchestrator.dispatcher import DispatchContext, _dispatch_app_help
from src.orchestrator.intent_router import _deterministic_route
from src.services.app_help_retriever import AppHelpChunkMatch, AppHelpRetrievalResult, AppHelpRetrieverError


# ==============================================================================
# AH-01..AH-05: known app-help phrasings route to APP_HELP
# ==============================================================================

@pytest.mark.parametrize(
    "message",
    [
        "Làm sao tải phiếu xét nghiệm?",  # AH-01
        "Tôi xem lịch sử ở đâu?",  # AH-02
        "Làm sao xem xu hướng WBC?",  # AH-03
        "Tại sao phải xác nhận OCR?",  # AH-04
        "Tôi sửa hồ sơ ở đâu?",  # AH-05
    ],
)
def test_ah01_to_ah05_route_to_app_help(message):
    route = _deterministic_route(message)
    assert route is not None, f"Expected {message!r} to be deterministically routed"
    assert route.intent == IntentEnum.APP_HELP


# ==============================================================================
# AH-06, AH-07: medical questions must NOT be classified as APP_HELP
# ==============================================================================

@pytest.mark.parametrize(
    "message",
    [
        "WBC là gì?",  # AH-06
        "WBC của tôi có cao không?",  # AH-07
    ],
)
def test_ah06_ah07_medical_questions_are_not_app_help(message):
    route = _deterministic_route(message)
    if route is not None:
        assert route.intent != IntentEnum.APP_HELP


# ==============================================================================
# AH-10, AH-12: fail-closed, never invent a route/button
# ==============================================================================

@dataclass
class _FakeUser:
    role: str


class _EmptyRetriever:
    """Stub: no chunk clears the min_score threshold (AH-10/AH-12 case)."""

    def retrieve(self, query, *, requester_role=None):
        return AppHelpRetrievalResult(query=query, matches=[])


class _UnavailableRetrieverFactory:
    def __call__(self):
        raise AppHelpRetrieverError("disabled for this test")


@pytest.mark.asyncio
async def test_ah10_ah12_no_match_does_not_invent_a_feature(monkeypatch):
    monkeypatch.setattr(
        "src.services.app_help_retriever.get_app_help_retriever",
        lambda: _EmptyRetriever(),
    )
    context = DispatchContext(
        current_user=_FakeUser(role="patient"),
        db=None,
        current_report_ref=None,
        current_analyte=None,
        message="Làm sao xuất phiếu ra file PDF ký số?",
    )
    result = await _dispatch_app_help(context)
    assert result.status == ResponseStatus.SUCCESS
    assert result.data.sources == []
    # Fail-closed message must not name any concrete route/button — only the
    # generic "not found" template is allowed here.
    assert "chưa tìm thấy hướng dẫn phù hợp" in result.data.explanation.lower()


@pytest.mark.asyncio
async def test_app_help_disabled_fails_closed_not_silently(monkeypatch):
    monkeypatch.setattr(
        "src.services.app_help_retriever.get_app_help_retriever",
        _UnavailableRetrieverFactory(),
    )
    context = DispatchContext(
        current_user=_FakeUser(role="patient"),
        db=None,
        current_report_ref=None,
        current_analyte=None,
        message="Tôi xem lịch sử ở đâu?",
    )
    result = await _dispatch_app_help(context)
    assert result.status == ResponseStatus.SUCCESS
    assert result.data.sources == []


# ==============================================================================
# AH-11: role-aware answer when a doctor asks about a patient-only workflow
# ==============================================================================

class _PatientOnlyRetriever:
    def retrieve(self, query, *, requester_role=None):
        match = AppHelpChunkMatch(
            chunk_id="profile::sua-thong-tin-ca-nhan",
            text="Sửa thông tin cá nhân\n\nVào /patient/profile để chỉnh sửa hồ sơ.",
            feature="profile",
            role="patient",
            route="/patient/profile",
            heading="Sửa thông tin cá nhân",
            source_file="profile.md",
            score=0.9,
        )
        return AppHelpRetrievalResult(query=query, matches=[match])


@pytest.mark.asyncio
async def test_ah11_doctor_asking_patient_only_workflow_gets_role_caveat(monkeypatch):
    monkeypatch.setattr(
        "src.services.app_help_retriever.get_app_help_retriever",
        lambda: _PatientOnlyRetriever(),
    )
    context = DispatchContext(
        current_user=_FakeUser(role="doctor"),
        db=None,
        current_report_ref=None,
        current_analyte=None,
        message="Tôi sửa hồ sơ ở đâu?",
    )
    result = await _dispatch_app_help(context)
    assert result.status == ResponseStatus.SUCCESS
    assert "dành cho tài khoản bệnh nhân" in result.data.explanation
    assert result.data.sources == ["profile.md"]


@pytest.mark.asyncio
async def test_patient_asking_own_role_workflow_gets_no_caveat(monkeypatch):
    monkeypatch.setattr(
        "src.services.app_help_retriever.get_app_help_retriever",
        lambda: _PatientOnlyRetriever(),
    )
    context = DispatchContext(
        current_user=_FakeUser(role="patient"),
        db=None,
        current_report_ref=None,
        current_analyte=None,
        message="Tôi sửa hồ sơ ở đâu?",
    )
    result = await _dispatch_app_help(context)
    assert "Lưu ý:" not in result.data.explanation
