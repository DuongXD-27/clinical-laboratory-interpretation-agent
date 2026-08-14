"""Nghiệm thu hai chức năng: câu hỏi gợi ý và ghi chú lâm sàng của bác sĩ.

Ranh giới quan trọng nhất mà bộ test này canh: nội dung do hệ thống sinh phải đi
qua guardrail, nội dung do bác sĩ viết thì không. Hai loại chịu quy tắc ngược
nhau dù cùng hiển thị trên một màn hình.
"""

from unittest.mock import AsyncMock

import pytest

from src.api import routes
from src.models.db import DoctorNote, ReportDoctorView, ReportQuestion

GRAPH_RESULT = {
    "indicators": [
        {
            "name": "LDL-Cholesterol",
            "value": 4.2,
            "unit": "mmol/L",
            "reference_low": 0.0,
            "reference_high": 3.4,
            "status": "high",
            "is_abnormal": True,
            "is_critical": False,
            "explanation": "Chỉ số cao hơn khoảng tham chiếu.",
            "sources": ["https://example.org/ldl"],
        },
        {
            "name": "Kali",
            "value": 7.1,
            "unit": "mmol/L",
            "reference_low": 3.5,
            "reference_high": 5.0,
            "status": "critical_high",
            "is_abnormal": True,
            "is_critical": True,
            "explanation": "Chỉ số ở mức nguy kịch.",
            "sources": [],
        },
    ],
    "has_critical_values": True,
    "critical_alerts": [],
    "guardrail_passed": True,
    "disclaimer": "Test disclaimer",
    "questions_for_doctor": [
        "Chỉ số Kali của tôi là 7.1 mmol/L, cao hơn nhiều so với khoảng tham chiếu. Tôi cần làm gì ngay bây giờ ạ?",
        "Chỉ số LDL-Cholesterol của tôi là 4.2 mmol/L, cao hơn khoảng tham chiếu. Mức này có ý nghĩa gì với tôi ạ?",
    ],
    "doctor_question_meta": [
        {
            "priority": "critical",
            "display_order": 0,
            "analyte_id": "kali",
            "indicator_name": "Kali",
        },
        {
            "priority": "abnormal",
            "display_order": 1,
            "analyte_id": "ldl_cholesterol",
            "indicator_name": "LDL-Cholesterol",
        },
    ],
    "questions_for_doctor_meta_note": "song song, cùng thứ tự",
    "out_of_scope_indicators": [],
}


@pytest.fixture
def stub_graph(monkeypatch):
    monkeypatch.setattr(routes.agent, "ainvoke", AsyncMock(return_value=GRAPH_RESULT))


async def login_headers(client, username: str, password: str):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def register_and_login(client, username: str, password: str = "matkhau123"):
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201, response.text
    return await login_headers(client, username, password)


async def doctor_headers(client):
    return await login_headers(client, "bacsi", "bacsi123")


async def guest_headers(client):
    response = await client.post("/api/v1/auth/guest")
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def submit_analysis(client, headers, *, test_date: str = "2026-08-11"):
    response = await client.post(
        "/api/v1/analyze",
        headers=headers,
        json={
            "patient_age": 40,
            "patient_gender": "female",
            "test_date": test_date,
            "indicators": [
                {"name": "LDL-Cholesterol", "value": 4.2, "unit": "mmol/L"},
                {"name": "Kali", "value": 7.1, "unit": "mmol/L"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def make_report(client, username: str = "benhnhan_a"):
    headers = await register_and_login(client, username)
    saved = await submit_analysis(client, headers)
    return headers, saved["saved_report_id"]


# ===========================================================================
# Câu hỏi gợi ý
# ===========================================================================


@pytest.mark.asyncio
async def test_whole_question_set_is_saved_with_the_report(client, test_db, stub_graph):
    """Lưu cả bộ câu sinh ra, không chỉ câu bệnh nhân tick.

    Mở lại phiếu cũ phải thấy đúng bộ của lần đó, vì bệnh nhân có thể đã in ra
    mang đi khám và đang mở lại để đối chiếu.
    """
    headers, report_id = await make_report(client)

    with test_db.session() as db:
        assert db.query(ReportQuestion).count() == 2

    detail = await client.get(f"/api/v1/history/{report_id}", headers=headers)

    questions = detail.json()["questions"]
    assert len(questions) == 2
    assert [question["priority"] for question in questions] == ["critical", "abnormal"]
    assert all(question["is_selected"] is False for question in questions)
    assert all(question["status"] == "generated" for question in questions)


@pytest.mark.asyncio
async def test_questions_are_linked_back_to_the_right_indicator_row(client, stub_graph):
    headers, report_id = await make_report(client)

    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()

    assert all(question["indicator_id"] is not None for question in detail["questions"])
    assert len({question["indicator_id"] for question in detail["questions"]}) == 2


@pytest.mark.asyncio
async def test_patient_selects_the_questions_to_bring_along(client, stub_graph):
    headers, report_id = await make_report(client)
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    chosen = detail["questions"][0]["id"]

    response = await client.post(
        f"/api/v1/history/{report_id}/questions/selection",
        headers=headers,
        json={"question_ids": [chosen]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    selected = [question for question in body if question["is_selected"]]
    assert [question["id"] for question in selected] == [chosen]
    assert selected[0]["status"] == "sent_to_doctor"
    assert [question for question in body if not question["is_selected"]][0]["status"] == "generated"


@pytest.mark.asyncio
async def test_unselecting_returns_the_question_to_generated(client, stub_graph):
    headers, report_id = await make_report(client)
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    chosen = detail["questions"][0]["id"]

    await client.post(
        f"/api/v1/history/{report_id}/questions/selection",
        headers=headers,
        json={"question_ids": [chosen]},
    )
    response = await client.post(
        f"/api/v1/history/{report_id}/questions/selection",
        headers=headers,
        json={"question_ids": []},
    )

    assert all(question["is_selected"] is False for question in response.json())
    assert all(question["status"] == "generated" for question in response.json())


@pytest.mark.asyncio
async def test_doctor_cannot_tick_questions_on_behalf_of_the_patient(client, stub_graph):
    """Danh sách này thể hiện bệnh nhân thật sự quan tâm gì; bác sĩ tick hộ là mất đúng thông tin đó."""
    _, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    response = await client.post(
        f"/api/v1/history/{report_id}/questions/selection",
        headers=doctor,
        json={"question_ids": []},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patient_cannot_touch_another_patients_questions(client, stub_graph):
    _, report_id_a = await make_report(client, "benhnhan_a")
    headers_b = await register_and_login(client, "benhnhan_b")

    response = await client.post(
        f"/api/v1/history/{report_id_a}/questions/selection",
        headers=headers_b,
        json={"question_ids": []},
    )

    # 404 chứ không 403: 403 xác nhận phiếu đó tồn tại.
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_doctor_sees_which_questions_the_patient_chose(client, stub_graph):
    """Bác sĩ cần thấy bệnh nhân đã chuẩn bị thắc mắc gì trước khi viết ghi chú."""
    headers, report_id = await make_report(client)
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    chosen = detail["questions"][0]["id"]

    await client.post(
        f"/api/v1/history/{report_id}/questions/selection",
        headers=headers,
        json={"question_ids": [chosen]},
    )

    doctor = await doctor_headers(client)
    seen = (await client.get(f"/api/v1/history/{report_id}", headers=doctor)).json()

    assert [question["id"] for question in seen["questions"] if question["is_selected"]] == [chosen]


@pytest.mark.asyncio
async def test_doctor_answers_a_question_and_the_patient_reads_it(client, stub_graph):
    headers, report_id = await make_report(client)
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    question_id = detail["questions"][0]["id"]

    doctor = await doctor_headers(client)
    answered = await client.post(
        f"/api/v1/history/{report_id}/questions/{question_id}/answer",
        headers=doctor,
        json={"answer_text": "Mức này cần theo dõi, hẹn tái khám sau hai tuần."},
    )

    assert answered.status_code == 200, answered.text
    assert answered.json()["status"] == "answered"
    assert answered.json()["answered_by_username"] == "bacsi"
    assert answered.json()["answered_at"] is not None

    seen = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    target = next(q for q in seen["questions"] if q["id"] == question_id)
    assert target["answer_text"] == "Mức này cần theo dõi, hẹn tái khám sau hai tuần."
    assert target["answered_by_username"] == "bacsi"


@pytest.mark.asyncio
async def test_patient_cannot_answer_their_own_question(client, stub_graph):
    headers, report_id = await make_report(client)
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    question_id = detail["questions"][0]["id"]

    response = await client.post(
        f"/api/v1/history/{report_id}/questions/{question_id}/answer",
        headers=headers,
        json={"answer_text": "tu tra loi"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_answering_a_question_from_another_report_returns_404(client, stub_graph):
    headers_a, report_id_a = await make_report(client, "benhnhan_a")
    detail_a = (await client.get(f"/api/v1/history/{report_id_a}", headers=headers_a)).json()
    question_of_a = detail_a["questions"][0]["id"]

    headers_b = await register_and_login(client, "benhnhan_b")
    report_id_b = (await submit_analysis(client, headers_b))["saved_report_id"]

    doctor = await doctor_headers(client)
    response = await client.post(
        f"/api/v1/history/{report_id_b}/questions/{question_of_a}/answer",
        headers=doctor,
        json={"answer_text": "sai phieu"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unselecting_does_not_erase_an_existing_answer(client, stub_graph):
    headers, report_id = await make_report(client)
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    question_id = detail["questions"][0]["id"]

    doctor = await doctor_headers(client)
    await client.post(
        f"/api/v1/history/{report_id}/questions/{question_id}/answer",
        headers=doctor,
        json={"answer_text": "cau tra loi da co"},
    )

    await client.post(
        f"/api/v1/history/{report_id}/questions/selection",
        headers=headers,
        json={"question_ids": []},
    )

    seen = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    target = next(q for q in seen["questions"] if q["id"] == question_id)
    assert target["answer_text"] == "cau tra loi da co"
    assert target["status"] == "answered"


@pytest.mark.asyncio
async def test_empty_answer_is_rejected(client, stub_graph):
    headers, report_id = await make_report(client)
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    question_id = detail["questions"][0]["id"]

    doctor = await doctor_headers(client)
    response = await client.post(
        f"/api/v1/history/{report_id}/questions/{question_id}/answer",
        headers=doctor,
        json={"answer_text": ""},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_guest_has_no_questions_to_select(client, test_db, stub_graph):
    headers = await guest_headers(client)
    result = await submit_analysis(client, headers)

    assert result["saved_report_id"] is None
    with test_db.session() as db:
        assert db.query(ReportQuestion).count() == 0

    response = await client.post(
        "/api/v1/history/1/questions/selection",
        headers=headers,
        json={"question_ids": []},
    )
    assert response.status_code == 403


# ===========================================================================
# Ghi chú lâm sàng của bác sĩ
# ===========================================================================


@pytest.mark.asyncio
async def test_doctor_note_is_saved_and_shown_to_the_patient(client, stub_graph):
    """Vòng lặp có con người tham gia phải tồn tại trong hệ thống, không chỉ trên giao diện."""
    headers, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    created = await client.post(
        f"/api/v1/history/{report_id}/notes",
        headers=doctor,
        json={"note_text": "Kali cao, cần kiểm tra lại trong tuần này."},
    )

    assert created.status_code == 201, created.text
    assert created.json()["target_type"] == "report"
    assert created.json()["target_id"] == report_id
    assert created.json()["doctor_username"] == "bacsi"

    seen = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    assert len(seen["doctor_notes"]) == 1
    note = seen["doctor_notes"][0]
    assert note["note_text"] == "Kali cao, cần kiểm tra lại trong tuần này."
    assert note["doctor_username"] == "bacsi"
    assert note["created_at"] is not None
    assert seen["has_doctor_notes"] is True


@pytest.mark.asyncio
async def test_doctor_note_is_not_filtered_by_guardrail(client, stub_graph):
    """Ghi chú của bác sĩ KHÔNG đi qua guardrail.

    Câu "nên dùng thuốc theo chỉ định và tái khám sau ba tháng" chứa cụm mà
    guardrail chặn với nội dung do hệ thống sinh. Bác sĩ có thẩm quyền nói điều
    đó, nên nội dung phải được lưu nguyên văn — áp guardrail ở đây là xoá mất
    lời chuyên môn của chính người có quyền nói ra nó.
    """
    headers, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    clinical = "Kết quả gợi ý rối loạn lipid máu, nên dùng thuốc theo chỉ định và tái khám sau ba tháng."

    created = await client.post(
        f"/api/v1/history/{report_id}/notes",
        headers=doctor,
        json={"note_text": clinical},
    )

    assert created.status_code == 201
    assert created.json()["note_text"] == clinical

    seen = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    assert seen["doctor_notes"][0]["note_text"] == clinical
    # Không bị thay bằng mẫu dự phòng của guardrail.
    assert "suy đoán" not in seen["doctor_notes"][0]["note_text"]


@pytest.mark.asyncio
async def test_patient_cannot_write_a_doctor_note(client, stub_graph):
    """Giá trị của ghi chú nằm ở chỗ nó do người có thẩm quyền y khoa viết."""
    headers, report_id = await make_report(client)

    response = await client.post(
        f"/api/v1/history/{report_id}/notes",
        headers=headers,
        json={"note_text": "tu ghi chu cho minh"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_notes_are_append_only_newest_first(client, test_db, stub_graph):
    """Mỗi lần ghi tạo bản ghi mới; muốn đính chính thì viết ghi chú mới."""
    headers, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    for text in ("ghi chu thu nhat", "ghi chu thu hai dinh chinh"):
        response = await client.post(
            f"/api/v1/history/{report_id}/notes",
            headers=doctor,
            json={"note_text": text},
        )
        assert response.status_code == 201

    with test_db.session() as db:
        assert db.query(DoctorNote).count() == 2

    seen = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    assert [note["note_text"] for note in seen["doctor_notes"]] == [
        "ghi chu thu hai dinh chinh",
        "ghi chu thu nhat",
    ]


@pytest.mark.asyncio
async def test_there_is_no_endpoint_to_edit_or_delete_a_note(client, stub_graph):
    headers, report_id = await make_report(client)
    doctor = await doctor_headers(client)
    created = await client.post(
        f"/api/v1/history/{report_id}/notes",
        headers=doctor,
        json={"note_text": "khong sua duoc"},
    )
    note_id = created.json()["id"]

    deleted = await client.delete(f"/api/v1/history/{report_id}/notes/{note_id}", headers=doctor)
    patched = await client.patch(
        f"/api/v1/history/{report_id}/notes/{note_id}",
        headers=doctor,
        json={"note_text": "sua"},
    )

    assert deleted.status_code in (404, 405)
    assert patched.status_code in (404, 405)


@pytest.mark.asyncio
async def test_empty_note_is_rejected(client, stub_graph):
    _, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    response = await client.post(
        f"/api/v1/history/{report_id}/notes",
        headers=doctor,
        json={"note_text": ""},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_note_target_id_from_body_cannot_redirect_to_another_report(client, stub_graph):
    """target_id của ghi chú mức phiếu luôn lấy từ URL, không nhận từ body."""
    headers_a, report_id_a = await make_report(client, "benhnhan_a")
    headers_b = await register_and_login(client, "benhnhan_b")
    report_id_b = (await submit_analysis(client, headers_b))["saved_report_id"]

    doctor = await doctor_headers(client)
    await client.post(
        f"/api/v1/history/{report_id_b}/notes",
        headers=doctor,
        json={"note_text": "ghi vao phieu B", "target_id": report_id_a},
    )

    seen_a = (await client.get(f"/api/v1/history/{report_id_a}", headers=headers_a)).json()
    seen_b = (await client.get(f"/api/v1/history/{report_id_b}", headers=headers_b)).json()

    assert seen_a["doctor_notes"] == []
    assert len(seen_b["doctor_notes"]) == 1


@pytest.mark.asyncio
async def test_patient_cannot_read_another_patients_notes(client, stub_graph):
    headers_a, report_id_a = await make_report(client, "benhnhan_a")
    doctor = await doctor_headers(client)
    await client.post(
        f"/api/v1/history/{report_id_a}/notes",
        headers=doctor,
        json={"note_text": "rieng cua benh nhan A"},
    )

    headers_b = await register_and_login(client, "benhnhan_b")
    response = await client.get(f"/api/v1/history/{report_id_a}", headers=headers_b)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_doctor_reads_notes_written_by_another_doctor(client, test_db, stub_graph, monkeypatch):
    from src.scripts import create_doctor

    monkeypatch.setattr(create_doctor, "SessionLocal", test_db.session_factory)
    monkeypatch.setattr(create_doctor, "init_db", lambda: None)
    assert create_doctor.main(["--username", "bs.hai", "--password", "matkhau123"]) == 0

    _, report_id = await make_report(client)

    first = await doctor_headers(client)
    await client.post(
        f"/api/v1/history/{report_id}/notes",
        headers=first,
        json={"note_text": "ghi chu cua bac si thu nhat"},
    )

    second = await login_headers(client, "bs.hai", "matkhau123")
    seen = (await client.get(f"/api/v1/history/{report_id}", headers=second)).json()

    assert seen["doctor_notes"][0]["doctor_username"] == "bacsi"


# ===========================================================================
# "Đã xem" tách khỏi "đã có ý kiến"
# ===========================================================================


@pytest.mark.asyncio
async def test_a_fresh_report_is_neither_reviewed_nor_noted(client, stub_graph):
    headers, report_id = await make_report(client)

    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    listing = (await client.get("/api/v1/history", headers=headers)).json()

    assert detail["reviewed_by_doctor"] is False
    assert detail["has_doctor_notes"] is False
    assert listing["items"][0]["reviewed_by_doctor"] is False
    assert listing["items"][0]["has_doctor_notes"] is False


@pytest.mark.asyncio
async def test_doctor_marks_reviewed_without_writing_a_note(client, stub_graph):
    """Bác sĩ thấy mọi thứ bình thường vẫn báo được là đã xem, không phải viết câu vô nghĩa cho có."""
    headers, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    response = await client.post(f"/api/v1/history/{report_id}/review", headers=doctor)

    assert response.status_code == 200, response.text
    assert response.json()["reviewed_by_doctor"] is True
    assert response.json()["has_doctor_notes"] is False
    assert response.json()["doctor_views"][0]["doctor_username"] == "bacsi"

    listing = (await client.get("/api/v1/history", headers=headers)).json()
    assert listing["items"][0]["reviewed_by_doctor"] is True
    assert listing["items"][0]["has_doctor_notes"] is False


@pytest.mark.asyncio
async def test_marking_reviewed_twice_does_not_duplicate_the_row(client, test_db, stub_graph):
    _, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    await client.post(f"/api/v1/history/{report_id}/review", headers=doctor)
    await client.post(f"/api/v1/history/{report_id}/review", headers=doctor)

    with test_db.session() as db:
        assert db.query(ReportDoctorView).count() == 1


@pytest.mark.asyncio
async def test_second_doctor_viewing_is_not_lost(client, test_db, stub_graph, monkeypatch):
    """Lưu danh sách chứ không phải một cờ chung: bác sĩ thứ hai từng xem là dữ liệu có giá trị."""
    from src.scripts import create_doctor

    monkeypatch.setattr(create_doctor, "SessionLocal", test_db.session_factory)
    monkeypatch.setattr(create_doctor, "init_db", lambda: None)
    assert create_doctor.main(["--username", "bs.hai", "--password", "matkhau123"]) == 0

    headers, report_id = await make_report(client)

    await client.post(f"/api/v1/history/{report_id}/review", headers=await doctor_headers(client))
    await client.post(
        f"/api/v1/history/{report_id}/review",
        headers=await login_headers(client, "bs.hai", "matkhau123"),
    )

    with test_db.session() as db:
        assert db.query(ReportDoctorView).count() == 2

    seen = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    assert {view["doctor_username"] for view in seen["doctor_views"]} == {"bacsi", "bs.hai"}


@pytest.mark.asyncio
async def test_a_noted_report_counts_as_reviewed_without_pressing_the_button(client, test_db, stub_graph):
    """Phiếu có ghi chú thì hiển nhiên đã được xem."""
    headers, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    await client.post(
        f"/api/v1/history/{report_id}/notes",
        headers=doctor,
        json={"note_text": "da xem va co y kien"},
    )

    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()

    assert detail["reviewed_by_doctor"] is True
    assert detail["has_doctor_notes"] is True
    with test_db.session() as db:
        assert db.query(ReportDoctorView).count() == 0


@pytest.mark.asyncio
async def test_patient_cannot_mark_their_own_report_reviewed(client, stub_graph):
    headers, report_id = await make_report(client)

    response = await client.post(f"/api/v1/history/{report_id}/review", headers=headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_guest_cannot_reach_notes_or_review(client, stub_graph):
    headers = await guest_headers(client)

    note = await client.post(
        "/api/v1/history/1/notes",
        headers=headers,
        json={"note_text": "khach ghi chu"},
    )
    review = await client.post("/api/v1/history/1/review", headers=headers)

    assert note.status_code == 403
    assert review.status_code == 403


@pytest.mark.asyncio
async def test_notes_and_review_require_authentication(client):
    assert (await client.post("/api/v1/history/1/notes", json={"note_text": "x"})).status_code == 401
    assert (await client.post("/api/v1/history/1/review")).status_code == 401
    assert (
        await client.post("/api/v1/history/1/questions/selection", json={"question_ids": []})
    ).status_code == 401


@pytest.mark.asyncio
async def test_notes_and_questions_survive_a_backend_restart(client, test_db, stub_graph):
    headers, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    await client.post(
        f"/api/v1/history/{report_id}/notes",
        headers=doctor,
        json={"note_text": "ghi chu phai con sau restart"},
    )
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=headers)).json()
    question_id = detail["questions"][0]["id"]
    await client.post(
        f"/api/v1/history/{report_id}/questions/selection",
        headers=headers,
        json={"question_ids": [question_id]},
    )

    test_db.restart()

    headers_after = await login_headers(client, "benhnhan_a", "matkhau123")
    seen = (await client.get(f"/api/v1/history/{report_id}", headers=headers_after)).json()

    assert seen["doctor_notes"][0]["note_text"] == "ghi chu phai con sau restart"
    assert [q["id"] for q in seen["questions"] if q["is_selected"]] == [question_id]


@pytest.mark.asyncio
async def test_deleting_a_report_cascades_to_its_questions(client, test_db, stub_graph):
    """Câu hỏi không tồn tại độc lập với phiếu.

    Ghi chú thì KHÔNG cascade vì target_id không phải FK thật — hai tài liệu
    nghiệp vụ chốt ngược nhau ở điểm này, và hiện chưa có endpoint xoá phiếu nào
    nên chưa phải chọn. Test này ghi lại hành vi thật của DB để lúc làm chức năng
    xoá thì thấy ngay.
    """
    _, report_id = await make_report(client)

    with test_db.session() as db:
        from src.models.db import LabReport

        report = db.get(LabReport, report_id)
        db.delete(report)
        db.commit()

        assert db.query(ReportQuestion).count() == 0
