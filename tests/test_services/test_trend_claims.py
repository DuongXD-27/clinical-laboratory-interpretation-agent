"""Backend chốt nhận định, LLM chỉ diễn đạt — ADR-010 CRIT-TREND-01/02/04.

Ca thật (WBC, khoảng tham chiếu 4.72 - 11.3 10^9/L, chuỗi 20.0 → 8.0 → 6.0 → 8.0),
đoạn model sinh ra và ba lỗi trong đó:

    "Giá trị WBC gần nhất là 8.0 10^9/L, nằm trong khoảng tham chiếu 4.72 - 11.3
     10^9/L, tuy nhiên đã GIẢM 33.3% so với giá trị ngay trước đó là 6.0 10^9/L.
     Trong chuỗi xét nghiệm, giá trị đã GIẢM DẦN từ mức cao 20.0 10^9/L vào ngày
     13 tháng 8, vượt cận trên 11.3 10^9/L, xuống còn 6.0 10^9/L vào ngày 19 tháng 8,
     NẰM DƯỚI CẬN DƯỚI. Các giá trị trong khoảng 8.0 10^9/L vào ngày 16 và 20 tháng 8
     đều nằm trong khoảng tham chiếu."

1. 8.0 so với 6.0 là TĂNG 33.3%, không phải giảm.
2. 6.0 nằm trong 4.72 - 11.3 nên không thể "dưới cận dưới".
3. 20.0 → 8.0 → 6.0 → 8.0 không phải "giảm dần" vì điểm cuối đã tăng trở lại.

Cả ba đều lọt guardrail cũ vì guardrail đó chỉ quét SỐ, mà không lỗi nào tạo ra số
mới: 33.3, 6.0, 20.0, 11.3 đều nằm trong whitelist. Backend thì đã tính đúng cả ba
(``percent_change`` trả "tăng", ``classify_reference_position`` trả within_reference,
``trend_service._observed_direction`` trả None) — chỉ là chưa ai đối chiếu ngược.
"""

from datetime import date

import pytest

from src.models.schemas import TrendPointResponse, TrendResponse
from src.services.trend_claims import (
    TrendClaim,
    build_claim_set,
    classify_reference_position,
    compose_deterministic_explanation,
    merge_claims,
    percent_change,
    series_shape,
    split_sentences,
    validate_claims,
)
from src.services.trend_explanation_service import TrendPointReferenceFact

WBC_UNIT = "10^9/L"
WBC_LOWER, WBC_UPPER = 4.72, 11.3
WBC_SERIES = [(13, 20.0), (16, 8.0), (19, 6.0), (20, 8.0)]

BLOCKED_TEXT = (
    "Giá trị WBC gần nhất là 8.0 10^9/L, nằm trong khoảng tham chiếu 4.72 - 11.3 10^9/L, "
    "tuy nhiên đã giảm 33.3% so với giá trị ngay trước đó là 6.0 10^9/L. "
    "Trong chuỗi xét nghiệm, giá trị đã giảm dần từ mức cao 20.0 10^9/L vào ngày 13 tháng 8, "
    "vượt cận trên 11.3 10^9/L, xuống còn 6.0 10^9/L vào ngày 19 tháng 8, nằm dưới cận dưới. "
    "Các giá trị trong khoảng 8.0 10^9/L vào ngày 16 và 20 tháng 8 đều nằm trong khoảng tham chiếu."
)


def _trend(series=WBC_SERIES, *, unit=WBC_UNIT, observed_direction=None, name="WBC") -> TrendResponse:
    return TrendResponse(
        analyte_canonical=name,
        display_name=name,
        canonical_unit=unit,
        filter="latest5",
        result_count=len(series),
        trend_available=True,
        observed_direction=observed_direction,
        points=[
            TrendPointResponse(report_id=index, test_date=date(2026, 8, day), value=value, assessment="normal")
            for index, (day, value) in enumerate(series, start=1)
        ],
    )


def _facts(series=WBC_SERIES, *, lower=WBC_LOWER, upper=WBC_UPPER) -> list[TrendPointReferenceFact]:
    return [
        TrendPointReferenceFact(
            report_id=index,
            test_date=f"2026-08-{day:02d}",
            value=value,
            lower=lower,
            upper=upper,
            relation=classify_reference_position(value, lower, upper),
        )
        for index, (day, value) in enumerate(series, start=1)
    ]


# --- backend vốn đã tính đúng cả ba ------------------------------------------


def test_backend_reads_the_wbc_series_correctly():
    trend, facts = _trend(), _facts()

    assert percent_change(trend) == (33.3, "tăng")
    assert [fact.relation for fact in facts] == [
        "above_reference",
        "within_reference",
        "within_reference",
        "within_reference",
    ]
    # 6.0 cách cận dưới 1.28, rộng hơn biên 10% (0.658) nên cũng không phải "gần cận dưới".
    assert classify_reference_position(6.0, WBC_LOWER, WBC_UPPER) == "within_reference"
    assert series_shape(trend, facts) == "fell_from_high"


# --- ba lỗi phải bị chặn ------------------------------------------------------


def test_the_exact_production_paragraph_is_now_blocked():
    claim_set = build_claim_set(_trend(), _facts())

    violations = validate_claims(BLOCKED_TEXT, claim_set.claims)
    reasons = " | ".join(reason for reason, _ in violations)

    assert "mức biến động" in reasons, "phải bắt được 'giảm 33.3%' khi backend tính ra 'tăng'"
    assert "within_reference" in reasons, "phải bắt được 6.0 bị gán 'dưới cận dưới'"
    assert "hướng đi tổng thể" in reasons, "phải bắt được 'giảm dần' trên chuỗi không đơn điệu"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Giá trị gần nhất 8.0 10^9/L đã giảm 33.3% so với lần trước.", "mức biến động"),
        ("Ngày 19/08/2026 giá trị 6.0 10^9/L nằm dưới cận dưới.", "within_reference"),
        ("Các giá trị giảm dần qua các lần đo.", "hướng đi tổng thể"),
        ("Chỉ số liên tục giảm từ đầu chuỗi.", "hướng đi tổng thể"),
    ],
)
def test_each_semantic_error_is_caught_on_its_own(text, expected):
    claim_set = build_claim_set(_trend(), _facts())

    violations = validate_claims(text, claim_set.claims)

    assert any(expected in reason for reason, _ in [(r, e) for r, e in violations]), violations


def test_claiming_a_reference_position_when_no_range_matched_is_blocked():
    """Prompt vẫn luôn cấm điều này, nhưng trước đây không có gì cưỡng chế."""
    facts = _facts(lower=None, upper=None)
    claim_set = build_claim_set(_trend(), facts)

    violations = validate_claims("Giá trị 8.0 10^9/L nằm trong khoảng tham chiếu.", claim_set.claims)

    assert any("unknown_reference" in reason for reason, _ in violations)


# --- và câu đúng vẫn phải đi qua ---------------------------------------------


def test_the_deterministic_paragraph_validates_against_its_own_claims():
    """Bất biến quan trọng nhất: nội dung dự phòng của backend không được tự chặn chính nó."""
    claim_set = build_claim_set(_trend(), _facts())

    assert validate_claims(compose_deterministic_explanation(claim_set.sentences), claim_set.claims) == []


def test_a_faithful_rewrite_by_the_model_passes():
    claim_set = build_claim_set(_trend(), _facts())

    text = (
        "Giá trị WBC gần nhất là 8.0 10^9/L, nằm trong khoảng tham chiếu 4.72 - 11.3 10^9/L "
        "và đã tăng 33.3% so với lần đo ngay trước là 6.0 10^9/L. "
        "Chuỗi kết quả giảm mạnh từ mức cao nhất 20.0 10^9/L ở lần đo đầu, sau đó dao động trong "
        "khoảng tham chiếu. Ngày 13/08/2026 là điểm cần chú ý trên biểu đồ vì vượt cận trên 11.3 10^9/L."
    )

    assert validate_claims(text, claim_set.claims) == []


def test_one_sentence_describing_two_points_correctly_is_not_blocked():
    """Từ "bắt buộc" là lối thoát, nếu không mọi câu kể nhiều điểm cùng lúc đều bị chặn oan."""
    claim_set = build_claim_set(_trend(), _facts())

    text = "Ngày 13/08/2026 giá trị 20.0 10^9/L vượt cận trên 11.3 10^9/L, còn 6.0 10^9/L nằm trong khoảng tham chiếu."

    assert validate_claims(text, claim_set.claims) == []


def test_a_month_number_is_not_mistaken_for_a_value():
    """Neo số phải chặn biên, nếu không "ngày 20 tháng 8" bị coi là nhắc giá trị 20.0."""
    claim_set = build_claim_set(_trend(), _facts())

    text = "Ngày 20 tháng 8 giá trị 8.0 10^9/L nằm trong khoảng tham chiếu."

    assert validate_claims(text, claim_set.claims) == []


def test_a_decimal_value_is_not_split_across_sentences():
    assert split_sentences("Giá trị 8.0 tăng. Ngày sau giảm.") == ["Giá trị 8.0 tăng", " Ngày sau giảm"]


# --- hình dạng chuỗi ----------------------------------------------------------


@pytest.mark.parametrize(
    "series,observed,expected",
    [
        ([(1, 2.1), (2, 2.3), (3, 2.6)], "increasing", "increasing"),
        ([(1, 2.6), (2, 2.3), (3, 2.1)], "decreasing", "decreasing"),
        ([(1, 8.0), (2, 8.1), (3, 8.0)], None, "stable"),
        ([(1, 5.0), (2, 11.0), (3, 6.0)], None, "fluctuating"),
        (WBC_SERIES, None, "fell_from_high"),
    ],
)
def test_series_shape_is_decided_by_the_backend(series, observed, expected):
    trend = _trend(series, observed_direction=observed)

    assert series_shape(trend, _facts(series)) == expected


def test_monotonic_wording_is_allowed_when_the_backend_agrees():
    trend = _trend([(1, 2.1), (2, 2.3), (3, 2.6)], observed_direction="increasing")
    claim_set = build_claim_set(trend, _facts([(1, 2.1), (2, 2.3), (3, 2.6)]))

    assert validate_claims("Chỉ số tăng dần qua 3 lần đo.", claim_set.claims) == []


# --- chế độ nhóm --------------------------------------------------------------


def test_group_mode_anchors_shape_on_the_analyte_name():
    """"A tăng dần trong khi B dao động" là câu hợp lệ ở chế độ nhóm."""
    rising = [(1, 2.1), (2, 2.3), (3, 2.6)]
    swinging = [(1, 5.0), (2, 11.0), (3, 6.0)]
    claims = merge_claims(
        [
            build_claim_set(
                _trend(rising, observed_direction="increasing", name="LDL-C"),
                _facts(rising, lower=2.0, upper=3.5),
                shape_anchor="LDL-C",
            ).claims,
            build_claim_set(
                _trend(swinging, name="HDL-C"),
                _facts(swinging, lower=1.0, upper=2.0),
                shape_anchor="HDL-C",
            ).claims,
        ]
    )

    text = "LDL-C tăng dần qua các lần đo, trong khi HDL-C dao động lên xuống."

    assert validate_claims(text, claims) == []


def test_group_mode_still_blocks_a_wrong_shape_for_the_named_analyte():
    swinging = [(1, 5.0), (2, 11.0), (3, 6.0)]
    claims = build_claim_set(
        _trend(swinging, name="HDL-C"),
        _facts(swinging, lower=1.0, upper=2.0),
        shape_anchor="HDL-C",
    ).claims

    violations = validate_claims("HDL-C giảm dần qua các lần đo.", claims)

    assert any("hướng đi tổng thể" in reason for reason, _ in violations)


def test_group_mode_drops_anchors_two_analytes_fight_over():
    """Cùng giá trị 8.0 nhưng hai nhãn khác nhau: không quy được câu về chỉ số nào."""
    series = [(1, 8.0), (2, 8.0), (3, 8.0)]
    inside = build_claim_set(_trend(series, name="A"), _facts(series, lower=4.0, upper=11.0), shape_anchor="A")
    outside = build_claim_set(_trend(series, name="B"), _facts(series, lower=1.0, upper=2.0), shape_anchor="B")

    merged = merge_claims([inside.claims, outside.claims])

    assert not [claim for claim in merged if "khoảng tham chiếu" in claim.kind]
    assert len([claim for claim in merged if "hướng đi tổng thể" in claim.kind]) == 2


# --- không có claim thì không kiểm gì ----------------------------------------


def test_no_claims_means_no_semantic_checking():
    assert validate_claims(BLOCKED_TEXT, ()) == []
    assert validate_claims(BLOCKED_TEXT, [TrendClaim(kind="x", required=(), forbidden=(), anchors=())]) == []
