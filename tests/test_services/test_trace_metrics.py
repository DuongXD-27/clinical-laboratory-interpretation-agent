"""Phân vị và chia nhóm endpoint — hàm thuần, test không cần DB.

Test quan trọng nhất trong file này là
`test_average_hides_the_long_tail_that_percentiles_expose`: nó dựng lại đúng
hình dạng dữ liệu production hôm nay (1200 request API ~50ms + 27 request AI
4–7s) và chứng minh bằng số rằng trung bình 85ms nói sai về trải nghiệm của
bệnh nhân. Không có test đó thì "thêm P95" chỉ là thêm một cột.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services.trace_metrics import (
    GROUP_AI,
    GROUP_API,
    classify_path,
    percentile,
    summarise_by_group,
)


def _row(path, duration_ms, *, method="POST", status=200, llm=0, llm_err=0):
    return SimpleNamespace(
        path=path,
        method=method,
        duration_ms=duration_ms,
        status_code=status,
        llm_call_count=llm,
        llm_error_count=llm_err,
    )


# --- chia nhóm ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analyze",
        "/api/v1/orchestrator/message",
        "/api/v1/orchestrator/message/stream",
        "/api/v1/ocr/upload",
    ],
)
def test_llm_endpoints_are_grouped_as_ai(path):
    assert classify_path(path) == GROUP_AI


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/login",
        "/api/v1/history",
        "/api/v1/conversations",
        "/api/v1/admin/traces",
        "/health",
    ],
)
def test_non_llm_endpoints_are_grouped_as_api(path):
    assert classify_path(path) == GROUP_API


def test_admin_traces_is_not_mistaken_for_ai():
    """Chia nhóm theo danh sách khai rõ, không theo tiền tố.

    `/api/v1/admin/traces` cũng nằm dưới `/api/v1/` và cũng là endpoint nội bộ,
    nhưng nó không gọi LLM. Xếp nó vào nhóm AI là tự làm loãng chính con số
    mình vừa tạo ra để đo LLM.
    """

    assert classify_path("/api/v1/admin/traces") == GROUP_API
    assert classify_path("/api/v1/admin/traces/summary") == GROUP_API


@pytest.mark.parametrize("method", ["OPTIONS", "options", "HEAD"])
def test_preflight_requests_are_excluded_entirely(method):
    """Preflight bị loại khỏi mẫu, không xếp vào nhóm nào.

    Nó không chạm DB, không chạm LLM, luôn ~0ms. Để nó trong mẫu là tự kéo mọi
    phân vị xuống. Trả `None` để nó biến mất, chứ không lặng lẽ chảy vào một
    nhóm thứ ba rồi có người đọc nó như số liệu thật.
    """

    assert classify_path("/api/v1/analyze", method) is None


# --- phân vị -----------------------------------------------------------------


def test_percentile_matches_linear_interpolation_definition():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile(values, 50) == 5.5
    assert percentile(values, 0) == 1.0
    assert percentile(values, 100) == 10.0


def test_percentile_returns_none_for_an_empty_sample():
    """`None`, không phải 0.0.

    Trên màn hình vận hành, `0ms` đọc như "nhanh tuyệt đối" còn `None` đọc như
    "chưa có dữ liệu". Nhầm hai thứ đó là loại nhầm dẫn tới kết luận sai.
    """

    assert percentile([], 95) is None
    assert percentile([], 50) is None


def test_percentile_handles_a_single_sample():
    assert percentile([42.0], 95) == 42.0


def test_percentile_is_order_independent():
    a = percentile([5, 1, 9, 3, 7], 95)
    b = percentile([9, 7, 5, 3, 1], 95)
    assert a == b


# --- vì sao cần phân vị: dựng lại đúng dữ liệu production --------------------


def test_average_hides_the_long_tail_that_percentiles_expose():
    """Đúng hình dạng dữ liệu production ngày 27/08: avg 85ms, max 6.85s.

    1200 request API ~50ms trộn với 27 request AI 4–7s. Trung bình toàn hệ
    thống ra ~85ms và nhìn rất đẹp, trong khi bệnh nhân thật đang chờ hàng
    giây. Test này ghim lại con số để "thêm P95" không chỉ là thêm một cột.
    """

    rows = [_row("/api/v1/history", 50.0, method="GET") for _ in range(1200)]
    rows += [_row("/api/v1/analyze", 4000.0 + i * 100, llm=1) for i in range(27)]

    overall_avg = sum(r.duration_ms for r in rows) / len(rows)
    assert overall_avg < 200, "trung bình toàn hệ thống nhìn rất nhanh"

    groups = summarise_by_group(rows)

    # Nhóm API: đúng là nhanh.
    assert groups[GROUP_API]["count"] == 1200
    assert groups[GROUP_API]["p95_ms"] == 50.0

    # Nhóm AI: chậm, và giờ nhìn thấy được.
    assert groups[GROUP_AI]["count"] == 27
    assert groups[GROUP_AI]["p50_ms"] >= 5000
    assert groups[GROUP_AI]["p95_ms"] >= 6000
    assert groups[GROUP_AI]["llm_call_count"] == 27

    # Điểm của cả bài: P95 của nhóm AI lớn hơn trung bình toàn hệ thống hàng
    # chục lần. Đó là khoảng cách giữa "dashboard nhìn xanh" và "bệnh nhân chờ".
    assert groups[GROUP_AI]["p95_ms"] > overall_avg * 30


def test_preflight_noise_does_not_move_the_percentiles():
    """Đối chứng: thêm 500 preflight 0ms vào không được làm phân vị nhúc nhích."""

    real = [_row("/api/v1/analyze", 4000.0 + i, llm=1) for i in range(20)]
    before = summarise_by_group(real)[GROUP_AI]

    noisy = real + [_row("/api/v1/analyze", 0.0, method="OPTIONS") for _ in range(500)]
    after = summarise_by_group(noisy)[GROUP_AI]

    assert before == after


# --- tỉ lệ lỗi ---------------------------------------------------------------


def test_error_rate_counts_only_server_errors():
    """4xx không tính là lỗi hệ thống.

    Đếm 4xx vào error rate sẽ làm một đợt quét URL của bot, hoặc một loạt 404
    từ việc dò conversation id, trông như hệ thống đang sập.
    """

    rows = [
        _row("/api/v1/analyze", 100.0, status=200),
        _row("/api/v1/analyze", 100.0, status=404),
        _row("/api/v1/analyze", 100.0, status=422),
        _row("/api/v1/analyze", 100.0, status=500),
    ]
    ai = summarise_by_group(rows)[GROUP_AI]
    assert ai["error_count"] == 1
    assert ai["error_rate_pct"] == 25.0


def test_error_rate_is_none_when_there_are_no_requests():
    groups = summarise_by_group([])
    assert groups[GROUP_AI]["count"] == 0
    assert groups[GROUP_AI]["error_rate_pct"] is None
    assert groups[GROUP_AI]["p95_ms"] is None


# --- QPS ---------------------------------------------------------------------


def test_request_rate_needs_an_explicit_window():
    """Không có cửa sổ thời gian thì không có QPS — thà thiếu hơn đoán bừa."""

    rows = [_row("/api/v1/analyze", 100.0) for _ in range(120)]
    assert summarise_by_group(rows)[GROUP_AI]["requests_per_min"] is None
    assert summarise_by_group(rows, window_minutes=60)[GROUP_AI]["requests_per_min"] == 2.0


def test_zero_window_does_not_divide_by_zero():
    rows = [_row("/api/v1/analyze", 100.0)]
    assert summarise_by_group(rows, window_minutes=0)[GROUP_AI]["requests_per_min"] is None


# --- hợp đồng ----------------------------------------------------------------


def test_group_payload_never_exposes_an_average():
    """`avg` không được có mặt trong payload.

    Để nó ở đó là mời người đọc quay lại đúng con số đã che mất long tail. Bỏ
    hẳn thì màn hình buộc phải nói bằng phân vị.
    """

    groups = summarise_by_group([_row("/api/v1/analyze", 100.0)])
    for payload in groups.values():
        assert "avg" not in payload
        assert "avg_duration_ms" not in payload


def test_malformed_rows_do_not_crash_the_summary():
    rows = [
        SimpleNamespace(path="/api/v1/analyze", method="POST"),  # thiếu mọi số
        _row("/api/v1/analyze", 100.0),
    ]
    ai = summarise_by_group(rows)[GROUP_AI]
    assert ai["count"] == 2
