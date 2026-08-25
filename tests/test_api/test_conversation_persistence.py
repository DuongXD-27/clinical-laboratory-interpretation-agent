"""Conversation Persistence & New Chat — nghiệm thu CP-01..CP-04, CP-06..CP-10.

CP-05, CP-11 và CP-12 nằm ở `tests/orchestrator/test_conversation_context_isolation.py`
vì chúng nói về context của orchestrator chứ không về hợp đồng HTTP.

## Vì sao stub `_handle_message_core` chứ không stub `handle_message`

Việc lưu transcript nằm trong chính `handle_message`. Stub nó đi là stub luôn
thứ đang cần kiểm. Stub phần lõi bên dưới thì lớp bọc vẫn chạy thật: vẫn gắn
hội thoại, vẫn ghi hai lượt, vẫn cập nhật tiêu đề — đúng khuôn với quy ước sẵn
có của repo là monkeypatch `routes.agent.ainvoke` thay vì chạy cả graph.
"""

from __future__ import annotations

import pytest

from src.models.orchestrator_schemas import (
    DataType,
    ExplanationDataPayload,
    IntentEnum,
    OrchestratorResponse,
    ResponseStatus,
)
from src.orchestrator import service as orchestrator_service

ANSWER = "WBC của bạn là 12.5 10^9/L, cao hơn khoảng tham chiếu."


def _canned_response(message: str = ANSWER) -> OrchestratorResponse:
    return OrchestratorResponse(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        message=message,
        data_type=DataType.EXPLANATION,
        data=ExplanationDataPayload(explanation=message),
    )


@pytest.fixture
def stub_core(monkeypatch):
    """Thay phần lõi orchestrator bằng câu trả lời cố định.

    Trả về danh sách các câu hỏi đã đi qua, để test chứng minh được lõi thật sự
    được gọi — chứ không phải endpoint trả 200 mà chẳng làm gì.
    """

    seen: list[str] = []

    async def _fake_core(request, **kwargs):
        seen.append(request.message)
        return _canned_response(f"Trả lời cho: {request.message}")

    monkeypatch.setattr(orchestrator_service, "_handle_message_core", _fake_core)
    return seen


async def _register(client, username: str, password: str = "matkhau123"):
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201, response.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _guest(client):
    response = await client.post("/api/v1/auth/guest")
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _say(client, headers, message: str, conversation_id: int | None = None):
    payload: dict = {"message": message}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    return await client.post("/api/v1/orchestrator/message", headers=headers, json=payload)


# --- CP-01: tạo hội thoại -> được lưu ---------------------------------------


@pytest.mark.asyncio
async def test_cp_01_patient_creates_conversation_and_it_is_saved(client):
    headers = await _register(client, "cp01.duy")

    created = await client.post("/api/v1/conversations", headers=headers, json={})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    listed = await client.get("/api/v1/conversations", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [conversation_id]


# --- CP-02: gửi tin nhắn -> được lưu ----------------------------------------


@pytest.mark.asyncio
async def test_cp_02_messages_are_persisted_with_both_roles(client, stub_core):
    headers = await _register(client, "cp02.duy")
    conversation_id = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]

    response = await _say(client, headers, "WBC của tôi là bao nhiêu?", conversation_id)
    assert response.status_code == 200, response.text
    assert stub_core == ["WBC của tôi là bao nhiêu?"]

    detail = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    messages = detail.json()["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "WBC của tôi là bao nhiêu?"
    assert messages[1]["content"] == "Trả lời cho: WBC của tôi là bao nhiêu?"
    # Metadata của lượt trợ lý phải đủ để dựng lại giao diện khi tải lại trang.
    assert messages[1]["intent"] == IntentEnum.EXPLAIN_CURRENT_RESULT.value
    assert messages[1]["data_type"] == DataType.EXPLANATION.value


@pytest.mark.asyncio
async def test_cp_02_first_question_becomes_the_title(client, stub_core):
    headers = await _register(client, "cp02b.duy")
    conversation_id = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]

    await _say(client, headers, "Chỉ số WBC nghĩa là gì?", conversation_id)
    await _say(client, headers, "Còn LDL thì sao?", conversation_id)

    listed = await client.get("/api/v1/conversations", headers=headers)
    # Câu đầu tiên đặt tên, câu thứ hai không đổi tên nữa — nếu không, nhãn
    # trong danh sách nhảy sau mỗi lượt và không còn nhận ra hội thoại nào.
    assert listed.json()["items"][0]["title"] == "Chỉ số WBC nghĩa là gì?"


# --- CP-03: tải lại -> transcript nguyên vẹn ---------------------------------


@pytest.mark.asyncio
async def test_cp_03_transcript_survives_a_backend_restart(client, stub_core, test_db):
    """Tải lại trang, và mạnh hơn: khởi động lại backend.

    `test_db.restart()` đóng sạch connection rồi mở lại từ chính file đó. Test
    này đỏ nếu transcript chỉ nằm trong bộ nhớ — đó là điểm chứng minh dữ liệu
    thật sự được lưu, không phải chỉ còn sống nhờ tiến trình chưa chết.
    """

    headers = await _register(client, "cp03.duy")
    conversation_id = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]
    await _say(client, headers, "Giải thích chỉ số WBC", conversation_id)
    await _say(client, headers, "Vậy tôi nên làm gì?", conversation_id)

    test_db.restart()

    detail = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    contents = [m["content"] for m in detail.json()["messages"]]
    assert contents == [
        "Giải thích chỉ số WBC",
        "Trả lời cho: Giải thích chỉ số WBC",
        "Vậy tôi nên làm gì?",
        "Trả lời cho: Vậy tôi nên làm gì?",
    ]


# --- CP-04: New Chat -> hội thoại B, transcript trống ------------------------


@pytest.mark.asyncio
async def test_cp_04_new_chat_creates_a_second_conversation_with_empty_transcript(client, stub_core):
    headers = await _register(client, "cp04.duy")
    first = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]
    await _say(client, headers, "Giải thích chỉ số WBC", first)

    second = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]
    assert second != first

    detail = await client.get(f"/api/v1/conversations/{second}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["messages"] == []
    assert detail.json()["conversation"]["title"] is None

    listed = await client.get("/api/v1/conversations", headers=headers)
    assert listed.json()["total"] == 2


# --- CP-06: quay lại hội thoại cũ -> transcript đúng -------------------------


@pytest.mark.asyncio
async def test_cp_06_switching_back_restores_the_right_transcript(client, stub_core):
    headers = await _register(client, "cp06.duy")
    first = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]
    await _say(client, headers, "Câu hỏi thuộc hội thoại một", first)

    second = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]
    await _say(client, headers, "Câu hỏi thuộc hội thoại hai", second)

    back = await client.get(f"/api/v1/conversations/{first}", headers=headers)
    contents = [m["content"] for m in back.json()["messages"]]
    assert contents == [
        "Câu hỏi thuộc hội thoại một",
        "Trả lời cho: Câu hỏi thuộc hội thoại một",
    ]
    # Và không lẫn sang hội thoại kia theo chiều nào cả.
    assert all("hội thoại hai" not in c for c in contents)


# --- CP-07: bệnh nhân A đọc hội thoại của bệnh nhân B -> chặn ----------------


@pytest.mark.asyncio
async def test_cp_07_patient_a_cannot_read_patient_b_conversation(client, stub_core):
    headers_b = await _register(client, "cp07.benhnhan.b")
    owned = (await client.post("/api/v1/conversations", headers=headers_b, json={})).json()["id"]
    await _say(client, headers_b, "Nội dung riêng tư của bệnh nhân B", owned)

    headers_a = await _register(client, "cp07.benhnhan.a")
    stolen = await client.get(f"/api/v1/conversations/{owned}", headers=headers_a)

    # 404 chứ không 403: 403 xác nhận id đó tồn tại, đủ để dò ra hội thoại của
    # người khác bằng cách thử id. Cùng quy tắc với /history/{report_id}.
    assert stolen.status_code == 404, stolen.text
    assert "Nội dung riêng tư" not in stolen.text

    # Và hội thoại đó không hiện trong danh sách của A.
    listed = await client.get("/api/v1/conversations", headers=headers_a)
    assert listed.json()["total"] == 0


@pytest.mark.asyncio
async def test_cp_07_patient_a_cannot_chat_into_patient_b_conversation(client, stub_core):
    """Chặn cả chiều GHI, không chỉ chiều đọc.

    Chỉ chặn đọc thì A vẫn chèn được lượt vào hội thoại của B, và B mở ra thấy
    tin nhắn không phải của mình — hỏng còn nặng hơn đọc lỏm.
    """

    headers_b = await _register(client, "cp07w.benhnhan.b")
    owned = (await client.post("/api/v1/conversations", headers=headers_b, json={})).json()["id"]

    headers_a = await _register(client, "cp07w.benhnhan.a")
    intrusion = await _say(client, headers_a, "Chèn vào hội thoại của người khác", owned)
    assert intrusion.status_code == 404, intrusion.text
    assert stub_core == []

    detail = await client.get(f"/api/v1/conversations/{owned}", headers=headers_b)
    assert detail.json()["messages"] == []


# --- CP-08: bệnh nhân A đọc tin nhắn của bệnh nhân B -> chặn -----------------


@pytest.mark.asyncio
async def test_cp_08_patient_a_cannot_read_patient_b_messages(client, stub_core):
    headers_b = await _register(client, "cp08.benhnhan.b")
    owned = (await client.post("/api/v1/conversations", headers=headers_b, json={})).json()["id"]
    await _say(client, headers_b, "Kết quả xét nghiệm riêng của bệnh nhân B", owned)

    headers_a = await _register(client, "cp08.benhnhan.a")
    stolen = await client.get(f"/api/v1/conversations/{owned}/messages", headers=headers_a)

    assert stolen.status_code == 404, stolen.text
    assert "riêng của bệnh nhân B" not in stolen.text

    # Chứng cứ đối chứng: chính chủ đọc được. Không có dòng này thì "không lộ"
    # cũng xanh trong trường hợp endpoint hỏng và chẳng trả gì cho ai.
    owner_view = await client.get(f"/api/v1/conversations/{owned}/messages", headers=headers_b)
    assert owner_view.status_code == 200, owner_view.text
    assert "riêng của bệnh nhân B" in owner_view.text


# --- CP-09: id không hợp lệ -> fail closed ----------------------------------


@pytest.mark.asyncio
async def test_cp_09_unknown_conversation_id_fails_closed(client, stub_core):
    headers = await _register(client, "cp09.duy")

    for path in ("/api/v1/conversations/999999", "/api/v1/conversations/999999/messages"):
        response = await client.get(path, headers=headers)
        assert response.status_code == 404, f"{path}: {response.text}"

    # Chat vào một id không tồn tại cũng phải 404, không được âm thầm rơi về
    # hội thoại gần nhất: người dùng sẽ thấy câu trả lời của mình nằm sai chỗ.
    response = await _say(client, headers, "Xin chào", 999999)
    assert response.status_code == 404, response.text
    assert stub_core == []

    # Kiểu dữ liệu sai thì 422, không phải 500.
    bad = await client.post(
        "/api/v1/orchestrator/message",
        headers=headers,
        json={"message": "Xin chào", "conversation_id": "không-phải-số"},
    )
    assert bad.status_code == 422, bad.text


@pytest.mark.asyncio
async def test_cp_09_unauthenticated_access_is_401(client):
    for path in ("/api/v1/conversations", "/api/v1/conversations/1"):
        response = await client.get(path)
        assert response.status_code in (401, 403), f"{path}: {response.status_code}"


# --- CP-10: khách -> theo đúng hợp đồng hiện hành ---------------------------


@pytest.mark.asyncio
async def test_cp_10_guest_gets_no_persistence_and_is_invited_to_register(client, stub_core):
    """Khách vẫn chat được, nhưng không có hội thoại nào được lưu.

    Ràng buộc nằm ở tầng schema chứ không ở tầng code nhớ kiểm:
    `conversations.patient_id` là NOT NULL mà `user_id` của khách là None, nên
    không có đường nào tạo ra một hàng thuộc về khách.
    """

    headers = await _guest(client)

    chatting = await _say(client, headers, "Chỉ số WBC là gì?")
    assert chatting.status_code == 200, chatting.text
    assert stub_core == ["Chỉ số WBC là gì?"]

    for method, path in (("get", "/api/v1/conversations"), ("post", "/api/v1/conversations")):
        response = await getattr(client, method)(path, headers=headers)
        assert response.status_code == 403, f"{path}: {response.text}"
        assert "đăng ký" in response.json()["detail"].casefold()


@pytest.mark.asyncio
async def test_cp_10_guest_chat_writes_no_conversation_row(client, stub_core, test_db):
    from src.models.db import Conversation, ConversationMessage

    headers = await _guest(client)
    await _say(client, headers, "Chỉ số WBC là gì?")

    with test_db.session() as session:
        assert session.query(Conversation).count() == 0
        assert session.query(ConversationMessage).count() == 0


@pytest.mark.asyncio
async def test_cp_10_doctor_has_no_conversation_area(client, stub_core):
    """Bác sĩ 403, không phải 200-rỗng.

    Không phải vì nghi ngờ bác sĩ, mà để ma trận quyền chỉ có một cách đọc: V1
    không có hội thoại của bác sĩ, nên mở cửa bây giờ là thêm một ô trống.
    """

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "bacsi", "password": "bacsi123"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get("/api/v1/conversations", headers=headers)
    assert response.status_code == 403, response.text


# --- Tương thích ngược: client cũ không gửi conversation_id -----------------


@pytest.mark.asyncio
async def test_backward_compatible_request_without_conversation_id_still_works(client, stub_core):
    """Bản frontend đã deploy gọi endpoint này không kèm id, và phải tiếp tục chạy.

    Thiếu id thì server dùng hội thoại gần nhất, tạo mới nếu chưa có cái nào —
    chứ không 422. Đổi hợp đồng theo kiểu bắt buộc trường mới là làm sập
    production ngay lúc backend lên trước frontend.
    """

    headers = await _register(client, "compat.duy")

    first = await _say(client, headers, "Câu hỏi đầu tiên")
    assert first.status_code == 200, first.text

    second = await _say(client, headers, "Câu hỏi thứ hai")
    assert second.status_code == 200, second.text

    listed = await client.get("/api/v1/conversations", headers=headers)
    # Cả hai lượt vào CÙNG một hội thoại, không phải mỗi lượt một hội thoại mới.
    assert listed.json()["total"] == 1
    conversation_id = listed.json()["items"][0]["id"]

    detail = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert len(detail.json()["messages"]) == 4


# --- Onboarding: xác nhận phải rơi vào đúng hội thoại đang nói -------------


@pytest.mark.asyncio
async def test_onboarding_acknowledgement_lands_on_the_conversation(client, test_db):
    """Bấm "Tôi đã hiểu" rồi chat phải đi được, không kẹt lại ở onboarding.

    Đây là hồi quy cho một lỗi thật: khi context chuyển sang gắn theo hội thoại,
    route xác nhận vẫn ghi vào bản ghi in-memory khoá theo `patient:{uid}`, còn
    lượt chat sau đó đọc hàng `conv:{id}`. Kết quả là mọi bệnh nhân kẹt ở màn
    onboarding đúng một bước sau khi vừa xác nhận. Bộ test tip006 bắt được;
    test này giữ cho nó không quay lại.
    """

    from src.models.db import Conversation

    headers = await _register(client, "onboarding.duy")
    conversation_id = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]

    ack = await client.post("/api/v1/orchestrator/onboarding/acknowledge", headers=headers)
    assert ack.status_code == 200, ack.text

    with test_db.session() as session:
        row = session.get(Conversation, conversation_id)
        assert row is not None
        assert row.onboarding_acknowledged is True


@pytest.mark.asyncio
async def test_new_chat_does_not_ask_for_onboarding_again(client, test_db):
    """New Chat kế thừa xác nhận hướng dẫn — và chỉ kế thừa đúng thứ đó.

    Xác nhận là thuộc tính của người; ngữ cảnh y khoa là thuộc tính của cuộc
    trò chuyện. Bắt bấm lại "Tôi đã hiểu" mỗi lần mở hội thoại mới là biến một
    cam kết an toàn thành cái nút phải bấm cho qua.
    """

    from src.models.db import Conversation

    headers = await _register(client, "onboarding2.duy")
    first = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]
    await client.post("/api/v1/orchestrator/onboarding/acknowledge", headers=headers)

    with test_db.session() as session:
        session.get(Conversation, first).current_analyte = "WBC"
        session.commit()

    second = (await client.post("/api/v1/conversations", headers=headers, json={})).json()["id"]

    with test_db.session() as session:
        row = session.get(Conversation, second)
        assert row.onboarding_acknowledged is True, "New Chat lại hỏi onboarding"
        # Và ngữ cảnh y khoa thì KHÔNG được kế thừa. Không có dòng này thì test
        # trên cũng xanh khi hàng mới sao chép nguyên cả context cũ.
        assert row.current_analyte is None
        assert row.current_report_ref is None
