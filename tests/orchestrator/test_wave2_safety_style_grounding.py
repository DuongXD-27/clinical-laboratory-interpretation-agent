from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.models.db import Base, User, ROLE_PATIENT, backfill_added_column_defaults
from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    DataType,
    ExplanationDataPayload,
    ExplanationIndicatorFacts,
    IntentEnum,
    OrchestratorRequest,
    OrchestratorResponse,
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
from src.orchestrator.service import _response_from_workflow, handle_message


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
# 3. Response Style Variations & Fact Invariance
# ============================================================================

def test_single_analyte_fact_invariance_across_all_styles():
    facts = ExplanationIndicatorFacts(
        analyte_name="Hemoglobin (HGB)",
        value="110",
        unit="g/L",
        status="low",
        reference_low="120",
        reference_high="150",
        has_two_sided_reference_range=True,
        critical_status=None,
        approved_critical_message=None,
    )
    payload = ExplanationDataPayload(
        explanation="Hemoglobin là protein vận chuyển oxy trong máu. Chỉ số này phản ánh lượng hồng cầu trong cơ thể.",
        sources=["Bộ Y Tế"],
        presentation_mode="current_fact_first",
        facts=facts,
    )

    msg_concise = _compose_explanation_message(payload, response_style="concise")
    msg_simple = _compose_explanation_message(payload, response_style="simple")
    msg_detailed = _compose_explanation_message(payload, response_style="detailed")

    # Invariant facts check across all 3 styles
    for msg in (msg_concise, msg_simple, msg_detailed):
        assert "Hemoglobin (HGB)" in msg
        assert f"{facts.value} {facts.unit}" in msg
        assert "THẤP" in msg
        assert f"{facts.reference_low} - {facts.reference_high} {facts.unit}" in msg

    # Style differentiation check
    assert len(msg_concise) < len(msg_simple)
    assert len(msg_simple) < len(msg_detailed)
    assert "Thông tin tham khảo y khoa:" in msg_detailed or "Lưu ý:" in msg_detailed


def test_detailed_style_preserves_safety_invariants_and_never_diagnoses():
    facts = ExplanationIndicatorFacts(
        analyte_name="Glucose",
        value="15.2",
        unit="mmol/L",
        status="high",
        reference_low="3.9",
        reference_high="6.4",
        has_two_sided_reference_range=True,
        critical_status="critical_high",
        approved_critical_message="Cần liên hệ bác sĩ ngay lập tức.",
    )
    payload = ExplanationDataPayload(
        explanation="Glucose là đường trong máu phản ánh mức năng lượng của cơ thể.",
        sources=["Hội Nội tiết"],
        presentation_mode="status_first",
        facts=facts,
    )

    msg_detailed = _compose_explanation_message(payload, response_style="detailed")
    assert "NGUY KỊCH (CAO)" in msg_detailed
    assert "15.2 mmol/L" in msg_detailed
    # Never diagnose diabetes or prescribe insulin
    assert "bạn bị tiểu đường" not in msg_detailed.lower()
    assert "uống thuốc" not in msg_detailed.lower()


# ============================================================================
# 4. Deterministic Patient Grounding
# ============================================================================

def test_grounding_validator_catches_unreported_symptoms():
    # User only asked about HGB, didn't report shortness of breath
    raw_user_msg = "Giải thích chỉ số HGB của tôi"
    hallucinated_msg = "Chỉ số HGB của bạn thấp, bạn đang bị khó thở và mệt mỏi."

    assert _validate_patient_grounding(hallucinated_msg, raw_user_msg) is False


def test_grounding_validator_allows_symptoms_explicitly_reported_by_patient():
    raw_user_msg = "Tôi đang bị khó thở và mệt mỏi, giải thích giúp tôi"
    grounded_msg = "Bạn đang bị khó thở và mệt mỏi, điều này có thể liên quan đến các vấn đề sức khỏe tổng quát."

    assert _validate_patient_grounding(grounded_msg, raw_user_msg) is True


def test_grounding_validator_rejects_disease_diagnosis():
    raw_user_msg = "Xem kết quả máu của tôi"
    diagnosis_msg = "Dựa trên kết quả này, bạn bị thiếu máu nặng."

    assert _validate_patient_grounding(diagnosis_msg, raw_user_msg) is False


def test_enforce_final_response_blocks_ungrounded_response():
    resp = OrchestratorResponse(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        message="Kết quả của bạn cho thấy bạn đang bị khó thở và bạn bị thiếu máu.",
        data_type=DataType.EXPLANATION,
        data=ExplanationDataPayload(explanation=""),
    )
    enforced = enforce_final_response(resp, user_message="Giải thích kết quả")
    assert enforced.status == ResponseStatus.BLOCKED
    assert enforced.reason_code == ReasonCode.GUARDRAIL_BLOCKED


# ============================================================================
# 5. Pure Educational Definition Dispatch (e.g. "RBC là gì?")
# ============================================================================

@pytest.mark.asyncio
async def test_rbc_educational_definition_dispatch_without_unrelated_facts():
    # Mock user and empty DB
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

    # Now connect via SQLAlchemy engine pointing to the legacy DB
    engine = create_engine(f"sqlite:///{db_file}")
    SessionLocal = sessionmaker(bind=engine)

    # Patch engine in db module
    with patch("src.models.db.engine", engine):
        from src.models.db import add_missing_columns
        added = add_missing_columns()
        assert "users.response_style" in added

        # Backfill
        backfill_added_column_defaults()

        # Verify populated user row now has response_style == 'simple'
        with engine.connect() as check_conn:
            row = check_conn.execute(text("SELECT username, response_style FROM users WHERE username = 'patient_legacy'")).fetchone()
            assert row is not None
            assert row[0] == "patient_legacy"
            assert row[1] == "simple"
