"""Tính phân vị và tỉ lệ lỗi từ các dòng trace — hàm thuần, không chạm DB.

## Vì sao trung bình là con số vô dụng ở đây

Màn `/admin` đang hiện `TRUNG BÌNH: 85ms` trên 1213 request, trong khi
`CHẬM NHẤT: 6.85s`. Hai con số đó không mâu thuẫn: khoảng 1200 request API
thường chạy ~50ms, còn ~27 request đi qua LLM mất 4–7 giây. Trung bình bị nhóm
đông đè xuống, nên nó trả lời câu "hệ thống nhìn chung thế nào" — mà không ai
cần câu đó. Câu cần trả lời là "bệnh nhân đang chờ bao lâu", và đó là P95 của
riêng nhóm AI.

Đây là lý do module này làm hai việc cùng lúc, không tách rời được:

1. **Chia nhóm endpoint trước.** Trộn `/analyze` với `OPTIONS /auth/login` thì
   mọi phân vị đều vô nghĩa, kể cả P99.
2. **Rồi mới tính phân vị trong từng nhóm.**

## Vì sao tính bằng Python chứ không bằng SQL

Postgres có `percentile_cont`, SQLite không. Repo này chạy SQLite ở máy dev và
Postgres ở production, và mỗi lần một đường code chỉ tồn tại ở một trong hai
dialect thì bộ test không bắt được — đúng vụ `String(64)` vừa rồi. Với vài
nghìn dòng mỗi ngày, tải về rồi tính trong Python vừa đủ nhanh, vừa cho ra CÙNG
một con số ở cả hai môi trường.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# Nhóm endpoint đi qua LLM. Khai tường minh chứ không đoán theo tiền tố:
# `/api/v1/admin/traces` cũng bắt đầu bằng `/api/v1/` nhưng không phải AI, và
# một danh sách khai rõ thì đọc `git diff` là thấy ai thêm gì.
AI_PATH_MARKERS: tuple[str, ...] = (
    "/analyze",
    "/orchestrator/message",
    "/ocr/upload",
    "/ocr/confirm",
    "/trend-explanation",
    "/trends/explanation",
    "/patient/trends/explain",
)

GROUP_AI = "ai"
GROUP_API = "api"

# Preflight CORS không phản ánh gì về hệ thống: nó không chạm DB, không chạm
# LLM, và luôn ~0ms. Để nó trong mẫu là tự kéo mọi phân vị xuống.
EXCLUDED_METHODS: frozenset[str] = frozenset({"OPTIONS", "HEAD"})


def classify_path(path: str, method: str = "GET") -> str | None:
    """Xếp một request vào nhóm. `None` nghĩa là không tính vào phân vị nào.

    Trả `None` chứ không xếp vào nhóm "khác": một request bị loại phải biến mất
    khỏi mẫu, không được lặng lẽ chảy vào một nhóm thứ ba rồi có người đọc nó
    như số liệu thật.
    """

    if method.upper() in EXCLUDED_METHODS:
        return None
    if any(marker in path for marker in AI_PATH_MARKERS):
        return GROUP_AI
    return GROUP_API


def percentile(values: Sequence[float], q: float) -> float | None:
    """Phân vị theo nội suy tuyến tính, cùng định nghĩa với `numpy.percentile`.

    `q` trong khoảng 0..100. Trả `None` khi không có mẫu — KHÔNG trả 0.0, vì 0ms
    đọc như "nhanh tuyệt đối" còn `None` đọc như "chưa có dữ liệu", và trên một
    màn hình vận hành thì nhầm hai thứ đó là nhầm nguy hiểm.
    """

    if not values:
        return None
    if len(values) == 1:
        return round(float(values[0]), 1)

    ordered = sorted(values)
    position = (len(ordered) - 1) * (q / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(float(ordered[int(position)]), 1)
    weight = position - lower
    return round(float(ordered[lower] * (1 - weight) + ordered[upper] * weight), 1)


@dataclass
class GroupMetrics:
    """Số liệu của một nhóm endpoint.

    Không có trường `avg`. Cố ý: để nó ở đây là mời người đọc quay lại đúng con
    số đã che mất long tail. Ai cần trung bình thì tự tính từ `count`.
    """

    group: str
    count: int = 0
    p50_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None
    max_ms: float | None = None
    error_count: int = 0
    error_rate_pct: float | None = None
    requests_per_min: float | None = None
    llm_call_count: int = 0
    llm_error_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # `None` = khong loi goi nao trong nhom nay tinh duoc gia. Khong phai 0.0.
    cost_usd: float | None = None
    unpriced_call_count: int = 0
    cost_per_call_usd: float | None = None
    # TTFT — do tre phia nha cung cap, KHONG phai TTFT nguoi dung cam nhan:
    # he thong khong stream ra client vi guardrail phai la lop cuoi (ADR-004).
    # `None` khi chua bat streaming.
    ttft_p50_ms: float | None = None
    ttft_p95_ms: float | None = None
    # Khac 0 nghia la co luot goi bao 0 token — gan nhu chac chan loi do luong.
    missing_usage_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "count": self.count,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "max_ms": self.max_ms,
            "error_count": self.error_count,
            "error_rate_pct": self.error_rate_pct,
            "requests_per_min": self.requests_per_min,
            "llm_call_count": self.llm_call_count,
            "llm_error_count": self.llm_error_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "unpriced_call_count": self.unpriced_call_count,
            "cost_per_call_usd": self.cost_per_call_usd,
            "ttft_p50_ms": self.ttft_p50_ms,
            "ttft_p95_ms": self.ttft_p95_ms,
            "missing_usage_count": self.missing_usage_count,
        }


@dataclass
class _Accumulator:
    durations: list[float] = field(default_factory=list)
    error_count: int = 0
    llm_call_count: int = 0
    llm_error_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    priced_any: bool = False
    unpriced_call_count: int = 0
    ttfts: list[float] = field(default_factory=list)
    missing_usage_count: int = 0


def summarise_by_group(
    rows: Iterable[object],
    *,
    window_minutes: float | None = None,
) -> dict[str, dict[str, object]]:
    """Gom các dòng trace thành số liệu theo nhóm.

    `rows` là bất cứ thứ gì có `path`, `method`, `duration_ms`, `status_code`,
    `llm_call_count`, `llm_error_count` — nhận theo hình dáng chứ không nhận
    đúng một lớp, để test dựng được dữ liệu bằng `SimpleNamespace` mà không cần
    tạo bảng.

    `window_minutes` chỉ dùng để tính QPS. Thiếu nó thì `requests_per_min` là
    `None` — thà không có con số hơn là có một con số chia cho khoảng thời gian
    đoán bừa.
    """

    buckets: dict[str, _Accumulator] = {GROUP_AI: _Accumulator(), GROUP_API: _Accumulator()}

    for row in rows:
        group = classify_path(
            str(getattr(row, "path", "") or ""),
            str(getattr(row, "method", "GET") or "GET"),
        )
        if group is None:
            continue

        acc = buckets[group]
        acc.durations.append(float(getattr(row, "duration_ms", 0.0) or 0.0))

        status = int(getattr(row, "status_code", 0) or 0)
        # Chỉ 5xx tính là lỗi hệ thống. 4xx là client gửi sai — đếm nó vào
        # error rate sẽ làm một đợt quét URL của bot trông như hệ thống đang sập.
        if status >= 500:
            acc.error_count += 1

        acc.llm_call_count += int(getattr(row, "llm_call_count", 0) or 0)
        acc.llm_error_count += int(getattr(row, "llm_error_count", 0) or 0)
        acc.input_tokens += int(getattr(row, "llm_input_tokens", 0) or 0)
        acc.output_tokens += int(getattr(row, "llm_output_tokens", 0) or 0)
        acc.unpriced_call_count += int(getattr(row, "llm_unpriced_call_count", 0) or 0)

        acc.missing_usage_count += int(getattr(row, "llm_missing_usage_count", 0) or 0)
        row_ttft = getattr(row, "llm_ttft_ms", None)
        if row_ttft is not None:
            acc.ttfts.append(float(row_ttft))

        row_cost = getattr(row, "llm_cost_usd", None)
        if row_cost is not None:
            acc.cost_usd += float(row_cost)
            acc.priced_any = True

    result: dict[str, dict[str, object]] = {}
    for group, acc in buckets.items():
        count = len(acc.durations)
        metrics = GroupMetrics(
            group=group,
            count=count,
            p50_ms=percentile(acc.durations, 50),
            p95_ms=percentile(acc.durations, 95),
            p99_ms=percentile(acc.durations, 99),
            max_ms=round(max(acc.durations), 1) if acc.durations else None,
            error_count=acc.error_count,
            error_rate_pct=round(acc.error_count / count * 100, 2) if count else None,
            requests_per_min=(round(count / window_minutes, 2) if window_minutes and window_minutes > 0 else None),
            llm_call_count=acc.llm_call_count,
            llm_error_count=acc.llm_error_count,
            input_tokens=acc.input_tokens,
            output_tokens=acc.output_tokens,
            cost_usd=round(acc.cost_usd, 6) if acc.priced_any else None,
            unpriced_call_count=acc.unpriced_call_count,
            # Chia cho SO LUOT GOI LLM, khong phai so request: mot request
            # `/analyze` nhieu chi so goi LLM nhieu lan, con mot request khong
            # goi LLM thi khong nen keo con so nay xuong.
            cost_per_call_usd=(
                round(acc.cost_usd / acc.llm_call_count, 6) if acc.priced_any and acc.llm_call_count else None
            ),
            ttft_p50_ms=percentile(acc.ttfts, 50),
            ttft_p95_ms=percentile(acc.ttfts, 95),
            missing_usage_count=acc.missing_usage_count,
        )
        result[group] = metrics.as_dict()

    return result


__all__ = [
    "AI_PATH_MARKERS",
    "GROUP_AI",
    "GROUP_API",
    "GroupMetrics",
    "classify_path",
    "percentile",
    "summarise_by_group",
]
