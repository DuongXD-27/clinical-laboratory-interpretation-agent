"""ORCH-V1.4C - deterministic single-analyte fact composition.

Acceptance criteria:
- A10: mock/hostile composer LLM returning wrong facts -> composer NOT called,
  wrong content absent from final response.
- A11: authoritative HIGH non-critical indicator with misleading
  explanation/context mentioning "critical" -> no critical warning produced.
- A12: missing/incomplete reference bounds -> no fabricated two-sided range.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    DataType,
    ExplanationDataPayload,
    ExplanationIndicatorFacts,
    IntentEnum,
    ResponseStatus,
)
from src.models.schemas import CriticalAlertSchema, IndicatorResultSchema, LabReportDetailSchema
from src.orchestrator import response_composer
from src.orchestrator.dispatcher import DispatchContext, dispatch_workflow
from src.orchestrator.response_composer import (
    _compose_explanation_message,
    build_final_response,
)
from src.services import history_repository

HOSTILE_MESSAGE = "WBC 8.1 G/L cua ban hoan toan binh thuong, khong can lo lan."
HOSTILE_MESSAGE_VI = "WBC 8.1 G/L của bạn hoàn toàn bình thường, không cần lo lắng."


class HostileComposerLlm:
    """Composer LLM that must NEVER be reached for fact-bearing payloads."""

    def __init__(self) -> None:
        self.invocations = 0

    def with_structured_output(self, _schema):
        hostile = self

        class _Chain:
            async def ainvoke(self, _messages):
                hostile.invocations += 1
                return response_composer.ComposedMessage(message=HOSTILE_MESSAGE_VI)

        return _Chain()


def _facts(**overrides) -> ExplanationIndicatorFacts:
    values: dict = dict(
        analyte_name="WBC",
        value=12.3,
        unit="G/L",
        status="high",
        reference_low=4.0,
        reference_high=10.0,
        has_two_sided_reference_range=True,
        critical_status=None,
    )
    values.update(overrides)
    return ExplanationIndicatorFacts(**values)


def _payload(explanation: str, facts: ExplanationIndicatorFacts) -> ExplanationDataPayload:
    return ExplanationDataPayload(explanation=explanation, sources=["HD-BYT"], facts=facts)


# ---------------------------------------------------------------------------
# A10 - hostile composer output can never reach the final response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a10_hostile_composer_not_called_and_wrong_facts_absent(monkeypatch):
    llm = HostileComposerLlm()
    monkeypatch.setattr(response_composer, "get_llm", lambda: llm)

    data = _payload("Bạch cầu tăng nhẹ.", _facts())
    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        data=data,
    )

    # The general composer LLM must not be invoked at all on this path.
    assert llm.invocations == 0
    # Wrong value/status claims from the hostile composer are absent.
    assert "8.1" not in response.message
    assert "hoàn toàn bình thường" not in response.message
    # The deterministic fact block is present.
    assert "12.3 G/L" in response.message
    assert "Trạng thái: CAO" in response.message
    assert "Khoảng tham chiếu: 4.0 - 10.0 G/L" in response.message


@pytest.mark.asyncio
async def test_a10_hostile_statement_never_enters_final_response(monkeypatch):
    llm = HostileComposerLlm()
    monkeypatch.setattr(response_composer, "get_llm", lambda: llm)

    data = _payload("", _facts())
    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        data=data,
    )

    assert llm.invocations == 0
    assert HOSTILE_MESSAGE not in response.message
    assert HOSTILE_MESSAGE_VI not in response.message
    assert "CẢNH BÁO" not in response.message  # non-critical analyte


# ---------------------------------------------------------------------------
# A11 - HIGH non-critical never produces a critical warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a11_high_noncritical_produces_no_critical_warning(monkeypatch):
    llm = HostileComposerLlm()
    monkeypatch.setattr(response_composer, "get_llm", lambda: llm)

    misleading = "Chỉ số này đang cao. Đây là tình trạng nguy kịch cần xử trí ngay."
    data = _payload(misleading, _facts(status="high", critical_status=None))
    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        data=data,
    )

    assert llm.invocations == 0
    # No deterministic critical warning and no critical status label.
    assert "⚠️ CẢNH BÁO" not in response.message
    assert "NGUY KỊCH (" not in response.message
    # Authoritative status stays CAO.
    assert "Trạng thái: CAO" in response.message
    # Approved explanation prose is preserved verbatim (never rewritten).
    assert misleading in response.message


@pytest.mark.asyncio
async def test_a11_canonical_critical_still_warns():
    data = _payload("Kali máu cao.", _facts(critical_status="critical_high"))
    message = _compose_explanation_message(data)
    assert "⚠️ CẢNH BÁO" in message
    assert "Trạng thái: NGUY KỊCH (CAO)" in message


def test_a11_missing_authority_is_never_inferred():
    message = _compose_explanation_message(_payload("", _facts(critical_status=None)))
    assert "CẢNH BÁO" not in message
    assert "NGUY KỊCH" not in message


# ---------------------------------------------------------------------------
# A12 - missing/incomplete bounds never fabricate a range
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a12_missing_bound_no_fabricated_range(monkeypatch):
    llm = HostileComposerLlm()
    monkeypatch.setattr(response_composer, "get_llm", lambda: llm)

    data = _payload(
        "Chưa xác định được khoảng tham chiếu cho chỉ số này.",
        _facts(reference_high=None, has_two_sided_reference_range=False, status="unknown"),
    )
    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        data=data,
    )

    assert llm.invocations == 0
    assert "- Khoảng tham chiếu:" not in response.message
    assert "Trạng thái: CHƯA XÁC ĐỊNH (UNKNOWN)" in response.message
    assert "Giá trị: 12.3 G/L" in response.message
    assert "Chưa xác định được khoảng tham chiếu cho chỉ số này." in response.message


def test_a12_schema_rejects_inconsistent_range_flag():
    with pytest.raises(ValidationError):
        ExplanationIndicatorFacts(
            analyte_name="X",
            value=1.0,
            unit="u",
            status="high",
            reference_low=4.0,
            reference_high=None,
            has_two_sided_reference_range=True,
        )
    with pytest.raises(ValidationError):
        ExplanationIndicatorFacts(
            analyte_name="X",
            value=1.0,
            unit="u",
            status="high",
            reference_low=4.0,
            reference_high=10.0,
            has_two_sided_reference_range=False,
        )


# ---------------------------------------------------------------------------
# Dispatcher carries the canonical fact block (FIRST_DIVERGENCE fix)
# ---------------------------------------------------------------------------


class DummyPatient:
    def __init__(self):
        self.user_id = 101
        self.username = "test_patient"
        self.role = ROLE_PATIENT


def _detail() -> LabReportDetailSchema:
    return LabReportDetailSchema(
        id=42,
        patient_id=101,
        test_date=date(2026, 8, 15),
        created_at=datetime(2026, 8, 15, 10, 0, 0),
        status="normal",
        summary="Xét nghiệm máu tổng quát",
        has_critical_values=False,
        verification_status="verified",
        reviewed_by_doctor=True,
        language="vi",
        guardrail_passed=True,
        disclaimer="Tham khảo y khoa",
        indicators=[
            IndicatorResultSchema(
                name="WBC",
                value=12.3,
                unit="G/L",
                analyte_canonical="WBC",
                reference_low=4.0,
                reference_high=10.0,
                status="high",
                is_abnormal=True,
                is_critical=False,
                explanation="Bạch cầu tăng nhẹ so với khoảng tham chiếu.",
                sources=["HD-BYT"],
            ),
        ],
        critical_alerts=[],
    )


def _context(db) -> DispatchContext:
    return DispatchContext(
        current_user=DummyPatient(),
        db=db,
        current_report_ref="42",
        current_analyte="WBC",
    )


@pytest.mark.asyncio
async def test_dispatcher_mode_a_carries_authoritative_facts(monkeypatch):
    detail = _detail()
    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    result = await dispatch_workflow(IntentEnum.EXPLAIN_CURRENT_RESULT, _context(mock_db))

    assert result.status == ResponseStatus.SUCCESS
    facts = result.data.facts
    assert facts is not None
    assert facts.analyte_name == "WBC"
    assert facts.value == 12.3
    assert facts.unit == "G/L"
    assert facts.status == "high"
    assert facts.has_two_sided_reference_range is True
    assert facts.critical_status is None  # HIGH != CRITICAL
    assert result.data.explanation == "Bạch cầu tăng nhẹ so với khoảng tham chiếu."


@pytest.mark.asyncio
async def test_approved_critical_alert_message_preserved_verbatim(monkeypatch):
    llm = HostileComposerLlm()
    monkeypatch.setattr(response_composer, "get_llm", lambda: llm)
    detail = _detail()
    warning = "Chi so WBC tang toi nguong nguy kich (12.3 > 10.0 G/L). Yeu cau can thiep y te."
    detail.critical_alerts = [
        CriticalAlertSchema(
            indicator_name="WBC",
            value=12.3,
            unit="G/L",
            message=warning,
        )
    ]
    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    result = await dispatch_workflow(IntentEnum.EXPLAIN_CURRENT_RESULT, _context(mock_db))
    facts = result.data.facts
    assert facts.critical_status is None  # verdict is NEVER inferred from alert rows
    assert facts.approved_critical_message == warning

    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=result.status,
        data=result.data,
    )
    assert llm.invocations == 0
    assert f"⚠️ {warning}" in response.message


@pytest.mark.asyncio
async def test_dispatcher_carries_canonical_critical_verdict(monkeypatch):
    detail = _detail()
    detail.indicators[0] = detail.indicators[0].model_copy(update={"critical_status": "critical_high"})
    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    result = await dispatch_workflow(IntentEnum.EXPLAIN_CURRENT_RESULT, _context(mock_db))
    assert result.data.facts.critical_status == "critical_high"


@pytest.mark.asyncio
async def test_e2e_single_analyte_final_response_is_fact_block_plus_approved_prose(monkeypatch):
    llm = HostileComposerLlm()
    monkeypatch.setattr(response_composer, "get_llm", lambda: llm)
    detail = _detail()
    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    result = await dispatch_workflow(IntentEnum.EXPLAIN_CURRENT_RESULT, _context(mock_db))
    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=result.status,
        data=result.data,
    )

    assert llm.invocations == 0
    assert response.status == ResponseStatus.SUCCESS
    assert response.data_type == DataType.EXPLANATION
    assert "8.1" not in response.message
    assert "Kết quả WBC của bạn:" in response.message
    assert "Giá trị: 12.3 G/L" in response.message
    assert "Trạng thái: CAO" in response.message
    assert "Khoảng tham chiếu: 4.0 - 10.0 G/L" in response.message
    assert "Bạch cầu tăng nhẹ so với khoảng tham chiếu." in response.message
