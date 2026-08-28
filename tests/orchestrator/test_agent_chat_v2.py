from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from src.config import get_settings
from src.models.db import LabReport, ReportIndicator, User
from src.models.orchestrator_schemas import (
    DataType,
    ExplanationDataPayload,
    IntentEnum,
    OrchestratorRequest,
    OrchestratorResponse,
    ReasonCode,
    ResponseStatus,
)
from src.orchestrator.agent_tools import AgentToolbox
from src.orchestrator.agent_v2 import (
    AgentV2Result,
    run_agent_v2,
    validate_or_sanitize_patient_reassurance,
)
from src.orchestrator.errors import OrchestratorWrapperError
from src.orchestrator.gates import medical_safety_gate, treatment_followup_gate
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import ConversationScopedSessionStore, bind_conversation, default_session_store
from src.services import conversation_repository


class ScriptedToolCallingLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.bound_tool_names = []
        self.tool_schemas = {}

    def bind_tools(self, tools):
        self.bound_tool_names = [item.name for item in tools]
        self.tool_schemas = {item.name: item.args_schema.model_json_schema() for item in tools}
        return self

    async def ainvoke(self, _messages):
        return self.responses.pop(0)


def _call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _patient(test_db):
    db = test_db.session()
    user = db.query(User).filter(User.role == "patient").first()
    actor = SimpleNamespace(role="patient", user_id=user.id, username=user.username)
    return db, actor


def _add_wbc(db, patient_id: int, report_date: date, value: float, status: str = "high"):
    report = LabReport(patient_id=patient_id, test_date=report_date, status="COMPLETED")
    report.indicators.append(
        ReportIndicator(
            name="WBC",
            analyte_raw="WBC",
            analyte_canonical="WBC",
            value=value,
            unit="10^9/L",
            canonical_value=value,
            canonical_unit="10^9/L",
            reference_low=4.0,
            reference_high=10.0,
            status=status,
            explanation="",
            sources=[],
        )
    )
    db.add(report)
    db.commit()
    return report


def test_history_tool_returns_actual_previous_measurement(test_db):
    db, actor = _patient(test_db)
    try:
        _add_wbc(db, actor.user_id, date(2026, 7, 1), 11.0)
        _add_wbc(db, actor.user_id, date(2026, 8, 1), 15.0)

        result = AgentToolbox(actor, db).get_indicator_history("WBC", limit=5)
        current = AgentToolbox(actor, db).get_indicator("WBC")
        report_summary = AgentToolbox(actor, db).get_current_report()

        assert [item["value"] for item in result["measurements"]] == [11.0, 15.0]
        assert result["current"] == {"report_ref": result["measurements"][1]["report_ref"], "index": 1}
        assert result["previous"] == {"report_ref": result["measurements"][0]["report_ref"], "index": 0}
        assert result["measurements"][0]["status"] == "HIGH"
        assert result["measurements"][0]["critical_status"] == "NOT_CRITICAL"
        assert result["measurements"][0]["reference"]["display"] == "4.0–10.0 10^9/L"
        assert current["canonical_analyte"] == "WBC"
        assert current["status"] == "HIGH"
        assert current["reference"] == {
            "low": 4.0,
            "high": 10.0,
            "operator": None,
            "display": "4.0–10.0 10^9/L",
        }
        assert set(report_summary) == {
            "report_ref",
            "test_date",
            "result_count",
            "has_abnormal",
            "has_critical",
        }
    finally:
        db.close()


def test_trend_tool_reuses_existing_trend_service(test_db):
    db, actor = _patient(test_db)
    try:
        for day, value in ((1, 9.0), (8, 10.0), (15, 11.0)):
            _add_wbc(db, actor.user_id, date(2026, 8, day), value, "normal" if value <= 10 else "high")

        result = AgentToolbox(actor, db).get_indicator_trend("WBC")

        assert result["trend_available"] is True
        assert result["direction"] == "INCREASING"
        assert [point["value"] for point in result["points"]] == [9.0, 10.0, 11.0]

        for day, value in ((20, 12.0), (24, 13.0), (28, 14.0)):
            _add_wbc(db, actor.user_id, date(2026, 8, day), value)
        all_points = AgentToolbox(actor, db).get_indicator_trend("WBC", window="all")
        latest_three = AgentToolbox(actor, db).get_indicator_trend("WBC", window="latest3")
        assert all_points["point_count"] == 6
        assert latest_three["point_count"] == 3
        assert [point["value"] for point in latest_three["points"]] == [12.0, 13.0, 14.0]
        assert latest_three["direction"] == "INCREASING"

        empty_user = User(username="patient_no_trend", password_hash="not-used", role="patient")
        db.add(empty_user)
        db.commit()
        unavailable = AgentToolbox(
            SimpleNamespace(role="patient", user_id=empty_user.id, username=empty_user.username),
            db,
        ).get_indicator_trend("WBC")
        assert unavailable == {
            "analyte": "WBC",
            "trend_available": False,
            "point_count": 0,
            "direction": None,
            "points": [],
            "latest": None,
            "reason_code": "INSUFFICIENT_TREND_DATA",
        }
    finally:
        db.close()


@pytest.mark.asyncio
async def test_agent_calls_indicator_and_medical_kb_for_explanation(monkeypatch):
    actor = SimpleNamespace(role="patient", user_id=7, username="patient")
    indicator = {
        "report_ref": "21",
        "analyte": "WBC",
        "value": 15.0,
        "unit": "10^9/L",
        "status": "high",
        "critical_status": "NOT_CRITICAL",
        "reference": {"low": 4.0, "high": 10.0, "operator": None, "display": "4.0–10.0 10^9/L"},
    }
    retrieval_args = {}

    class FakeRetriever:
        def retrieve(self, **kwargs):
            retrieval_args.update(kwargs)
            return [
                {
                    "indicator_name": "WBC",
                    "text": "Approved text",
                    "source_title": "WHO",
                    "source_url": "https://example.test/wbc",
                    "score": 0.91,
                }
            ]

    monkeypatch.setattr(AgentToolbox, "get_indicator", lambda self, analyte, report_ref=None: indicator)
    monkeypatch.setattr("src.orchestrator.agent_tools.get_medical_knowledge_retriever", lambda: FakeRetriever())
    llm = ScriptedToolCallingLlm(
        [
            AIMessage(
                content="",
                tool_calls=[
                    _call("get_indicator", {"analyte": "WBC"}, "c1"),
                    _call("retrieve_medical_evidence", {"query": "Giải thích WBC", "status": "HIGH"}, "c2"),
                ],
            ),
            AIMessage(
                content="WBC đang được hệ thống đánh dấu cao. Tài liệu được phê duyệt cung cấp thông tin giáo dục tổng quan; đây không phải kết luận về nguyên nhân của riêng bạn."
            ),
        ]
    )
    monkeypatch.setattr("src.orchestrator.agent_v2.get_llm", lambda: llm)

    result = await run_agent_v2(
        message="Giải thích WBC của tôi",
        current_user=actor,
        db=object(),
        current_report_ref="21",
        current_analyte=None,
    )

    assert "get_indicator" in llm.bound_tool_names
    assert "retrieve_medical_evidence" in llm.bound_tool_names
    assert llm.tool_schemas["get_current_report"]["additionalProperties"] is False
    assert "patient_id" not in str(llm.tool_schemas)
    assert result.response.status == ResponseStatus.SUCCESS
    assert result.response.sources == ["https://example.test/wbc"]
    assert result.response.data.facts.value == 15.0
    assert retrieval_args["analyte_id"] == "wbc"


@pytest.mark.asyncio
async def test_agent_followup_uses_previous_wbc_value(monkeypatch):
    actor = SimpleNamespace(role="patient", user_id=7, username="patient")
    previous = {
        "report_ref": "20",
        "test_date": "2026-07-01",
        "analyte": "WBC",
        "value": 11.0,
        "unit": "10^9/L",
        "status": "HIGH",
        "critical_status": "NOT_CRITICAL",
        "reference": {"low": 4.0, "high": 10.0, "display": "4.0–10.0 10^9/L"},
    }
    current = {**previous, "report_ref": "21", "value": 15.0}
    history = {
        "analyte": "WBC",
        "canonical_analyte": "WBC",
        "current": {"report_ref": "21", "index": 1},
        "previous": {"report_ref": "20", "index": 0},
        "measurements": [previous, current],
    }
    monkeypatch.setattr(AgentToolbox, "get_indicator_history", lambda self, analyte, limit=5: history)
    llm = ScriptedToolCallingLlm(
        [
            AIMessage(content="", tool_calls=[_call("get_indicator_history", {"analyte": "WBC", "limit": 5}, "c1")]),
            AIMessage(content="Lần trước, WBC được ghi nhận là 11.0 10^9/L vào ngày 01/07/2026."),
        ]
    )
    monkeypatch.setattr("src.orchestrator.agent_v2.get_llm", lambda: llm)

    result = await run_agent_v2(
        message="So với lần trước thì sao?",
        current_user=actor,
        db=object(),
        current_report_ref="21",
        current_analyte="WBC",
    )

    assert result.workflow_selected == "get_indicator_history"
    assert result.current_report_ref == "21"
    assert result.response.data.facts.value == 11.0
    assert "11.0" in result.response.message


@pytest.mark.asyncio
async def test_agent_fails_closed_without_approved_evidence(monkeypatch):
    actor = SimpleNamespace(role="patient", user_id=7, username="patient")
    monkeypatch.setattr(
        AgentToolbox, "retrieve_medical_evidence", lambda *args, **kwargs: {"evidence": [], "sufficient": False}
    )
    llm = ScriptedToolCallingLlm(
        [
            AIMessage(
                content="",
                tool_calls=[
                    _call(
                        "retrieve_medical_evidence",
                        {"query": "WBC cao nói chung có ý nghĩa gì?", "analyte": "WBC", "status": "HIGH"},
                        "c1",
                    )
                ],
            ),
            AIMessage(content="Nội dung không có căn cứ và không được phép hiển thị."),
        ]
    )
    monkeypatch.setattr("src.orchestrator.agent_v2.get_llm", lambda: llm)

    result = await run_agent_v2(
        message="WBC cao nói chung có ý nghĩa gì?",
        current_user=actor,
        db=object(),
        current_report_ref=None,
        current_analyte=None,
    )

    assert "chưa có đủ bằng chứng y khoa" in result.response.message
    assert "không có căn cứ" not in result.response.message


@pytest.mark.asyncio
async def test_feature_flag_delegates_existing_endpoint_service(monkeypatch):
    actor = SimpleNamespace(role="patient", user_id=7, username="patient")
    default_session_store.acknowledge_onboarding(actor)
    monkeypatch.setenv("AGENT_CHAT_V2", "true")
    get_settings.cache_clear()
    response = OrchestratorResponse(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        message="Phản hồi từ Agent V2.",
        data_type=DataType.EXPLANATION,
        data=ExplanationDataPayload(explanation="Phản hồi từ Agent V2."),
    )

    async def fake_agent(**_kwargs):
        return AgentV2Result(response, "21", "WBC", "get_indicator")

    monkeypatch.setattr("src.orchestrator.agent_v2.run_agent_v2", fake_agent)

    result = await handle_message(OrchestratorRequest(message="Giải thích WBC"), current_user=actor, db=object())

    assert result.message == "Phản hồi từ Agent V2."
    assert default_session_store.get_or_create(actor).current_analyte == "WBC"


@pytest.mark.asyncio
async def test_treatment_safety_blocks_before_agent_v2(monkeypatch):
    actor = SimpleNamespace(role="patient", user_id=7, username="patient")
    default_session_store.acknowledge_onboarding(actor)
    monkeypatch.setenv("AGENT_CHAT_V2", "true")
    get_settings.cache_clear()

    async def must_not_run(**_kwargs):
        raise AssertionError("Agent V2 must not run before the treatment gate")

    monkeypatch.setattr("src.orchestrator.agent_v2.run_agent_v2", must_not_run)
    result = await handle_message(
        OrchestratorRequest(message="Tôi nên uống thuốc gì để hạ WBC?"), current_user=actor, db=object()
    )

    assert result.status == ResponseStatus.BLOCKED
    assert result.reason_code is not None
    assert result.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE


@pytest.mark.asyncio
async def test_causal_followup_uses_trend_and_rag_without_personal_cause(monkeypatch):
    actor = SimpleNamespace(role="patient", user_id=7, username="patient")
    indicator = {
        "report_ref": "3",
        "test_date": "2026-08-20",
        "analyte": "WBC",
        "canonical_analyte": "WBC",
        "value": 15.0,
        "unit": "10^9/L",
        "status": "HIGH",
        "critical_status": "NOT_CRITICAL",
        "reference": {"low": 4.0, "high": 10.0, "operator": None, "display": "4.0–10.0 10^9/L"},
        "sources": [],
    }
    trend_payload = {
        "data_type": "trend",
        "trend": {
            "analyte_canonical": "WBC",
            "display_name": "WBC",
            "canonical_unit": "10^9/L",
            "filter": "latest5",
            "result_count": 3,
            "trend_available": True,
            "observed_direction": "increasing",
            "points": [
                {"report_id": 1, "test_date": "2026-06-10", "value": 7.8, "assessment": "normal"},
                {"report_id": 2, "test_date": "2026-07-12", "value": 9.2, "assessment": "normal"},
                {"report_id": 3, "test_date": "2026-08-20", "value": 15.0, "assessment": "high"},
            ],
        },
    }
    trend = {
        "analyte": "WBC",
        "trend_available": True,
        "point_count": 3,
        "direction": "INCREASING",
        "points": [],
        "latest": {"value": 15.0, "unit": "10^9/L", "status": "HIGH", "critical_status": "NOT_CRITICAL"},
        "reason_code": None,
        "_ui_trend_payload": trend_payload,
    }
    evidence = {
        "sufficient": True,
        "reason_code": None,
        "evidence": [
            {
                "evidence_id": "ev_wbc_1",
                "text": "Nhiều bối cảnh y khoa tổng quát được mô tả.",
                "source_url": "https://example.test/approved",
            }
        ],
    }
    monkeypatch.setattr(AgentToolbox, "get_indicator", lambda self, analyte, report_ref=None: indicator)
    monkeypatch.setattr(AgentToolbox, "get_indicator_trend", lambda self, analyte, window="latest5": trend)
    monkeypatch.setattr(
        AgentToolbox, "retrieve_medical_evidence", lambda self, query, analyte=None, status=None: evidence
    )
    first_turn_llm = ScriptedToolCallingLlm(
        [
            AIMessage(
                content="",
                tool_calls=[
                    _call("get_indicator", {"analyte": "WBC"}, "t1c1"),
                    _call(
                        "retrieve_medical_evidence",
                        {"query": "Giải thích WBC", "analyte": "WBC", "status": "HIGH"},
                        "t1c2",
                    ),
                ],
            ),
            AIMessage(
                content="WBC đang được đánh dấu cao. Tài liệu được phê duyệt cung cấp thông tin giáo dục tổng quát; kết quả này không tự xác lập chẩn đoán."
            ),
        ]
    )
    second_turn_llm = ScriptedToolCallingLlm(
        [
            AIMessage(
                content="",
                tool_calls=[
                    _call("get_indicator_trend", {"analyte": "WBC", "window": "latest5"}, "c1"),
                    _call(
                        "retrieve_medical_evidence",
                        {"query": "Tại sao WBC tăng?", "analyte": "WBC", "status": "HIGH"},
                        "c2",
                    ),
                ],
            ),
            AIMessage(
                content="Tài liệu được phê duyệt mô tả nhiều bối cảnh y khoa tổng quát có thể đi kèm WBC tăng. Không thể xác định nguyên nhân riêng của bạn chỉ từ kết quả xét nghiệm; cần trao đổi với bác sĩ để đánh giá thêm."
            ),
        ]
    )
    models = iter([first_turn_llm, second_turn_llm])
    monkeypatch.setattr("src.orchestrator.agent_v2.get_llm", lambda: next(models))

    first_turn = await run_agent_v2(
        message="Giải thích WBC của tôi", current_user=actor, db=object(), current_report_ref="3", current_analyte=None
    )
    result = await run_agent_v2(
        message="Tại sao lại tăng vậy?",
        current_user=actor,
        db=object(),
        current_report_ref=first_turn.current_report_ref,
        current_analyte=first_turn.current_analyte,
    )

    assert first_turn.current_analyte == "WBC"
    assert result.response.status == ResponseStatus.SUCCESS
    assert result.workflow_selected == "get_indicator_trend"
    assert result.response.sources == ["https://example.test/approved"]
    assert "Không thể xác định nguyên nhân riêng" in result.response.message
    assert "bạn bị nhiễm" not in result.response.message
    assert "uống thuốc" not in result.response.message


def test_agent_tool_cannot_read_another_patients_report(test_db):
    db, actor = _patient(test_db)
    try:
        other = User(username="patient_other", password_hash="not-used", role="patient")
        db.add(other)
        db.commit()
        db.refresh(other)
        foreign_report = _add_wbc(db, other.id, date(2026, 8, 20), 1234.0)

        with pytest.raises(OrchestratorWrapperError) as caught:
            AgentToolbox(actor, db).get_indicator("WBC", report_ref=str(foreign_report.id))

        assert caught.value.reason_code == ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED
        assert "1234" not in str(caught.value)
    finally:
        db.close()


@pytest.mark.asyncio
async def test_numeric_grounding_audit_warns_without_blocking(monkeypatch, caplog):
    actor = SimpleNamespace(role="patient", user_id=7, username="patient")
    llm = ScriptedToolCallingLlm([AIMessage(content="Giá trị được tạo ngoài công cụ là 999.")])
    monkeypatch.setattr("src.orchestrator.agent_v2.get_llm", lambda: llm)

    with caplog.at_level("WARNING", logger="src.orchestrator.agent_v2"):
        result = await run_agent_v2(
            message="Cho tôi biết kết quả",
            current_user=actor,
            db=object(),
            current_report_ref=None,
            current_analyte=None,
        )

    assert result.response.status == ResponseStatus.SUCCESS
    assert any(record.message == "agent_v2_numeric_grounding_warning" for record in caplog.records)
    warning = next(record for record in caplog.records if record.message == "agent_v2_numeric_grounding_warning")
    assert warning.unexpected_numbers == ["999"]


def test_normal_analyte_statement_remains_unchanged():
    message = "WBC của bạn nằm trong khoảng tham chiếu."
    results = [{"tool": "get_indicator", "ok": True, "data": {"status": "NORMAL"}}]

    assert validate_or_sanitize_patient_reassurance(message, results) == message


def test_not_critical_analyte_statement_remains_unchanged():
    message = "Giá trị WBC hiện không được hệ thống đánh dấu ở ngưỡng Critical."
    results = [
        {
            "tool": "get_indicator",
            "ok": True,
            "data": {"critical_status": "NOT_CRITICAL"},
        }
    ]

    assert validate_or_sanitize_patient_reassurance(message, results) == message


@pytest.mark.parametrize(
    "message, unsupported_claim",
    [
        (
            "WBC của bạn bình thường nên hiện không có tình trạng cấp cứu.",
            "không có tình trạng cấp cứu",
        ),
        (
            "WBC của bạn bình thường và không nằm trong tình trạng khẩn cấp.",
            "không nằm trong tình trạng khẩn cấp",
        ),
        (
            "WBC của bạn bình thường và không được phân loại là khẩn cấp.",
            "không được phân loại là khẩn cấp",
        ),
    ],
)
def test_emergency_inference_is_removed(message, unsupported_claim):
    results = [{"tool": "get_indicator", "ok": True, "data": {"status": "NORMAL"}}]

    sanitized = validate_or_sanitize_patient_reassurance(message, results)

    assert unsupported_claim not in sanitized
    assert "không thể kết luận" in sanitized


def test_immune_system_inference_is_removed():
    message = "Kết quả này cho thấy hệ miễn dịch của bạn đang hoạt động bình thường."
    results = [{"tool": "get_indicator", "ok": True, "data": {"status": "NORMAL"}}]

    sanitized = validate_or_sanitize_patient_reassurance(message, results)

    assert sanitized != message
    assert "hệ miễn dịch của bạn đang hoạt động bình thường" not in sanitized


def test_general_immune_system_education_remains_unchanged():
    message = "WBC là một thành phần của hệ miễn dịch."

    assert validate_or_sanitize_patient_reassurance(message, []) == message


def test_standalone_benign_nutrition_followup_is_not_treatment_blocked():
    session = SimpleNamespace(current_report_ref=None, current_analyte=None)

    assert medical_safety_gate("Ăn gì nhỉ") is None
    assert treatment_followup_gate("Ăn gì nhỉ", session) is None


@pytest.mark.asyncio
async def test_blocked_medication_turn_carries_into_short_diet_followup(test_db, monkeypatch):
    db = test_db.session()
    try:
        patient = db.query(User).filter(User.username == "benhnhan").one()
        actor = SimpleNamespace(role="patient", user_id=patient.id, username=patient.username)
        conversation = conversation_repository.create_conversation(db, patient_id=patient.id)
        store = ConversationScopedSessionStore()
        runtime = OrchestratorRuntime(session_store=store)
        with bind_conversation(db, conversation):
            store.acknowledge_onboarding(actor)

        async def must_not_run(**_kwargs):
            raise AssertionError("Contextual treatment follow-up must be blocked before Agent V2")

        monkeypatch.setattr("src.orchestrator.agent_v2.run_agent_v2", must_not_run)
        first = await handle_message(
            OrchestratorRequest(
                message="Tôi nên uống thuốc gì để hạ WBC?",
                conversation_id=conversation.id,
            ),
            current_user=actor,
            db=db,
            runtime=runtime,
            conversation=conversation,
        )
        second = await handle_message(
            OrchestratorRequest(message="Ăn gì nhỉ", conversation_id=conversation.id),
            current_user=actor,
            db=db,
            runtime=runtime,
            conversation=conversation,
        )

        assert first.reason_code == ReasonCode.TREATMENT_REQUEST
        assert second.reason_code == ReasonCode.TREATMENT_REQUEST
        assert all(food not in second.message.casefold() for food in ("rau", "cá hồi", "omega-3", "hạt chia"))
    finally:
        db.close()


def test_exact_live_emergency_reassurance_is_removed():
    message = (
        "Chỉ số WBC của bạn là 7.1 x 10^9/L. "
        "Giá trị này nằm trong khoảng tham chiếu bình thường từ 4.72 đến 11.3 x 10^9/L. "
        "Do đó, kết quả của bạn được phân loại là bình thường và không có tình trạng khẩn cấp."
    )

    sanitized = validate_or_sanitize_patient_reassurance(
        message,
        [{"tool": "get_indicator", "ok": True, "data": {"status": "NORMAL"}}],
    )

    assert "không có tình trạng khẩn cấp" not in sanitized
    assert "Giá trị này nằm trong khoảng tham chiếu" in sanitized
