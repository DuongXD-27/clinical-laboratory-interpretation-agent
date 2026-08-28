"""Chia trace thành các mốc thời gian cho biểu đồ — hàm thuần, không chạm DB.

## Vì sao kích thước mốc tự chọn theo cửa sổ

Cố định mốc 1 giờ thì cửa sổ "1 giờ qua" ra đúng **một** điểm — không phải biểu
đồ, mà là một con số vẽ to. Còn cửa sổ 7 ngày ra 168 điểm, dày hơn số pixel
ngang mà mắt phân biệt được, và mọi đỉnh bị nhoè thành một dải.

Nên mốc được chọn để mọi cửa sổ đều ra khoảng 12–30 điểm: đủ để thấy xu hướng,
đủ thưa để thấy một đỉnh đơn lẻ.

## Mốc rỗng vẫn được trả về

Một khoảng không có request nào vẫn là một mốc, với `count=0` và mọi phân vị là
`None`. Bỏ mốc rỗng đi thì biểu đồ nối liền hai điểm cách nhau sáu giờ thành một
đường thoải, và người đọc thấy một hệ thống chạy êm suốt đêm trong khi thực tế
nó không nhận request nào — có thể vì nó đã chết.

Đây là lý do `None` khác `0`: `p95=None` nghĩa là không đo được, `p95=0` nghĩa
là nhanh tuyệt đối.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.services.trace_metrics import GROUP_AI, classify_path, percentile

# (cua so toi da tinh bang phut, kich thuoc moc tinh bang phut)
# Chon de moi cua so ra khoang 12-30 diem.
_BUCKET_LADDER: tuple[tuple[float, int], ...] = (
    (90, 5),  # <= 1.5 gio  -> moc 5 phut   (18 diem cho 1 gio)
    (8 * 60, 30),  # <= 8 gio    -> moc 30 phut  (16 diem cho 8 gio)
    (36 * 60, 60),  # <= 36 gio   -> moc 1 gio    (24 diem cho 24 gio)
    (10 * 24 * 60, 360),  # <= 10 ngay -> moc 6 gio (28 diem cho 7 ngay)
)
_FALLBACK_BUCKET_MINUTES = 24 * 60


def pick_bucket_minutes(window_minutes: float) -> int:
    """Kích thước mốc cho một cửa sổ, sao cho biểu đồ ra 12–30 điểm."""

    for limit, size in _BUCKET_LADDER:
        if window_minutes <= limit:
            return size
    return _FALLBACK_BUCKET_MINUTES


@dataclass
class _Bucket:
    start: datetime
    durations: list[float] = field(default_factory=list)
    error_count: int = 0
    errors_by_type: dict[str, int] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    priced_any: bool = False
    llm_call_count: int = 0
    llm_error_count: int = 0
    guardrail_fallback_count: int = 0
    guardrail_rewrite_count: int = 0


def build_timeseries(
    rows: Iterable[object],
    *,
    since: datetime,
    until: datetime,
    group: str = GROUP_AI,
) -> dict[str, object]:
    """Chuỗi thời gian cho MỘT nhóm endpoint.

    Chỉ một nhóm, không trộn: mục đích của cả biểu đồ là thấy độ trễ của đường
    AI, mà trộn nó với hơn một nghìn request API thường thì đường P95 bị đè
    xuống đúng như con số trung bình 85ms đã làm.

    `until` truyền vào chứ không lấy `now()` bên trong: một hàm thuần đọc đồng
    hồ là một hàm không test được xác định.
    """

    window_minutes = max((until - since).total_seconds() / 60.0, 1.0)
    bucket_minutes = pick_bucket_minutes(window_minutes)
    step = timedelta(minutes=bucket_minutes)

    # Dựng sẵn TOÀN BỘ mốc, kể cả mốc sẽ rỗng. Xem docstring module.
    buckets: list[_Bucket] = []
    cursor = since
    while cursor < until:
        buckets.append(_Bucket(start=cursor))
        cursor += step
    if not buckets:
        buckets.append(_Bucket(start=since))

    def _index_for(moment: datetime) -> int | None:
        offset = (moment - since).total_seconds() / 60.0
        if offset < 0:
            return None
        index = int(offset // bucket_minutes)
        return index if 0 <= index < len(buckets) else None

    for row in rows:
        if (
            classify_path(
                str(getattr(row, "path", "") or ""),
                str(getattr(row, "method", "GET") or "GET"),
            )
            != group
        ):
            continue

        created = getattr(row, "created_at", None)
        if not isinstance(created, datetime):
            continue
        index = _index_for(created)
        if index is None:
            continue

        bucket = buckets[index]
        bucket.durations.append(float(getattr(row, "duration_ms", 0.0) or 0.0))

        status = int(getattr(row, "status_code", 0) or 0)
        if status >= 500:
            bucket.error_count += 1

        error_type = getattr(row, "error_type", None)
        if error_type:
            key = str(error_type)
            bucket.errors_by_type[key] = bucket.errors_by_type.get(key, 0) + 1

        bucket.input_tokens += int(getattr(row, "llm_input_tokens", 0) or 0)
        bucket.output_tokens += int(getattr(row, "llm_output_tokens", 0) or 0)
        bucket.llm_call_count += int(getattr(row, "llm_call_count", 0) or 0)
        bucket.llm_error_count += int(getattr(row, "llm_error_count", 0) or 0)
        bucket.guardrail_fallback_count += int(getattr(row, "guardrail_fallback_count", 0) or 0)
        bucket.guardrail_rewrite_count += int(getattr(row, "guardrail_rewrite_count", 0) or 0)

        cost = getattr(row, "llm_cost_usd", None)
        if cost is not None:
            bucket.cost_usd += float(cost)
            bucket.priced_any = True

    points = [
        {
            "start": bucket.start.isoformat(timespec="minutes"),
            "count": len(bucket.durations),
            "p50_ms": percentile(bucket.durations, 50),
            "p95_ms": percentile(bucket.durations, 95),
            "p99_ms": percentile(bucket.durations, 99),
            "error_count": bucket.error_count,
            "error_rate_pct": (
                round(bucket.error_count / len(bucket.durations) * 100, 2) if bucket.durations else None
            ),
            "errors_by_type": dict(sorted(bucket.errors_by_type.items())),
            "input_tokens": bucket.input_tokens,
            "output_tokens": bucket.output_tokens,
            "cost_usd": round(bucket.cost_usd, 6) if bucket.priced_any else None,
            "llm_call_count": bucket.llm_call_count,
            "llm_error_count": bucket.llm_error_count,
            "guardrail_fallback_count": bucket.guardrail_fallback_count,
            "guardrail_rewrite_count": bucket.guardrail_rewrite_count,
            # Ti le luot tra loi phai thay bang van ban dung san. Day la tin hieu
            # chat luong DO DUOC — khong phai groundedness, thu can mot bo danh
            # gia truc tuyen ma he thong chua co.
            "guardrail_fallback_rate_pct": (
                round(
                    bucket.guardrail_fallback_count / (bucket.guardrail_fallback_count + bucket.llm_call_count) * 100,
                    2,
                )
                if (bucket.guardrail_fallback_count + bucket.llm_call_count)
                else None
            ),
        }
        for bucket in buckets
    ]

    return {
        "group": group,
        "bucket_minutes": bucket_minutes,
        "since": since.isoformat(timespec="minutes"),
        "until": until.isoformat(timespec="minutes"),
        "points": points,
        # Moi nhom loi xuat hien trong ca cua so, de bieu do biet can bao nhieu
        # duong ma khong phai quet lai tung diem.
        "error_types": sorted({key for bucket in buckets for key in bucket.errors_by_type}),
    }


def total_error_breakdown(rows: Iterable[object]) -> list[dict[str, object]]:
    """Phân bố nhóm lỗi trong cả cửa sổ, nhiều nhất trước.

    Đây là thứ biến card "Lỗi 5xx — 3" thành bấm được: ba lỗi đó là gì.
    """

    counts: dict[str, int] = {}
    raw_examples: dict[str, str] = {}
    for row in rows:
        error_type = getattr(row, "error_type", None)
        if not error_type:
            continue
        key = str(error_type)
        counts[key] = counts.get(key, 0) + 1
        raw = getattr(row, "error_raw_type", None)
        if raw and key not in raw_examples:
            # Giu mot vi du ten lop nguyen ban: nhom loi noi "sua o dau", con ten
            # lop noi "sua cai gi".
            raw_examples[key] = str(raw)

    return [
        {"error_type": key, "count": count, "example_exception": raw_examples.get(key)}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


__all__ = ["build_timeseries", "pick_bucket_minutes", "total_error_breakdown"]
