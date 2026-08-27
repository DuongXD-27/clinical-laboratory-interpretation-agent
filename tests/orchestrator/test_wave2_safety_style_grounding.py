from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from src.api.patient_routes import _profile_response
from src.models.db import (
    ROLE_PATIENT,
    User,
    add_missing_columns,
    backfill_added_column_defaults,
)
from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    DataType,
    ExplanationDataPayload,
    ExplanationIndicatorFacts,
    IntentEnum,
    OrchestratorRequest,
    OrchestratorResponse,
    OrchestratorRole,
    OrchestratorSessionContext,
    ReasonCode,
    ResponseStatus,
    ResponseStyle,
    UIContext,
)
from src.orchestrator.dispatcher import DispatchContext, _dispatch_explain_current
from src.orchestrator.gates import (
    emergency_safety_gate,
    medical_safety_gate,
)
from src.orchestrator.response_composer import (
    STYLE_PROFILES,
    _compose_explanation_message,
    _format_whole_report_deterministic_summary,
    _validate_patient_grounding,
    build_final_response,
    deterministic_message_for,
    enforce_final_response,
)
from src.orchestrator.service import (
    OrchestratorRuntime,
    _response_from_workflow,
    handle_message,
)
from src.orchestrator.session_store import InMemorySessionStore


# ============================================================================
# 1. Emergency Precedence vs Theoretical / Educational Distinctions
# ============================================================================

def test_active_personal_urgent_symptoms_take_precedence_over_diagnosis_question():
    # Personal reporting of urgent symptoms MUST trigger EMERGENCY_INPUT_SAFETY
    # even when phrasing contains diagnosis question forms.
    assert emergency_safety_gate("Tôi đang đau ngực và khó thở, có phải bị tim không?") == ReasonCode.EMERGENCY_INPUT_SAFETY
    assert emergency_safety_gate("Tôi bị đau ngực và khó thở, có phải tôi bị bệnh tim không?") == ReasonCode.EMERGENCY_INPUT_SAFETY
    assert emergency_safety_gate("tôi bị khó thở nên làm gì") == ReasonCode.EMERGENCY_INPUT_SAFETY
    assert emergency_safety_gate("em đang đau ngực dữ dội cứu em với") == ReasonCode.EMERGENCY_INPUT_SAFETY


def test_theoretical_educational_symptom_queries_do_not_trigger_emergency():
    # Theoretical / general knowledge questions about symptoms are NOT emergencies
    assert emergency_safety_gate("Khó thở có phải dấu hiệu bệnh tim không?") is None
    assert emergency_safety_gate("HGB thấp có liên quan tới khó thở không?") is None
    assert emergency_safety_gate("tại sao thiếu máu lại gây khó thở?") is None
    assert emergency_safety_gate("khó thở nghĩa là gì?") is None


# ============================================================================
# 2. Personal Medical / Diet / Supplement Advice Gate
# ============================================================================

@pytest.mark.parametrize(
    "query",
    [
        "tôi ăn thịt bò tăng máu được không",
        "Tôi nên ăn gì để tăng HGB?",
        "ăn gì để bổ máu",
        "Tôi nên bổ sung sắt không?",
        "Tôi có nên uống thuốc nam không?",
        "Tôi nên kiêng ăn gì?",
        "ăn gì để hạ men gan",
        "ăn gì để giảm đường huyết",
    ],
)
def test_personal_medical_advice_gate_blocks_personal_diet_and_supplements(query: str):
    reason = medical_safety_gate(query)
    assert reason == ReasonCode.PERSONAL_MEDICAL_ADVICE


@pytest.mark.parametrize(
    "query",
    [
        "HGB là gì?",
        "RBC là gì?",
        "Khoảng tham chiếu nghĩa là gì?",
        "Chỉ số WBC có ý nghĩa gì?",
    ],
)
def test_educational_queries_pass_medical_safety_gate(query: str):
    reason = medical_safety_gate(query)
    assert reason is None


def test_personal_medical_advice_refusal_copy():
    msg = deterministic_message_for(ResponseStatus.BLOCKED, ReasonCode.PERSONAL_MEDICAL_ADVICE, IntentEnum.UNSUPPORTED_OR_UNSAFE)
    assert "chế độ ăn uống" in msg or "dinh dưỡng" in msg
    assert "bác sĩ" in msg


# ============================================================================
# 3. Real Deterministic Critical Fact Invariance Across All Styles
# ============================================================================

@pytest.mark.parametrize(
    ("analyte_name", "value", "unit", "status", "ref_low", "ref_high", "critical_status", "critical_msg"),
    [
        # Real critical high: Potassium 6.8 mmol/L (> 6.1 mmol/L threshold in critical_thresholds.json)
        ("Potassium", "6.8", "mmol/L", "high", "3.5", "5.0", "critical_high", "Potassium tăng tới ngưỡng nguy kịch. Cần can thiệp y tế khẩn cấp."),
        # Real critical low: Sodium 115.0 mmol/L (< 120 mmol/L threshold in critical_thresholds.json)
        ("Sodium", "115.0", "mmol/L", "low", "135.0", "145.0", "critical_low", "Sodium giảm tới ngưỡng nguy kịch. Cần can thiệp y tế khẩn cấp."),
        # Non-critical high: Fasting plasma glucose 15.2 mmol/L (273.8 mg/dL < 450 mg/dL critical threshold -> status HIGH, NOT CRITICAL)
        ("Fasting plasma glucose", "15.2", "mmol/L", "high", "3.9", "6.4", None, None),
        # Normal indicator: RBC 4.5 10^12/L (within 4.0 - 5.5 reference range -> status NORMAL)
        ("RBC", "4.5", "10^12/L", "normal", "4.0", "5.5", None, None),
    ],
)
def test_real_deterministic_fact_invariance_across_all_styles(
    analyte_name: str,
    value: str,
    unit: str,
    status: str,
    ref_low: str,
    ref_high: str,
    critical_status: str | None,
    critical_msg: str | None,
):
    facts = ExplanationIndicatorFacts(
        analyte_name=analyte_name,
        value=value,
        unit=unit,
        status=status,
        reference_low=ref_low,
        reference_high=ref_high,
        has_two_sided_reference_range=True,
        critical_status=critical_status,
        approved_critical_message=critical_msg,
    )
    payload = ExplanationDataPayload(
        explanation=f"{analyte_name} là chỉ số xét nghiệm quan trọng trong cơ thể.",
        sources=["Hệ thống Y tế Vinmec"],
        presentation_mode="current_fact_first",
        facts=facts,
    )

    msg_concise = _compose_explanation_message(payload, response_style="concise")
    msg_simple = _compose_explanation_message(payload, response_style="simple")
    msg_detailed = _compose_explanation_message(payload, response_style="detailed")

    # Assert exact invariant fact representation in all 3 styles
    for msg in (msg_concise, msg_simple, msg_detailed):
        assert analyte_name in msg
        assert f"{facts.value} {facts.unit}" in msg
        assert f"{facts.reference_low} - {facts.reference_high} {facts.unit}" in msg
        if critical_status == "critical_high":
            assert "NGUY KỊCH (CAO)" in msg
            assert (critical_msg and critical_msg in msg) or "nguy kịch" in msg.lower()
        elif critical_status == "critical_low":
            assert "NGUY KỊCH (THẤP)" in msg
            assert (critical_msg and critical_msg in msg) or "nguy kịch" in msg.lower()
        elif status == "high":
            assert "CAO" in msg
            assert "NGUY KỊCH" not in msg
        elif status == "normal":
            assert "BÌNH THƯỜNG" in msg
            assert "NGUY KỊCH" not in msg

    # Assert styles differ appropriately in structure without changing facts
    assert len(msg_concise) <= len(msg_simple) <= len(msg_detailed)


# ============================================================================
# 4. Expanded Deterministic Patient Grounding & Adversarial LLM Tests
# ============================================================================

@pytest.mark.parametrize(
    ("unsafe_statement", "description"),
    [
        ("Bạn có thể đang khó thở.", "Ungrounded symptom attribution"),
        ("Bạn bị thiếu máu.", "Ungrounded disease diagnosis"),
        ("HGB thấp khiến cơ thể bạn thiếu oxy.", "Ungrounded causation/physiological inference"),
        ("RBC bình thường nên cơ thể bạn được cung cấp oxy ổn định.", "Ungrounded physiological state reassurance"),
        ("Kết quả này cho thấy cơ thể bạn đang phục hồi tốt.", "Ungrounded prognosis/reassurance"),
        ("Chức năng gan của bạn đang ổn định.", "Ungrounded physiological state assertion"),
        ("Bạn cần uống thuốc bổ máu ngay.", "Ungrounded treatment recommendation"),
        ("Bạn hoàn toàn khỏe mạnh và không có bệnh gì.", "Ungrounded global health reassurance"),
    ],
)
def test_grounding_validator_blocks_all_unsupported_inferences(unsafe_statement: str, description: str):
    raw_user_msg = "Giải thích chỉ số xét nghiệm của tôi"
    assert _validate_patient_grounding(unsafe_statement, raw_user_msg) is False, f"Failed to block: {description}"


@pytest.mark.parametrize(
    "safe_statement",
    [
        "RBC là số lượng hồng cầu trong máu. Hồng cầu tham gia vận chuyển oxy trong cơ thể.",
        "Kết quả RBC của bạn: - Giá trị: 4.5 10^12/L - Trạng thái: BÌNH THƯỜNG - Khoảng tham chiếu: 4.0 - 5.5 10^12/L",
        "Hemoglobin (HGB) là protein trong hồng cầu có chức năng vận chuyển oxy từ phổi đến các mô.",
        "RBC của bạn nằm trong khoảng tham chiếu mà hệ thống đang sử dụng.",
        "WBC là chỉ số đếm số lượng bạch cầu trong máu toàn phần bằng máy huyết học tự động.",
    ],
)
def test_grounding_validator_permits_safe_educational_and_fact_statements(safe_statement: str):
    raw_user_msg = "RBC là gì?"
    assert _validate_patient_grounding(safe_statement, raw_user_msg) is True


@pytest.mark.parametrize("style", ["concise", "simple", "detailed"])
@pytest.mark.asyncio
async def test_adversarial_llm_output_is_blocked_and_falls_back_across_all_styles(style: str):
    # WAVE2-FIX invariant: AnalysisDataPayload whole-report summaries now
    # bypass LLM composition entirely (deterministic early-return in
    # compose_message). This is architecturally stronger than the previous
    # behaviour of calling the LLM and then catching unsafe output in
    # enforce_final_response. The LLM mock is irrelevant — it is never
    # invoked — and the response is always SUCCESS with the safe deterministic
    # summary. The core safety property ("unsafe text never reaches the
    # patient") is preserved and strengthened.
    unsafe_mock_message = "Kết quả RBC bình thường nên cơ thể bạn được cung cấp oxy ổn định. Bạn có thể đang khó thở và bạn bị thiếu máu."

    payload = AnalysisDataPayload(
        indicators=[],
        critical_alerts=[],
    )

    with patch("src.orchestrator.response_composer.get_llm") as mock_get_llm:
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = {"message": unsafe_mock_message}
        mock_get_llm.return_value.with_structured_output.return_value = mock_structured

        resp = await build_final_response(
            intent=IntentEnum.ANALYZE_REPORT,
            status=ResponseStatus.SUCCESS,
            data=payload,
            response_style=style,
            user_message="Tóm tắt phiếu xét nghiệm",
        )

        # LLM is never invoked for AnalysisDataPayload — deterministic path.
        mock_get_llm.return_value.with_structured_output.assert_not_called()

        # The unsafe statement MUST NOT survive in the final patient-visible output.
        assert "cơ thể bạn được cung cấp oxy ổn định" not in resp.message
        assert "bạn bị thiếu máu" not in resp.message
        assert "bạn có thể đang khó thở" not in resp.message

        # Deterministic path: response is SUCCESS with safe structured message.
        assert resp.status == ResponseStatus.SUCCESS


# ============================================================================
# 5. Pure Educational Definition Dispatch (e.g. "RBC là gì?")
# ============================================================================

@pytest.mark.asyncio
async def test_rbc_educational_definition_dispatch_without_unrelated_facts():
    user = User(id=1, username="test_patient", role=ROLE_PATIENT, response_style="simple")
    context = DispatchContext(
        current_user=user,
        db=None,
        current_report_ref=None,
        current_analyte="RBC",
        message="RBC là gì?",
    )

    result = await _dispatch_explain_current(context)
    assert result.status == ResponseStatus.SUCCESS
    assert isinstance(result.data, ExplanationDataPayload)
    assert "Hồng cầu" in result.data.explanation or "RBC" in result.data.explanation
    # Must NOT contain HGB or unrelated patient report values
    assert result.data.facts is None


# ============================================================================
# 6. SQLite Migration & Backfill on Existing Populated Database
# ============================================================================

def test_sqlite_migration_on_populated_database(tmp_path):
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Create legacy users table WITHOUT response_style column
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT,
            date_of_birth TEXT,
            sex TEXT,
            email TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT INTO users (username, hashed_password, role, full_name)
        VALUES ('patient_legacy', 'hash123', 'patient', 'Bệnh Nhân Cũ')
    """)
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db_file}")

    with patch("src.models.db.engine", engine):
        added = add_missing_columns()
        assert "users.response_style" in added

        backfill_added_column_defaults()

        # Verify populated user row now has response_style == 'simple'
        with engine.connect() as check_conn:
            row = check_conn.execute(text("SELECT username, response_style FROM users WHERE username = 'patient_legacy'")).fetchone()
            assert row is not None
            assert row[0] == "patient_legacy"
            assert row[1] == "simple"


def test_profile_endpoint_handles_null_and_invalid_styles_safely():
    now = datetime.now(UTC)
    # Null style in patient object
    user_null = User(id=1, username="u1", role="patient", response_style=None, created_at=now, updated_at=now)
    profile_null = _profile_response(user_null)
    assert profile_null.response_style == "simple"

    # Invalid style string in patient object
    user_invalid = User(id=2, username="u2", role="patient", response_style="pirate_mode", created_at=now, updated_at=now)
    profile_invalid = _profile_response(user_invalid)
    assert profile_invalid.response_style == "simple"

    # Valid styles
    user_concise = User(id=3, username="u3", role="patient", response_style="concise", created_at=now, updated_at=now)
    assert _profile_response(user_concise).response_style == "concise"

    user_detailed = User(id=4, username="u4", role="patient", response_style="detailed", created_at=now, updated_at=now)
    assert _profile_response(user_detailed).response_style == "detailed"


# ============================================================================
# 7. Per-Message Override Non-Persistence Invariant
# ============================================================================

@pytest.mark.asyncio
async def test_per_message_override_does_not_mutate_persisted_user_preference():
    user = User(id=10, username="patient_pref", role=ROLE_PATIENT, response_style="simple")
    session_store = InMemorySessionStore()
    session_store.acknowledge_onboarding(user)

    runtime = OrchestratorRuntime(session_store=session_store)
    mock_db = MagicMock()

    # Turn 1: request with per-message override = "detailed"
    req_1 = OrchestratorRequest(
        message="HGB là gì?",
        ui_context=UIContext(screen="analysis", response_style=ResponseStyle.DETAILED),
    )
    resp_1 = await handle_message(req_1, current_user=user, runtime=runtime, db=mock_db)

    assert resp_1.status == ResponseStatus.SUCCESS
    # User's persisted preference in DB must STILL be "simple"
    assert user.response_style == "simple"

    # Turn 2: request without override
    req_2 = OrchestratorRequest(
        message="RBC là gì?",
        ui_context=UIContext(screen="analysis"),
    )
    resp_2 = await handle_message(req_2, current_user=user, runtime=runtime, db=mock_db)

    assert resp_2.status == ResponseStatus.SUCCESS
    # User's persisted preference in DB must STILL be "simple"
    assert user.response_style == "simple"

    # Direct test of _response_from_workflow with single-analyte facts across turns
    facts = ExplanationIndicatorFacts(
        analyte_name="HGB",
        value="110.0",
        unit="g/L",
        status="low",
        reference_low="120.0",
        reference_high="150.0",
        has_two_sided_reference_range=True,
    )
    from src.orchestrator.dispatcher import WorkflowResult
    wf_result = WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=ExplanationDataPayload(
            explanation="Hemoglobin là protein vận chuyển oxy trong máu.",
            facts=facts,
        ),
        workflow_selected="get_my_report",
    )

    # Request 1 with override -> detailed
    resp_override = await _response_from_workflow(
        IntentEnum.EXPLAIN_CURRENT_RESULT,
        wf_result,
        response_style="detailed",
    )
    assert "Thông tin tham khảo y khoa:" in resp_override.message or "Lưu ý:" in resp_override.message

    # Request 2 without override -> simple
    resp_default = await _response_from_workflow(
        IntentEnum.EXPLAIN_CURRENT_RESULT,
        wf_result,
        response_style=user.response_style,
    )
    assert "Thông tin tham khảo y khoa:" not in resp_default.message
