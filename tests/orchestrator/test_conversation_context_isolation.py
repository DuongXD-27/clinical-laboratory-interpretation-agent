"""CP-05, CP-11, CP-12 — context gắn theo hội thoại, không rò sang hội thoại khác.

CP-05 là cổng quan trọng nhất của cả nhiệm vụ. Nó không phải "New Chat xoá giao
diện" mà là "New Chat không thừa hưởng `current_analyte` của hội thoại trước".

## Vì sao mỗi test ở đây đều có một vế đối chứng

"Không resolve ra WBC" cũng xanh khi bộ giải context hỏng hoàn toàn và chẳng
resolve ra gì. Nên mỗi khẳng định phủ định đi kèm một khẳng định khẳng định:
trong hội thoại A, cùng câu hỏi đó PHẢI resolve ra WBC. Thiếu vế đó thì test
chứng minh được rất ít.

## Cách gắn hội thoại trong file này

`bind_conversation` là context manager thường, nên test vào nó trực tiếp và gọi
`handle_message(..., conversation=None)`. Kết quả: store đọc/ghi context trên
hàng SQLite thật, còn phần y khoa vẫn dùng đúng mock sẵn có của G1. Nếu truyền
`conversation=` thì `handle_message` sẽ ghi transcript vào chính `db` giả kia —
lẫn hai chuyện vào một test.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.models.db import ROLE_PATIENT, User
from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorRequest,
    OrchestratorRole,
    OrchestratorSessionContext,
    ReasonCode,
    ResponseStatus,
)
from src.models.schemas import IndicatorResultSchema, LabReportDetailSchema
from src.orchestrator.medical_context import resolve_medical_context
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import (
    ConversationScopedSessionStore,
    bind_conversation,
)
from src.services import conversation_repository as repo
from src.services import history_repository

PATIENT_ID = 971
REPORT_REF = "401"


# --- helpers ----------------------------------------------------------------


@pytest.fixture
def db_session(test_db):
    with test_db.session() as session:
        session.add(
            User(
                id=PATIENT_ID,
                username="cp05.benhnhan",
                password_hash="x",
                role=ROLE_PATIENT,
            )
        )
        session.commit()
        yield session


def _patient() -> SimpleNamespace:
    return SimpleNamespace(user_id=PATIENT_ID, role=ROLE_PATIENT, username="cp05.benhnhan")


def _indicator(**overrides) -> IndicatorResultSchema:
    values = dict(
        name="WBC",
        value=12.0,
        unit="G/L",
        analyte_canonical="WBC",
        reference_low=4.0,
        reference_high=10.0,
        status="high",
        is_abnormal=True,
        is_critical=False,
        explanation="WBC cao hơn khoảng tham chiếu của phiếu này.",
        sources=["Approved WBC educational reference"],
    )
    values.update(overrides)
    return IndicatorResultSchema(**values)


def _detail(indicators=None) -> LabReportDetailSchema:
    return LabReportDetailSchema(
        id=int(REPORT_REF),
        patient_id=PATIENT_ID,
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
        indicators=indicators if indicators is not None else [_indicator()],
    )


def _mock_medical_db(monkeypatch, detail) -> MagicMock:
    mock_db = MagicMock()
    mock_db.scalar.return_value = PATIENT_ID
    report = MagicMock(id=int(REPORT_REF), patient_id=PATIENT_ID)
    monkeypatch.setattr(history_repository, "get_report", MagicMock(return_value=report))
    monkeypatch.setattr(history_repository, "to_detail", MagicMock(return_value=detail))
    return mock_db


def _session_of(conversation) -> OrchestratorSessionContext:
    """Context mà orchestrator sẽ thấy khi mở đúng hội thoại này."""

    return ConversationScopedSessionStore._hydrate(
        conversation,
        session_id=str(conversation.id),
        role=OrchestratorRole.PATIENT,
    )


# ---------------------------------------------------------------------------
# CP-05 — New Chat phải là cô lập context thật sự
# ---------------------------------------------------------------------------


def test_cp_05_new_chat_starts_with_a_structurally_empty_context(db_session):
    """Hội thoại A giữ WBC; hội thoại B sinh ra đã trống, không cần ai xoá."""

    user = _patient()
    store = ConversationScopedSessionStore()

    conv_a = repo.create_conversation(db_session, patient_id=PATIENT_ID)
    with bind_conversation(db_session, conv_a):
        session = store.acknowledge_onboarding(user)
        store.update_after_turn(
            user,
            session,
            last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
            current_report_ref=REPORT_REF,
            current_analyte="WBC",
        )

    # Context đã nằm trên hàng DB, không chỉ trong RAM.
    db_session.refresh(conv_a)
    assert conv_a.current_analyte == "WBC"
    assert conv_a.current_report_ref == REPORT_REF

    conv_b = repo.create_conversation(db_session, patient_id=PATIENT_ID)
    with bind_conversation(db_session, conv_b):
        fresh = store.get_or_create(user)

    assert fresh.current_analyte is None
    assert fresh.current_report_ref is None
    assert fresh.last_intent is None
    assert fresh.conversation_state.pending_question is None

    # Đối chứng: A vẫn còn nguyên. Nếu vế này hỏng thì "B trống" chỉ chứng minh
    # được là context bị xoá sạch ở đâu đó, chứ không phải bị cô lập.
    with bind_conversation(db_session, conv_a):
        again = store.get_or_create(user)
    assert again.current_analyte == "WBC"


def test_cp_05_referential_question_in_a_new_chat_must_not_resolve_wbc(db_session, monkeypatch):
    """Đúng kịch bản trong đề bài: "chỉ số này" ở hội thoại 2 không được ra WBC.

    Phiếu dùng ở đây có HAI chỉ số bất thường, nên bản thân phiếu không đủ để
    suy ra chỉ số nào. Con đường duy nhất để ra WBC là thừa hưởng từ hội thoại
    1 — nghĩa là test này đo đúng thứ cần đo, không đo hộ thứ khác.
    """

    user = _patient()
    store = ConversationScopedSessionStore()
    report = SimpleNamespace(
        patient_id=PATIENT_ID,
        indicators=[
            SimpleNamespace(name="WBC", analyte_canonical="WBC", status="high", critical_status=None),
            SimpleNamespace(name="HbA1c", analyte_canonical="HbA1c", status="high", critical_status=None),
        ],
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, report_id: report)

    conv_a = repo.create_conversation(db_session, patient_id=PATIENT_ID)
    with bind_conversation(db_session, conv_a):
        session = store.acknowledge_onboarding(user)
        store.update_after_turn(
            user,
            session,
            last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
            current_report_ref=REPORT_REF,
            current_analyte="WBC",
        )
    db_session.refresh(conv_a)

    conv_b = repo.create_conversation(db_session, patient_id=PATIENT_ID)

    resolved_b = resolve_medical_context(
        message="Giải thích kỹ hơn chỉ số này",
        session=_session_of(conv_b),
        ui_context=None,
        current_user=user,
        db=object(),
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )
    assert resolved_b.current_analyte is None, "WBC đã rò từ hội thoại 1 sang hội thoại 2"
    assert resolved_b.reason_code == ReasonCode.AMBIGUOUS_CONTEXT

    # Đối chứng: cùng câu hỏi đó, trong hội thoại 1, VẪN ra WBC.
    resolved_a = resolve_medical_context(
        message="Giải thích kỹ hơn chỉ số này",
        session=_session_of(conv_a),
        ui_context=None,
        current_user=user,
        db=object(),
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )
    assert resolved_a.current_analyte == "WBC"
    assert resolved_a.reason_code is None


@pytest.mark.asyncio
async def test_cp_05_end_to_end_new_chat_asks_which_indicator(db_session, monkeypatch):
    """Qua cả `handle_message`: hội thoại mới hỏi lại "chỉ số nào", không tự đoán WBC."""

    user = _patient()
    store = ConversationScopedSessionStore()
    report = SimpleNamespace(
        patient_id=PATIENT_ID,
        indicators=[
            SimpleNamespace(name="WBC", analyte_canonical="WBC", status="high", critical_status=None),
            SimpleNamespace(name="HbA1c", analyte_canonical="HbA1c", status="high", critical_status=None),
        ],
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, report_id: report)
    runtime = OrchestratorRuntime(session_store=store)

    conv_a = repo.create_conversation(db_session, patient_id=PATIENT_ID)
    with bind_conversation(db_session, conv_a):
        session = store.acknowledge_onboarding(user)
        store.update_after_turn(
            user,
            session,
            last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
            current_report_ref=REPORT_REF,
            current_analyte="WBC",
        )

    conv_b = repo.create_conversation(db_session, patient_id=PATIENT_ID)
    with bind_conversation(db_session, conv_b):
        store.acknowledge_onboarding(user)
        response = await handle_message(
            OrchestratorRequest(message="Giải thích kỹ hơn chỉ số này"),
            current_user=user,
            # DB THẬT, không phải `object()`.
            #
            # Bản đầu tôi truyền `object()` vì lúc đó `handle_message` không chạm
            # DB trên đường này — phần y khoa đã được monkeypatch. Sau đó ai đó
            # thêm `_immediately_previous_reason_code()`: orchestrator giờ đọc
            # transcript để biết mã lý do của lượt trước, một tính năng hợp lý,
            # và nó cần DB.
            #
            # Test đỏ đúng. Cái giả của tôi giả quá mức: nó khoá `handle_message`
            # vào một giả định về việc hàm đó chạm gì, chứ không vào hành vi mà
            # test muốn kiểm. Truyền session thật thì test chỉ còn khẳng định
            # đúng thứ nó nên khẳng định — New Chat không thừa hưởng WBC.
            db=db_session,
            runtime=runtime,
        )

    assert response.status == ResponseStatus.NEEDS_INPUT
    assert response.reason_code == ReasonCode.AMBIGUOUS_CONTEXT
    assert "chỉ số nào" in response.message.casefold()

    with bind_conversation(db_session, conv_b):
        assert store.get_or_create(user).current_analyte is None


def test_cp_05_isolation_holds_between_two_different_patients(db_session):
    """Hai bệnh nhân, hai hội thoại — context không đi qua ranh giới tài khoản.

    Trước đây store khoá theo `patient:{user_id}` nên chuyện này đã đúng sẵn.
    Vẫn ghim lại: khoá vừa đổi sang `conv:{id}`, và một khoá đặt sai sẽ làm
    context của người này hiện ra ở người kia — hỏng nặng hơn nhiều so với
    New Chat không sạch.
    """

    store = ConversationScopedSessionStore()
    db_session.add(User(id=PATIENT_ID + 1, username="cp05.khac", password_hash="x", role=ROLE_PATIENT))
    db_session.commit()

    user_a = _patient()
    user_b = SimpleNamespace(user_id=PATIENT_ID + 1, role=ROLE_PATIENT, username="cp05.khac")

    conv_a = repo.create_conversation(db_session, patient_id=PATIENT_ID)
    conv_b = repo.create_conversation(db_session, patient_id=PATIENT_ID + 1)

    with bind_conversation(db_session, conv_a):
        session = store.acknowledge_onboarding(user_a)
        store.update_after_turn(
            user_a,
            session,
            last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
            current_report_ref=REPORT_REF,
            current_analyte="WBC",
        )

    with bind_conversation(db_session, conv_b):
        assert store.get_or_create(user_b).current_analyte is None


# ---------------------------------------------------------------------------
# CP-11 — hỏi tiếp về nguồn, trong cùng một hội thoại
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cp_11_provenance_followup_still_works_inside_one_conversation(db_session, monkeypatch):
    """Chuỗi CRQ-014 hai lượt vẫn đúng khi context đi qua DB.

    Giữa hai lượt, cache trong tiến trình bị xoá sạch — mô phỏng lượt sau rơi
    vào worker khác, hoặc backend vừa khởi động lại. Lượt 2 vẫn trả lời được
    nghĩa là context thật sự sống ở hàng DB chứ không ở RAM.
    """

    user = _patient()
    store = ConversationScopedSessionStore()
    runtime = OrchestratorRuntime(session_store=store)
    mock_db = _mock_medical_db(monkeypatch, _detail())

    conv = repo.create_conversation(db_session, patient_id=PATIENT_ID)

    with bind_conversation(db_session, conv):
        store.acknowledge_onboarding(user)
        # Phiếu 401 là phiếu đang mở trong hội thoại này. Đi qua
        # `activate_report` chứ không gán thẳng cột: đó là API thật mà route
        # dùng, và nó còn xoá `current_analyte` của phiếu trước.
        store.activate_report(user, REPORT_REF)
        turn1 = await handle_message(
            OrchestratorRequest(message="Giải thích WBC giúp em"),
            current_user=user,
            db=mock_db,
            runtime=runtime,
        )
    assert turn1.status == ResponseStatus.SUCCESS

    db_session.refresh(conv)
    assert conv.current_analyte == "WBC"

    store.reset()

    with bind_conversation(db_session, conv):
        turn2 = await handle_message(
            OrchestratorRequest(message="Thông tin này dựa trên đâu?"),
            current_user=user,
            db=mock_db,
            runtime=runtime,
        )

    assert turn2.status == ResponseStatus.SUCCESS
    assert turn2.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
    assert "nguồn tham chiếu đã được duyệt" in turn2.message
    assert turn2.sources == ["Approved WBC educational reference"]
    assert turn2.message != turn1.message


@pytest.mark.asyncio
async def test_cp_11_provenance_followup_does_not_leak_into_a_new_chat(db_session, monkeypatch):
    """Và câu hỏi tiếp nối đó, đặt ở hội thoại mới, KHÔNG được trả lời về WBC."""

    user = _patient()
    store = ConversationScopedSessionStore()
    runtime = OrchestratorRuntime(session_store=store)
    mock_db = _mock_medical_db(monkeypatch, _detail())

    conv_a = repo.create_conversation(db_session, patient_id=PATIENT_ID)
    with bind_conversation(db_session, conv_a):
        store.acknowledge_onboarding(user)
        store.activate_report(user, REPORT_REF)
        await handle_message(
            OrchestratorRequest(message="Giải thích WBC giúp em"),
            current_user=user,
            db=mock_db,
            runtime=runtime,
        )

    conv_b = repo.create_conversation(db_session, patient_id=PATIENT_ID)
    with bind_conversation(db_session, conv_b):
        store.acknowledge_onboarding(user)
        response = await handle_message(
            OrchestratorRequest(message="Thông tin này dựa trên đâu?"),
            current_user=user,
            db=mock_db,
            runtime=runtime,
        )

    assert "Approved WBC educational reference" not in response.message


# ---------------------------------------------------------------------------
# CP-12 — HAL-039: hỏi tiếp "nên hỏi bác sĩ gì"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cp_12_doctor_question_followup_still_works_inside_one_conversation(db_session, monkeypatch):
    user = _patient()
    store = ConversationScopedSessionStore()
    runtime = OrchestratorRuntime(session_store=store)
    mock_db = _mock_medical_db(monkeypatch, _detail())

    conv = repo.create_conversation(db_session, patient_id=PATIENT_ID)

    with bind_conversation(db_session, conv):
        store.acknowledge_onboarding(user)
        store.activate_report(user, REPORT_REF)
        await handle_message(
            OrchestratorRequest(message="Giải thích WBC giúp em"),
            current_user=user,
            db=mock_db,
            runtime=runtime,
        )

    store.reset()

    with bind_conversation(db_session, conv):
        followup = await handle_message(
            OrchestratorRequest(message="Tôi nên hỏi bác sĩ những gì?"),
            current_user=user,
            db=mock_db,
            runtime=runtime,
        )

    # Không khẳng định nội dung câu hỏi: HAL-039 chỉ trả câu đã được duyệt của
    # phiếu, và phiếu giả ở đây không có câu nào. Điều cần chứng minh là luồng
    # vẫn định tuyến đúng qua context lấy từ DB, không rơi về BLOCKED.
    assert followup.intent == IntentEnum.GET_DOCTOR_QUESTIONS
    assert followup.status != ResponseStatus.BLOCKED

    db_session.refresh(conv)
    assert conv.last_intent == IntentEnum.GET_DOCTOR_QUESTIONS.value


# ---------------------------------------------------------------------------
# Vòng đời context: ghi xuống DB rồi đọc lại phải y nguyên
# ---------------------------------------------------------------------------


def test_context_round_trips_through_the_database_without_loss(db_session, test_db):
    """Mọi trường context được lưu phải trở về đúng như cũ sau khi restart.

    Đây là mắt xích mà CP-03, CP-11 và CP-12 đều dựa vào. Kiểm riêng để khi nó
    hỏng thì lỗi chỉ thẳng vào đây, thay vì hiện ra thành một câu trả lời sai ở
    tận lượt hội thoại thứ hai.
    """

    user = _patient()
    store = ConversationScopedSessionStore()
    conv = repo.create_conversation(db_session, patient_id=PATIENT_ID)

    with bind_conversation(db_session, conv):
        session = store.acknowledge_onboarding(user)
        store.update_after_turn(
            user,
            session,
            last_intent=IntentEnum.ANALYZE_TREND,
            current_report_ref=REPORT_REF,
            current_analyte="WBC",
        )

    conversation_id = conv.id
    db_session.close()
    test_db.restart()
    store.reset()

    with test_db.session() as reopened:
        row = repo.get_conversation(reopened, conversation_id=conversation_id, patient_id=PATIENT_ID)
        assert row is not None
        with bind_conversation(reopened, row):
            restored = store.get_or_create(user)

    assert restored.onboarding_acknowledged is True
    assert restored.current_report_ref == REPORT_REF
    assert restored.current_analyte == "WBC"
    assert restored.last_intent == IntentEnum.ANALYZE_TREND
    assert restored.user_role == OrchestratorRole.PATIENT
