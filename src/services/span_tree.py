"""Dựng cây span từ chuỗi `Server-Timing` đã lưu — hàm thuần, không chạm DB.

## Dữ liệu đã có sẵn, chỉ chưa ai đọc

`request_traces.server_timing` giữ nguyên chuỗi Server-Timing của từng request.
Một `/analyze` thật trên production:

    analysis-reference-range;dur=3.981, analysis-critical-detector;dur=0.049,
    analysis-analyzer;dur=4635.545, analysis-generate-questions;dur=0.953,
    analysis-guardrail;dur=1.233, analysis-graph-total;dur=4651.840,
    analysis-response-map;dur=0.044, db-query;dur=239.935,
    http-total;dur=4991.885

Đủ để trả lời "4.99 giây chậm vì đâu" mà màn admin đang chỉ hiện TOTAL/CSDL/LLM.

## Thứ đáng giá nhất là dòng "chưa đo được"

Cây span dễ tạo cảm giác đã giải thích hết thời gian. Thường thì không: với
trace ở trên, `http-total` 4991.9ms trừ đi mọi con của nó còn **339.9ms** không
nằm trong span nào — đó là parse request, xác thực, ghi DB, serialize. Không
hiện con số đó thì người đọc kết luận "LLM chiếm 93%, hết chuyện", và bỏ qua
1/3 giây không ai biết đi đâu.

Nên mỗi nút chứa con đều có một dòng `unaccounted`. Nó là lời thú nhận của
chính lớp đo lường về phần nó không thấy.

## Vì sao khai quan hệ cha–con tường minh

Đoán theo tiền tố sẽ sai ngay: `analysis-graph-total` và `analysis-analyzer`
cùng tiền tố nhưng một cái chứa cái kia. Bảng khai rõ thì đọc `git diff` là
thấy ai đổi cấu trúc.

Span lạ **không bị bỏ đi** — nó treo ở gốc. Thêm một `timing_span` mới mà quên
khai cha thì nó vẫn hiện ra, chỉ là hiện sai chỗ. Hướng hỏng đó an toàn hơn
việc lặng lẽ biến mất.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROOT_SPAN = "http-total"

# Span đo bằng cách CỘNG DỒN qua cả request, không phải một khoảng liền mạch.
# Để nó vào cây là làm số học trông như sai: tổng con sẽ vượt cha, vì truy vấn
# DB rải rác khắp nhiều nhánh. Hiện riêng.
AGGREGATE_SPANS: frozenset[str] = frozenset({"db-query"})

# Quan hệ cha–con, khai từ chính mã nguồn chứ không từ suy đoán:
# `graph.py` bọc từng node, `ocr_routes.py` và `vision_adapter.py` bọc từng bước.
SPAN_PARENTS: dict[str, str] = {
    # --- pipeline phân tích (src/agents/graph.py) ---
    "analysis-graph-total": ROOT_SPAN,
    "analysis-ui-review-gate": "analysis-graph-total",
    "analysis-reference-range": "analysis-graph-total",
    "analysis-critical-detector": "analysis-graph-total",
    "analysis-analyzer": "analysis-graph-total",
    "analysis-generate-questions": "analysis-graph-total",
    "analysis-guardrail": "analysis-graph-total",
    "analysis-response-map": ROOT_SPAN,
    # --- đường OCR (src/api/ocr_routes.py) ---
    "ocr-file-read": ROOT_SPAN,
    "ocr-sample-policy-check": ROOT_SPAN,
    "ocr-preprocess": ROOT_SPAN,
    "ocr-vision-extract": ROOT_SPAN,
    "ocr-build-analysis-request": ROOT_SPAN,
    "ocr-review-prepare": ROOT_SPAN,
    "ocr-review-validate": ROOT_SPAN,
    "ocr-review-consume": ROOT_SPAN,
    # --- tiền xử lý ảnh ---
    "image-processor-init": "ocr-preprocess",
    "image-decode": "ocr-preprocess",
    "image-auto-contrast": "ocr-preprocess",
    "image-deskew": "ocr-preprocess",
    "image-resize": "ocr-preprocess",
    "image-jpeg-encode": "ocr-preprocess",
    # --- gọi vision (src/adapters/vision_adapter.py) ---
    "vision-total": "ocr-vision-extract",
    "vision-client-init": "vision-total",
    "openrouter-base64": "vision-total",
    "vision-parse": "vision-total",
}

# `name;dur=123.4`. Server-Timing cho phép thêm `desc`, nên chỉ bắt phần cần.
_ENTRY_RE = re.compile(r"^\s*(?P<name>[A-Za-z0-9_.-]+)\s*;\s*dur\s*=\s*(?P<dur>[0-9.]+)")


@dataclass
class SpanNode:
    name: str
    duration_ms: float
    depth: int = 0
    # Phần thời gian của nút này không nằm trong bất kỳ con nào. `None` khi nút
    # không có con — khác hẳn 0.0, vốn nghĩa là "có con và chúng giải thích hết".
    unaccounted_ms: float | None = None
    share_pct: float | None = None
    children: list[SpanNode] = field(default_factory=list)

    def as_row(self) -> dict[str, object]:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "depth": self.depth,
            "unaccounted_ms": (
                round(self.unaccounted_ms, 3) if self.unaccounted_ms is not None else None
            ),
            "share_pct": self.share_pct,
        }


def parse_server_timing(raw: str | None) -> dict[str, float]:
    """Chuỗi Server-Timing -> {tên: ms}. Bỏ qua phần không đọc được.

    Bỏ qua chứ không nổ: `server_timing` là dữ liệu quan sát, và một dòng trace
    méo không được phép làm màn hình admin trắng xoá — nhất là khi người ta mở
    màn đó ra chính vì hệ thống đang có vấn đề.
    """

    if not raw:
        return {}

    result: dict[str, float] = {}
    for chunk in raw.split(","):
        match = _ENTRY_RE.match(chunk)
        if match is None:
            continue
        try:
            result[match.group("name")] = float(match.group("dur"))
        except ValueError:
            continue
    return result


def build_span_tree(raw: str | None) -> dict[str, object]:
    """Cây span phẳng hoá theo thứ tự hiển thị, kèm dòng thời gian chưa đo được.

    Trả danh sách phẳng có `depth` chứ không trả cấu trúc lồng: giao diện chỉ
    cần thụt lề theo `depth`, và một danh sách phẳng thì không đệ quy được sai.
    """

    measured = parse_server_timing(raw)
    if not measured:
        return {"rows": [], "aggregates": [], "total_ms": None}

    aggregates = [
        {"name": name, "duration_ms": round(measured[name], 3)}
        for name in sorted(AGGREGATE_SPANS)
        if name in measured
    ]

    total_ms = measured.get(ROOT_SPAN)

    # Con của từng nút. Span lạ treo ở gốc thay vì bị bỏ.
    children_of: dict[str, list[str]] = {}
    for name in measured:
        if name == ROOT_SPAN or name in AGGREGATE_SPANS:
            continue
        parent = SPAN_PARENTS.get(name, ROOT_SPAN)
        # Cha được khai nhưng không có trong lần đo này (ví dụ request không đi
        # qua OCR): nâng con lên gốc, để nó không mất tăm.
        if parent != ROOT_SPAN and parent not in measured:
            parent = ROOT_SPAN
        children_of.setdefault(parent, []).append(name)

    rows: list[dict[str, object]] = []

    def emit(name: str, depth: int) -> None:
        duration = measured[name]
        kids = sorted(children_of.get(name, []), key=lambda k: -measured[k])

        unaccounted: float | None = None
        if kids:
            unaccounted = duration - sum(measured[k] for k in kids)
            # Kẹp về 0 khi âm: span lồng nhau đo bằng đồng hồ tường nên sai số
            # làm phép trừ có thể ra -0.02ms, và một dòng "-0.02ms chưa đo được"
            # chỉ làm người đọc mất tin vào cả bảng.
            if unaccounted < 0:
                unaccounted = 0.0

        node = SpanNode(
            name=name,
            duration_ms=duration,
            depth=depth,
            unaccounted_ms=unaccounted,
            share_pct=(
                round(duration / total_ms * 100, 1) if total_ms and total_ms > 0 else None
            ),
        )
        rows.append(node.as_row())
        for kid in kids:
            emit(kid, depth + 1)

    if ROOT_SPAN in measured:
        emit(ROOT_SPAN, 0)
    else:
        # Không có `http-total` (trace từ bản cũ, hoặc middleware chưa chạy):
        # vẫn hiện những gì đo được, ở cùng một mức.
        for name in sorted(measured, key=lambda k: -measured[k]):
            if name in AGGREGATE_SPANS:
                continue
            rows.append(
                SpanNode(name=name, duration_ms=measured[name], depth=0).as_row()
            )

    return {"rows": rows, "aggregates": aggregates, "total_ms": total_ms}


__all__ = [
    "AGGREGATE_SPANS",
    "ROOT_SPAN",
    "SPAN_PARENTS",
    "SpanNode",
    "build_span_tree",
    "parse_server_timing",
]
