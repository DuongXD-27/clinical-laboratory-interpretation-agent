"""Dựng cây span từ `server_timing` — hàm thuần, test không cần DB.

Mốc dùng xuyên suốt file này là chuỗi `server_timing` THẬT của một request
`/analyze` trên production ngày 27/08. Dùng dữ liệu thật thay vì số bịa để khi
test đỏ, thông báo lỗi chỉ vào đúng một request có thể mở lại được.
"""

from __future__ import annotations

import pytest

from src.services.span_tree import (
    ROOT_SPAN,
    SPAN_PARENTS,
    build_span_tree,
    parse_server_timing,
)

# Nguyên văn, lấy từ `GET /admin/traces/{request_id}` trên production.
PRODUCTION_ANALYZE = (
    "analysis-reference-range;dur=3.981, analysis-critical-detector;dur=0.049, "
    "analysis-analyzer;dur=4635.545, analysis-generate-questions;dur=0.953, "
    "analysis-guardrail;dur=1.233, analysis-graph-total;dur=4651.840, "
    "analysis-response-map;dur=0.044, db-query;dur=239.935, http-total;dur=4991.885"
)


def _rows_by_name(tree):
    return {row["name"]: row for row in tree["rows"]}


# --- parse -------------------------------------------------------------------


def test_parses_every_entry_of_a_real_production_string():
    parsed = parse_server_timing(PRODUCTION_ANALYZE)
    assert parsed["http-total"] == 4991.885
    assert parsed["analysis-analyzer"] == 4635.545
    assert parsed["db-query"] == 239.935
    assert len(parsed) == 9


@pytest.mark.parametrize("raw", [None, "", "   ", ",,,"])
def test_empty_input_gives_an_empty_tree(raw):
    tree = build_span_tree(raw)
    assert tree["rows"] == []
    assert tree["total_ms"] is None


def test_malformed_entries_are_skipped_not_raised():
    """Một dòng trace méo không được làm màn admin trắng xoá.

    Người ta mở màn đó ra chính vì hệ thống đang có vấn đề; đó là lúc tệ nhất
    để nó nổ.
    """

    parsed = parse_server_timing("good;dur=1.5, rác-không-có-dur, khác;dur=abc, hai;dur=2")
    assert parsed == {"good": 1.5, "hai": 2.0}


# --- cấu trúc cây ------------------------------------------------------------


def test_graph_nodes_nest_under_graph_total():
    rows = _rows_by_name(build_span_tree(PRODUCTION_ANALYZE))

    assert rows["http-total"]["depth"] == 0
    assert rows["analysis-graph-total"]["depth"] == 1
    for node in (
        "analysis-analyzer",
        "analysis-reference-range",
        "analysis-critical-detector",
        "analysis-generate-questions",
        "analysis-guardrail",
    ):
        assert rows[node]["depth"] == 2, f"{node} phải là con của analysis-graph-total"


def test_children_are_ordered_slowest_first():
    """Nút chậm nhất lên đầu — người mở cây span đang đi tìm chỗ chậm."""

    tree = build_span_tree(PRODUCTION_ANALYZE)
    graph_children = [row["name"] for row in tree["rows"] if row["depth"] == 2 and row["name"].startswith("analysis-")]
    assert graph_children[0] == "analysis-analyzer"


def test_db_query_is_kept_out_of_the_tree():
    """`db-query` là số CỘNG DỒN, không phải một khoảng liền mạch.

    Truy vấn DB rải rác khắp nhiều nhánh, nên đưa nó vào cây sẽ làm tổng con
    vượt cha và cả bảng trông như tính sai.
    """

    tree = build_span_tree(PRODUCTION_ANALYZE)
    assert "db-query" not in _rows_by_name(tree)
    assert tree["aggregates"] == [{"name": "db-query", "duration_ms": 239.935}]


# --- thời gian chưa đo được: phần đáng giá nhất ------------------------------


def test_unaccounted_time_at_the_root_is_surfaced():
    """4991.9 − (4651.8 + 0.044) = 339.9ms không nằm trong span nào.

    Đó là parse request, xác thực, ghi DB, serialize. Không hiện con số này thì
    người đọc kết luận "LLM chiếm 93%, hết chuyện" và bỏ qua 1/3 giây không ai
    biết đi đâu.
    """

    rows = _rows_by_name(build_span_tree(PRODUCTION_ANALYZE))
    assert rows[ROOT_SPAN]["unaccounted_ms"] == pytest.approx(340.001, abs=0.01)


def test_unaccounted_time_inside_the_graph_is_surfaced():
    rows = _rows_by_name(build_span_tree(PRODUCTION_ANALYZE))
    children = 3.981 + 0.049 + 4635.545 + 0.953 + 1.233
    assert rows["analysis-graph-total"]["unaccounted_ms"] == pytest.approx(4651.840 - children, abs=0.01)


def test_leaf_nodes_report_none_not_zero_unaccounted():
    """Lá trả `None`, không phải 0.0.

    `0.0` nghĩa là "có con và chúng giải thích hết thời gian" — một khẳng định
    thật. Lá thì không có gì để khẳng định. Trộn hai thứ đó là bịa ra một kết
    luận không đo được.
    """

    rows = _rows_by_name(build_span_tree(PRODUCTION_ANALYZE))
    assert rows["analysis-analyzer"]["unaccounted_ms"] is None
    assert rows["analysis-guardrail"]["unaccounted_ms"] is None


def test_negative_unaccounted_is_clamped_to_zero():
    """Sai số đồng hồ tường không được hiện thành "-0.02ms chưa đo được"."""

    raw = "analysis-analyzer;dur=100.02, analysis-graph-total;dur=100.0, http-total;dur=100.0"
    rows = _rows_by_name(build_span_tree(raw))
    assert rows["analysis-graph-total"]["unaccounted_ms"] == 0.0


# --- tỉ lệ -------------------------------------------------------------------


def test_share_is_relative_to_the_root_total():
    rows = _rows_by_name(build_span_tree(PRODUCTION_ANALYZE))
    assert rows["http-total"]["share_pct"] == 100.0
    # LLM chiếm phần lớn thời gian — đây là câu trả lời cho "chậm vì đâu".
    assert rows["analysis-analyzer"]["share_pct"] == pytest.approx(92.9, abs=0.2)
    assert rows["analysis-guardrail"]["share_pct"] < 1


# --- hướng hỏng an toàn ------------------------------------------------------


def test_an_undeclared_span_hangs_off_the_root_instead_of_vanishing():
    """Thêm `timing_span` mới mà quên khai cha thì nó vẫn hiện, chỉ sai chỗ.

    Hướng hỏng đó an toàn hơn việc lặng lẽ biến mất: một span không hiện ra thì
    không ai biết mình đang thiếu số liệu.
    """

    raw = "span-chua-khai;dur=50.0, http-total;dur=100.0"
    rows = _rows_by_name(build_span_tree(raw))
    assert "span-chua-khai" in rows
    assert rows["span-chua-khai"]["depth"] == 1


def test_child_is_lifted_when_its_declared_parent_was_not_measured():
    """Request không đi qua OCR thì `image-decode` không có cha — vẫn phải hiện."""

    raw = "image-decode;dur=12.0, http-total;dur=100.0"
    rows = _rows_by_name(build_span_tree(raw))
    assert rows["image-decode"]["depth"] == 1


def test_tree_without_http_total_still_shows_what_was_measured():
    raw = "analysis-analyzer;dur=900.0, analysis-guardrail;dur=2.0"
    tree = build_span_tree(raw)
    names = [row["name"] for row in tree["rows"]]
    assert names == ["analysis-analyzer", "analysis-guardrail"]
    assert tree["total_ms"] is None
    assert all(row["share_pct"] is None for row in tree["rows"])


def test_every_declared_parent_is_itself_a_known_span():
    """Bảng khai không được trỏ tới một cha không tồn tại ở đâu cả.

    Một `SPAN_PARENTS` trỏ sai chỉ hiện ra thành "con treo ở gốc" lúc chạy —
    im lặng. Chốt ở đây để lỗi đánh máy lộ ra lúc test.
    """

    known = set(SPAN_PARENTS) | {ROOT_SPAN}
    for child, parent in SPAN_PARENTS.items():
        assert parent in known, f"{child} khai cha là {parent!r}, không phải span nào"


def test_ocr_pipeline_nests_three_levels_deep():
    raw = (
        "image-decode;dur=5.0, image-resize;dur=3.0, ocr-preprocess;dur=10.0, "
        "vision-parse;dur=4.0, openrouter-base64;dur=6.0, vision-total;dur=30000.0, "
        "ocr-vision-extract;dur=30010.0, http-total;dur=30100.0"
    )
    rows = _rows_by_name(build_span_tree(raw))
    assert rows["ocr-vision-extract"]["depth"] == 1
    assert rows["vision-total"]["depth"] == 2
    assert rows["openrouter-base64"]["depth"] == 3
    assert rows["ocr-preprocess"]["depth"] == 1
    assert rows["image-decode"]["depth"] == 2
