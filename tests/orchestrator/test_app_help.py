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

from src.models.orchestrator_schemas import ExplanationDataPayload, IntentEnum, ResponseStatus
from src.orchestrator import response_composer
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


# ==============================================================================
# Regression: the general response composer must NEVER paraphrase an
# APP_HELP answer through an LLM. Found live in manual testing: the
# dispatcher's raw corpus-chunk text was silently getting rewritten by
# response_composer.compose_message (which runs an LLM "rewrite/summarize"
# pass on any ExplanationDataPayload without `facts`) before reaching the
# user — defeating the whole point of returning the corpus text verbatim
# (yeu-cau-vu.txt mục D requires a "deterministic / grounded answer").
# ==============================================================================

class _FakeComposerLLM:
    """Mirrors test_response_composer.py's FakeLLM: get_llm() -> object with
    .with_structured_output(schema) -> self, .ainvoke(messages) -> output."""

    def __init__(self, output):
        self.output = output

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return self.output


@pytest.mark.asyncio
async def test_app_help_llm_rewrite_is_used_when_it_stays_grounded(monkeypatch):
    # A rewrite that only rephrases tone (no new quoted labels/routes beyond
    # what the source already names) is trusted and used — this is the
    # feature the user asked for: raw corpus dumps ("Feature này dùng để làm
    # gì?" headings, `file.md` references) read like internal docs, so a
    # bounded rewrite for natural chat tone is allowed as long as it can't
    # introduce a new claim.
    fallback = 'Tải phiếu tại trang "/patient/analysis", bấm nút "Tải ảnh phiếu".'
    natural_rewrite = 'Bạn vào trang "/patient/analysis" rồi bấm nút "Tải ảnh phiếu" để tải phiếu lên nhé.'
    monkeypatch.setattr(
        response_composer,
        "get_llm",
        lambda: _FakeComposerLLM(response_composer.ComposedMessage(message=natural_rewrite)),
    )

    message = await response_composer.compose_message(
        intent=IntentEnum.APP_HELP,
        status=ResponseStatus.SUCCESS,
        reason_code=None,
        data=ExplanationDataPayload(explanation=fallback, sources=["upload-lab-report.md"]),
        fallback_message=fallback,
    )
    assert message == natural_rewrite


@pytest.mark.asyncio
async def test_app_help_llm_rewrite_with_invented_route_is_rejected(monkeypatch):
    # If the rewrite names a route/button that never appeared in the
    # source, it's discarded and the verbatim fallback is used instead —
    # this is the actual AH-10 guarantee: a prompt instruction alone
    # ("don't invent routes") is a request, not a guarantee.
    fallback = 'Tải phiếu tại trang "/patient/analysis".'
    hallucinated_rewrite = 'Bạn vào trang "/patient/upload" rồi bấm nút "Xuất PDF" nhé.'
    monkeypatch.setattr(
        response_composer,
        "get_llm",
        lambda: _FakeComposerLLM(response_composer.ComposedMessage(message=hallucinated_rewrite)),
    )

    message = await response_composer.compose_message(
        intent=IntentEnum.APP_HELP,
        status=ResponseStatus.SUCCESS,
        reason_code=None,
        data=ExplanationDataPayload(explanation=fallback, sources=["upload-lab-report.md"]),
        fallback_message=fallback,
    )
    assert message == fallback


@pytest.mark.asyncio
async def test_app_help_composer_unavailable_falls_back_to_verbatim(monkeypatch):
    def _boom():
        raise RuntimeError("llm down")

    monkeypatch.setattr(response_composer, "get_llm", _boom)

    fallback = "Vào mục Lịch sử kết quả trên menu."
    message = await response_composer.compose_message(
        intent=IntentEnum.APP_HELP,
        status=ResponseStatus.SUCCESS,
        reason_code=None,
        data=ExplanationDataPayload(explanation=fallback, sources=["history.md"]),
        fallback_message=fallback,
    )
    assert message == fallback


def test_clean_app_help_text_strips_heading_and_file_refs():
    from src.orchestrator.dispatcher import _clean_app_help_text

    raw = (
        "Feature này dùng để làm gì?\n\n"
        "Cho phép bệnh nhân nhập kết quả xét nghiệm "
        "(xem file `ocr-review.md`)."
    )
    cleaned = _clean_app_help_text(raw)
    assert "Feature này dùng để làm gì?" not in cleaned
    assert "ocr-review.md" not in cleaned
    assert "Cho phép bệnh nhân nhập kết quả xét nghiệm" in cleaned


@pytest.mark.asyncio
async def test_app_help_build_final_response_surfaces_the_real_explanation(monkeypatch):
    # Regression: found live in manual UI testing. The first fix (blocking
    # the LLM composer for APP_HELP) was necessary but NOT sufficient — it
    # exposed a second, independent bug: deterministic_message_for() had no
    # APP_HELP branch, so it fell through to a generic AnalysisDataPayload-
    # shaped placeholder ("Đây là kết quả phân tích hiện có.") that ignores
    # ExplanationDataPayload.explanation entirely. Before the LLM-composer
    # fix, the LLM silently "fixed" this by reading the real explanation out
    # of _payload_summary(data) and paraphrasing it — masking the bug. This
    # test goes through the real build_final_response() wiring end-to-end
    # (deterministic_message_for -> compose_message), not a hand-supplied
    # fallback_message, so it cannot be fooled the same way the first
    # regression test could.
    def _boom():
        raise RuntimeError("should never be reached")

    monkeypatch.setattr(response_composer, "get_llm", _boom)

    explanation = "Vào mục \"Lịch sử kết quả\" trên menu để xem các phiếu đã lưu."
    response = await response_composer.build_final_response(
        intent=IntentEnum.APP_HELP,
        status=ResponseStatus.SUCCESS,
        data=ExplanationDataPayload(explanation=explanation, sources=["history.md"]),
    )
    assert response.message == explanation
    assert "kết quả phân tích hiện có" not in response.message
