"""Nghiệm thu chức năng câu hỏi gợi ý — phần logic sinh câu.

Sinh bằng bộ câu mẫu nên đầu ra cố định và kiểm được bằng assert chính xác. Đây
là lý do chọn phương án mẫu thay vì để LLM tự viết.
"""

import pytest

from src.services.question_templates import (
    MAX_QUESTIONS,
    MAX_UNKNOWN_QUESTIONS,
    GeneratedQuestion,
    generate_questions,
    load_question_templates,
    reconcile_after_guardrail,
    relative_deviation,
)


def indicator(
    name: str,
    *,
    status: str,
    value: float = 1.0,
    unit: str = "mmol/L",
    low: float | None = 1.0,
    high: float | None = 2.0,
    analyte_id: str | None = None,
):
    return {
        "name": name,
        "analyte_id": analyte_id,
        "value": value,
        "unit": unit,
        "reference_low": low,
        "reference_high": high,
        "status": status,
    }


# --- Sinh cho chỉ số nào ------------------------------------------------------


def test_normal_indicator_gets_no_question():
    """Chỉ số bình thường không sinh câu hỏi.

    Người đọc thấy câu hỏi về một chỉ số đang bình thường sẽ nghĩ chỉ số đó có
    vấn đề gì mà mình chưa nhận ra.
    """
    questions = generate_questions(
        [indicator("Glucose", status="normal", value=5.2, analyte_id="glucose")]
    )

    assert questions == []


def test_all_normal_report_returns_empty_not_fallback():
    """Toàn bộ bình thường thì rỗng, KHÔNG dùng bộ câu dự phòng.

    Bộ dự phòng chỉ dành cho trường hợp guardrail chặn nội dung. Một người có
    kết quả hoàn toàn bình thường không nên rời ứng dụng với cảm giác có điều gì
    cần lo lắng.
    """
    questions = generate_questions(
        [
            indicator("Glucose", status="normal", analyte_id="glucose"),
            indicator("WBC", status="normal", analyte_id="wbc"),
        ]
    )

    assert questions == []


@pytest.mark.parametrize("status", ["low", "high", "critical_low", "critical_high"])
def test_abnormal_and_critical_statuses_get_a_question(status):
    questions = generate_questions(
        [indicator("Kali", status=status, value=7.1, analyte_id="kali")]
    )

    assert len(questions) == 1
    assert questions[0].analyte_id == "kali"


def test_question_uses_the_name_the_patient_typed_not_the_canonical_id():
    """Hiển thị đúng tên trên phiếu của bệnh nhân.

    Người nhập "Đường huyết" mà nhận câu hỏi về "Fasting plasma glucose" sẽ
    không nhận ra đó là chỉ số của mình. Mã chuẩn chỉ dùng để chọn mẫu câu.
    """
    questions = generate_questions(
        [
            indicator(
                "Đường huyết",
                status="high",
                value=9.9,
                analyte_id="glucose",
            )
        ]
    )

    assert "Đường huyết" in questions[0].text
    assert "Fasting plasma glucose" not in questions[0].text
    assert "glucose" not in questions[0].text.casefold().replace("đường huyết", "")


# --- Ưu tiên và giới hạn ------------------------------------------------------


def test_critical_indicators_come_before_abnormal_ones():
    questions = generate_questions(
        [
            indicator("LDL-Cholesterol", status="high", value=4.2, low=0.0, high=3.4, analyte_id="ldl_cholesterol"),
            indicator("Kali", status="critical_high", value=7.1, low=3.5, high=5.0, analyte_id="kali"),
        ]
    )

    assert [question.priority for question in questions] == ["critical", "abnormal"]
    assert questions[0].analyte_id == "kali"


def test_cap_is_five_questions_and_keeps_the_critical_ones():
    """Sáu chỉ số bất thường vẫn chỉ ra 5 câu, và câu nguy kịch không bị loại.

    Một danh sách 12 câu mang vào phòng khám 5 phút dẫn tới việc không hỏi được
    câu nào.
    """
    indicators = [
        indicator("WBC", status="high", value=20.0, low=4.0, high=10.0, analyte_id="wbc"),
        indicator("RBC", status="high", value=6.2, low=4.0, high=5.4, analyte_id="rbc"),
        indicator("HGB", status="low", value=100.0, low=120.0, high=160.0, analyte_id="hgb"),
        indicator("Glucose", status="high", value=8.0, low=3.9, high=6.4, analyte_id="glucose"),
        indicator("HbA1c", status="high", value=8.0, low=4.0, high=5.6, analyte_id="hba1c"),
        indicator("Kali", status="critical_high", value=7.1, low=3.5, high=5.0, analyte_id="kali"),
    ]

    questions = generate_questions(indicators)

    assert len(questions) == MAX_QUESTIONS
    assert questions[0].priority == "critical"
    assert questions[0].analyte_id == "kali"


def test_furthest_from_reference_range_wins_within_the_same_priority():
    """Lệch xa hơn thì xếp trước, đo bằng tỉ lệ so với độ rộng khoảng.

    So mmol/L với 10^9/L trực tiếp là vô nghĩa, nên phải chuẩn hoá. Ở đây
    HbA1c lệch 1.5 lần độ rộng khoảng, Glucose lệch 0.64 lần.
    """
    far = indicator("HbA1c", status="high", value=8.0, low=4.0, high=5.6, analyte_id="hba1c")
    near = indicator("Glucose", status="high", value=8.0, low=3.9, high=6.4, analyte_id="glucose")

    questions = generate_questions([near, far])

    assert [question.analyte_id for question in questions] == ["hba1c", "glucose"]


def test_relative_deviation_normalises_across_units():
    wide = indicator("WBC", status="high", value=11.0, low=4.0, high=10.0)
    narrow = indicator("Kali", status="high", value=5.5, low=3.5, high=5.0)

    # WBC vượt 1 đơn vị trên khoảng rộng 6; Kali vượt 0.5 trên khoảng rộng 1.5.
    assert relative_deviation(wide) == pytest.approx(1 / 6)
    assert relative_deviation(narrow) == pytest.approx(0.5 / 1.5)
    assert relative_deviation(narrow) > relative_deviation(wide)


def test_tie_break_is_stable_so_tests_can_assert_order():
    """Hai chỉ số lệch bằng nhau luôn ra cùng thứ tự giữa các lần chạy."""
    first = indicator("Glucose", status="high", value=7.0, low=4.0, high=6.0, analyte_id="glucose")
    second = indicator("Kali", status="high", value=6.0, low=3.0, high=5.0, analyte_id="kali")

    assert relative_deviation(first) == relative_deviation(second)

    forward = generate_questions([first, second])
    backward = generate_questions([second, first])

    assert [question.analyte_id for question in forward] == ["glucose", "kali"]
    assert [question.analyte_id for question in backward] == ["glucose", "kali"]


def test_missing_reference_range_does_not_break_sorting():
    questions = generate_questions(
        [
            indicator("Kali", status="high", value=6.0, low=None, high=None, analyte_id="kali"),
            indicator("Glucose", status="high", value=8.0, low=3.9, high=6.4, analyte_id="glucose"),
        ]
    )

    assert len(questions) == 2


# --- Chỉ số unknown -----------------------------------------------------------


def test_unknown_indicator_gets_one_neutral_question_naming_it():
    """Mỗi chỉ số unknown một câu riêng có nêu tên.

    Một câu gộp chung ("có vài chỉ số chưa có trong dữ liệu đối chiếu") khiến
    bác sĩ không biết đang nói về dòng nào trên phiếu.
    """
    questions = generate_questions(
        [indicator("Ferritin", status="unknown", value=12.0, unit="ng/mL", low=None, high=None)]
    )

    assert len(questions) == 1
    assert questions[0].priority == "unknown"
    assert "Ferritin" in questions[0].text


def test_unknown_questions_do_not_crowd_out_real_abnormal_ones():
    """Ngân sách của unknown tách riêng, không chiếm suất trong 5 câu.

    Phiếu có 5 chỉ số nguy kịch và 2 chỉ số unknown phải giữ đủ 5 câu nguy kịch.
    """
    criticals = [
        indicator(f"Chi so {index}", status="critical_high", value=10.0, low=1.0, high=2.0, analyte_id=f"a{index}")
        for index in range(5)
    ]
    unknowns = [
        indicator("Ferritin", status="unknown", low=None, high=None),
        indicator("Zinc", status="unknown", low=None, high=None),
    ]

    questions = generate_questions(criticals + unknowns)

    priorities = [question.priority for question in questions]

    assert priorities.count("critical") == MAX_QUESTIONS
    assert priorities.count("unknown") == MAX_UNKNOWN_QUESTIONS
    assert len(questions) == MAX_QUESTIONS + MAX_UNKNOWN_QUESTIONS


def test_unknown_questions_are_capped_too():
    unknowns = [
        indicator(f"Chi so {index}", status="unknown", low=None, high=None)
        for index in range(5)
    ]

    questions = generate_questions(unknowns)

    assert len(questions) == MAX_UNKNOWN_QUESTIONS


# --- Ranh giới nội dung -------------------------------------------------------


FORBIDDEN_SUBSTRINGS = (
    "uống thuốc",
    "dùng thuốc",
    "đổi thuốc",
    "kê đơn",
    "bạn mắc bệnh",
    "chẩn đoán bạn bị",
    "tiểu đường",
    "ung thư",
    "suy thận",
)


def test_no_shipped_template_contains_forbidden_content():
    """Không mẫu nào chứa tên bệnh, tên thuốc hay giả định đang điều trị.

    Câu hỏi dạng nghi vấn dễ được đánh giá nhẹ hơn thực tế: "Tôi có bị tiểu
    đường không?" xét ngữ pháp là câu hỏi, xét tác dụng là đưa một tên bệnh vào
    đầu người bệnh.

    Test này cũng chặn luôn câu mẫu trong wireframe màn 6 ("LDL cao có cần đổi
    thuốc không?"), vốn giả định bệnh nhân đang dùng thuốc — thông tin hệ thống
    không có vì tiền sử điều trị chưa từng được thu thập.
    """
    library = load_question_templates()

    texts = [library.unknown_indicator, *library.generic.values()]
    for per_status in library.analytes.values():
        texts.extend(per_status.values())

    assert texts, "bộ mẫu không được rỗng"

    for text in texts:
        lowered = text.casefold()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in lowered, f"{forbidden!r} xuất hiện trong: {text}"


def test_every_approved_analyte_has_a_template_for_every_abnormal_status():
    library = load_question_templates()

    analyte_ids = (
        "wbc",
        "rbc",
        "hgb",
        "glucose",
        "hba1c",
        "ldl_cholesterol",
        "hdl_cholesterol",
        "creatinine",
        "kali",
    )

    for analyte_id in analyte_ids:
        for status in ("low", "high", "critical_low", "critical_high"):
            assert library.template_for(analyte_id, status), (analyte_id, status)


def test_unknown_analyte_falls_back_to_the_generic_template():
    questions = generate_questions(
        [indicator("Chỉ số lạ", status="high", value=9.0, analyte_id="khong-co-trong-catalog")]
    )

    assert len(questions) == 1
    assert "Chỉ số lạ" in questions[0].text


# --- Ghép lại sau guardrail ---------------------------------------------------


def test_reconcile_keeps_metadata_when_guardrail_only_rewrote_text():
    generated = [
        GeneratedQuestion(text="cu 1", priority="critical", display_order=0, analyte_id="kali", indicator_name="Kali"),
        GeneratedQuestion(text="cu 2", priority="abnormal", display_order=1, analyte_id="glucose", indicator_name="Glucose"),
    ]

    result = reconcile_after_guardrail(["moi 1", "moi 2"], generated)

    assert [question.text for question in result] == ["moi 1", "moi 2"]
    assert [question.analyte_id for question in result] == ["kali", "glucose"]
    assert [question.priority for question in result] == ["critical", "abnormal"]


def test_reconcile_drops_indicator_link_when_guardrail_swapped_the_whole_set():
    """Số lượng khác thì không đoán câu nào ứng với chỉ số nào.

    Mất liên kết chỉ số còn hơn nối một câu hỏi vào sai dòng trên phiếu.
    """
    generated = [
        GeneratedQuestion(text="cu 1", priority="critical", display_order=0, analyte_id="kali", indicator_name="Kali"),
    ]

    result = reconcile_after_guardrail(["du phong 1", "du phong 2", "du phong 3"], generated)

    assert len(result) == 3
    assert {question.priority for question in result} == {"fallback"}
    assert all(question.analyte_id is None for question in result)
    assert all(question.indicator_name is None for question in result)


def test_reconcile_ignores_blank_texts():
    result = reconcile_after_guardrail(["  ", "that su co noi dung"], [])

    assert [question.text for question in result] == ["that su co noi dung"]
