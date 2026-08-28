"""Chuỗi thời gian và SLO — hàm thuần, test không cần DB.

Hai khẳng định quan trọng nhất trong file này:

1. **Mốc rỗng vẫn được trả về.** Bỏ nó đi thì biểu đồ nối liền hai điểm cách
   nhau sáu giờ thành một đường thoải, và người đọc thấy một hệ thống chạy êm
   suốt đêm trong khi thực tế nó không nhận request nào — có thể vì đã chết.
2. **SLO tổng lấy theo cái TỆ NHẤT, không lấy trung bình.** Trung bình sẽ để một
   SLO vi phạm bị hai SLO khoẻ che đi — đúng loại che lấp mà con số trung bình
   85ms đã gây ra.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.services import trace_slo
from src.services.trace_timeseries import (
    build_timeseries,
    pick_bucket_minutes,
    total_error_breakdown,
)

NOW = datetime(2026, 8, 27, 12, 0)


def _row(
    minutes_ago: int,
    *,
    path="/api/v1/analyze",
    duration=4000.0,
    status=200,
    error_type=None,
    error_raw=None,
    llm_calls=1,
    tokens_in=1200,
    tokens_out=350,
    cost=0.00039,
    fallbacks=0,
):
    return SimpleNamespace(
        created_at=NOW - timedelta(minutes=minutes_ago),
        path=path,
        method="POST",
        duration_ms=duration,
        status_code=status,
        error_type=error_type,
        error_raw_type=error_raw,
        llm_call_count=llm_calls,
        llm_error_count=0,
        llm_input_tokens=tokens_in,
        llm_output_tokens=tokens_out,
        llm_cost_usd=cost,
        guardrail_fallback_count=fallbacks,
        guardrail_rewrite_count=0,
    )


# --- kích thước mốc ----------------------------------------------------------


@pytest.mark.parametrize(
    ("hours", "expected_points_min", "expected_points_max"),
    [(1, 10, 30), (8, 10, 30), (24, 10, 30), (24 * 7, 10, 30)],
)
def test_every_window_yields_a_readable_number_of_points(hours, expected_points_min, expected_points_max):
    """Mọi cửa sổ ra 10–30 điểm.

    Mốc cố định 1 giờ thì cửa sổ "1 giờ qua" ra đúng MỘT điểm — không phải biểu
    đồ, mà là một con số vẽ to. Còn 7 ngày ra 168 điểm, dày hơn số pixel ngang
    mắt phân biệt được, và mọi đỉnh bị nhoè thành một dải.
    """

    bucket = pick_bucket_minutes(hours * 60)
    points = hours * 60 / bucket
    assert expected_points_min <= points <= expected_points_max, f"{hours}h -> mốc {bucket} phút -> {points} điểm"


# --- mốc rỗng ----------------------------------------------------------------


def test_empty_buckets_are_returned_not_dropped():
    since = NOW - timedelta(hours=24)
    # Chỉ hai request, cách nhau rất xa.
    rows = [_row(23 * 60), _row(10)]
    series = build_timeseries(rows, since=since, until=NOW)

    points = series["points"]
    assert len(points) == 24, "phải trả về đủ 24 mốc, kể cả mốc rỗng"
    assert sum(1 for p in points if p["count"] == 0) == 22


def test_empty_bucket_reports_none_percentiles_not_zero():
    since = NOW - timedelta(hours=24)
    series = build_timeseries([_row(10)], since=since, until=NOW)
    empty = [p for p in series["points"] if p["count"] == 0]
    assert empty, "cần ít nhất một mốc rỗng để kiểm"
    for point in empty:
        assert point["p50_ms"] is None
        assert point["p95_ms"] is None
        assert point["error_rate_pct"] is None
        assert point["cost_usd"] is None


# --- chỉ nhóm AI -------------------------------------------------------------


def test_only_the_ai_group_is_plotted():
    """Trộn API thường vào thì đường P95 bị đè xuống.

    Đúng như con số trung bình 85ms đã làm: hơn một nghìn request ~50ms kéo mọi
    thống kê xuống, và biểu đồ trở thành đồ thị của nhóm đông chứ không của
    đường AI.
    """

    since = NOW - timedelta(hours=1)
    rows = [_row(10, path="/api/v1/analyze", duration=6000.0)]
    rows += [_row(10, path="/api/v1/history", duration=50.0) for _ in range(200)]

    series = build_timeseries(rows, since=since, until=NOW)
    total = sum(p["count"] for p in series["points"])
    assert total == 1, "chỉ request AI được tính"


def test_rows_outside_the_window_are_ignored():
    since = NOW - timedelta(hours=1)
    rows = [_row(10), _row(500)]
    series = build_timeseries(rows, since=since, until=NOW)
    assert sum(p["count"] for p in series["points"]) == 1


def test_malformed_created_at_does_not_crash():
    since = NOW - timedelta(hours=1)
    bad = _row(10)
    bad.created_at = "khong-phai-datetime"
    series = build_timeseries([bad, _row(10)], since=since, until=NOW)
    assert sum(p["count"] for p in series["points"]) == 1


# --- nội dung mốc ------------------------------------------------------------


def test_bucket_aggregates_tokens_cost_and_guardrail():
    since = NOW - timedelta(hours=1)
    # Cùng một mốc: cửa sổ 1 giờ -> mốc 5 phút, nên 10 và 9 phút trước rơi vào
    # cùng ô, còn 10 và 11 thì không. Bản đầu tôi dùng 10 và 11 rồi mới nhận ra.
    rows = [_row(10, fallbacks=1), _row(9)]
    series = build_timeseries(rows, since=since, until=NOW)
    filled = [p for p in series["points"] if p["count"]][0]

    assert filled["input_tokens"] == 2400
    assert filled["output_tokens"] == 700
    assert filled["cost_usd"] == pytest.approx(0.00078)
    assert filled["guardrail_fallback_count"] == 1
    # 1 lần phải thay / (1 + 2 lượt gọi) = 33.33%
    assert filled["guardrail_fallback_rate_pct"] == pytest.approx(33.33, abs=0.01)


def test_error_types_are_collected_per_bucket_and_for_the_window():
    since = NOW - timedelta(hours=2)
    rows = [
        _row(10, status=500, error_type="DB_SCHEMA", error_raw="DataError"),
        _row(70, status=500, error_type="LLM_PROVIDER", error_raw="APIStatusError"),
    ]
    series = build_timeseries(rows, since=since, until=NOW)

    assert series["error_types"] == ["DB_SCHEMA", "LLM_PROVIDER"]
    per_bucket = [p["errors_by_type"] for p in series["points"] if p["errors_by_type"]]
    assert {"DB_SCHEMA": 1} in per_bucket
    assert {"LLM_PROVIDER": 1} in per_bucket


def test_error_breakdown_keeps_a_raw_exception_example():
    """Nhóm lỗi nói "sửa ở đâu", tên lớp nói "sửa cái gì".

    `DB_SCHEMA` cho biết đi soi lược đồ; `DataError` cho biết đó là cột quá ngắn.
    Mất tên lớp thì phải quay lại grep log — đúng bước mà cả màn hình này tồn
    tại để bỏ đi.
    """

    rows = [
        _row(10, status=500, error_type="DB_SCHEMA", error_raw="DataError"),
        _row(20, status=500, error_type="DB_SCHEMA", error_raw="DataError"),
        _row(30, status=500, error_type="LLM_PROVIDER", error_raw="APIStatusError"),
    ]
    breakdown = total_error_breakdown(rows)

    assert breakdown[0] == {
        "error_type": "DB_SCHEMA",
        "count": 2,
        "example_exception": "DataError",
    }
    assert breakdown[1]["error_type"] == "LLM_PROVIDER"


# --- SLO ---------------------------------------------------------------------


def test_all_healthy_when_everything_is_within_target():
    rows = [_row(i) for i in range(200)]
    report = trace_slo.evaluate_slos(rows)
    assert report["overall_status"] == trace_slo.STATUS_HEALTHY
    assert all(s["status"] == trace_slo.STATUS_HEALTHY for s in report["slos"])


def test_overall_takes_the_worst_slo_not_the_average():
    """Một SLO vi phạm không được bị hai SLO khoẻ che đi.

    Lấy trung bình là tái tạo đúng cái bẫy mà con số trung bình 85ms đã gây ra.
    """

    # 199 request tốt + 1 lỗi -> availability 99.5% vẫn đạt... nhưng thêm nhiều
    # lỗi hơn để nó vi phạm, trong khi độ trễ vẫn rất tốt.
    rows = [_row(i) for i in range(190)]
    rows += [_row(i, status=500) for i in range(10)]

    report = trace_slo.evaluate_slos(rows)
    statuses = {s["name"]: s["status"] for s in report["slos"]}
    assert statuses["availability"] == trace_slo.STATUS_BREACHED
    assert statuses["latency"] == trace_slo.STATUS_HEALTHY
    assert report["overall_status"] == trace_slo.STATUS_BREACHED


def test_no_data_is_not_reported_as_healthy():
    """Hệ thống không nhận request nào thì KHÔNG phải là khoẻ mạnh.

    Nó có thể đã chết, và tô xanh lên đó là cách chắc nhất để không ai phát hiện.
    """

    report = trace_slo.evaluate_slos([])
    assert report["overall_status"] == trace_slo.STATUS_NO_DATA
    for slo in report["slos"]:
        assert slo["status"] == trace_slo.STATUS_NO_DATA
        assert slo["actual_pct"] is None
        assert slo["budget_used_pct"] is None


def test_error_budget_turns_a_percentage_into_a_count():
    """SLO 99.5% trên 200 request = được phép lỗi 1 lần."""

    rows = [_row(i) for i in range(200)]
    report = trace_slo.evaluate_slos(rows)
    availability = next(s for s in report["slos"] if s["name"] == "availability")
    assert availability["budget_used_pct"] == 0.0
    assert availability["budget_remaining"] == pytest.approx(1.0, abs=0.01)


def test_budget_at_risk_before_it_is_exhausted():
    """Chuyển AT_RISK ở 75% ngân sách, không phải 90%.

    Cảnh báo ở 90% thì khi thấy cảnh báo đã gần hết ngân sách, không còn chỗ để
    xử lý.
    """

    # 400 request, SLO 99.5% -> ngân sách 2 lỗi. Dùng 2 là 100%... dùng 1.5 thì
    # không được, nên lấy 400 request và 2 lỗi để vượt 75%.
    rows = [_row(i) for i in range(398)]
    rows += [_row(i, status=500) for i in range(2)]
    report = trace_slo.evaluate_slos(rows)
    availability = next(s for s in report["slos"] if s["name"] == "availability")
    assert availability["status"] in (trace_slo.STATUS_AT_RISK, trace_slo.STATUS_BREACHED)
    assert availability["budget_used_pct"] >= trace_slo.AT_RISK_BUDGET_PCT


def test_latency_slo_counts_requests_under_the_threshold():
    """Đạt ĐÚNG BẰNG mục tiêu thì trạng thái là AT_RISK, không phải HEALTHY.

    Tôi viết test này kỳ vọng `HEALTHY` và nó đỏ — hoá ra code đúng hơn kỳ vọng
    của tôi. 95 nhanh / 5 chậm cho đúng 95.0%, tức bằng mục tiêu, tức **đã dùng
    hết 100% ngân sách lỗi**. Không còn chỗ cho một request chậm nữa mà không vi
    phạm, nên gọi nó là "ổn" sẽ che mất đúng lúc cần cảnh báo.
    """

    rows = [_row(i, duration=7000.0) for i in range(95)]
    rows += [_row(i, duration=20000.0) for i in range(5)]
    report = trace_slo.evaluate_slos(rows)
    latency = next(s for s in report["slos"] if s["name"] == "latency")
    assert latency["actual_pct"] == 95.0
    assert latency["status"] == trace_slo.STATUS_AT_RISK
    assert latency["budget_used_pct"] == 100.0
    assert latency["budget_remaining"] == 0.0

    # Và nhiều hơn một chút là vi phạm thật.
    rows.append(_row(0, duration=20000.0))
    worse = trace_slo.evaluate_slos(rows)
    assert next(s for s in worse["slos"] if s["name"] == "latency")["status"] == (trace_slo.STATUS_BREACHED)


def test_quality_slo_samples_llm_calls_not_requests():
    """Mẫu là SỐ LƯỢT GỌI LLM, vì guardrail xét từng lượt một.

    Một request `/analyze` nhiều chỉ số gọi LLM nhiều lần; chia theo request sẽ
    làm tỉ lệ nói về phiếu chứ không về câu trả lời.
    """

    rows = [_row(0, llm_calls=10, fallbacks=1)]
    report = trace_slo.evaluate_slos(rows)
    quality = next(s for s in report["slos"] if s["name"] == "quality")
    assert quality["sample_count"] == 11
    assert quality["actual_pct"] == pytest.approx(90.91, abs=0.01)


def test_thresholds_are_flagged_as_provisional():
    """Màn hình phải nói ra rằng ngưỡng chưa được nhóm chốt.

    Trình bày một ngưỡng đề xuất như đã thống nhất là cách chắc nhất để sau này
    không ai dám sửa nó, kể cả khi số đo cho thấy nó sai.
    """

    assert trace_slo.evaluate_slos([])["thresholds_provisional"] is True


def test_slo_ignores_non_ai_endpoints():
    rows = [_row(i, path="/api/v1/history", duration=50.0, status=500) for i in range(100)]
    report = trace_slo.evaluate_slos(rows)
    # Toàn bộ là API thường -> không có mẫu AI nào.
    assert report["overall_status"] == trace_slo.STATUS_NO_DATA
