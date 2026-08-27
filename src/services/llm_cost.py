"""Quy token thành tiền — hàm thuần, bảng giá khai tường minh.

## Đây là số CẤU HÌNH, không phải số ĐO ĐƯỢC

Token thì đo được: nhà cung cấp trả về trong `usage_metadata`. Giá thì không —
nó là con số người ta gõ vào bảng dưới đây, và nhà cung cấp đổi giá mà không hỏi
ai. Nên `cost_usd` là **ước lượng**, và mọi chỗ hiển thị nó phải nói vậy.

## Model lạ trả `None`, không trả 0.0

Đây là quyết định quan trọng nhất của module này. Nếu ai đó đổi `MODEL_NAME`
sang một model chưa có trong bảng, trả 0.0 sẽ làm dashboard hiện "chi phí hôm
nay $0.00" — đọc như miễn phí, trong khi thực tế là **không biết**. Hai thứ đó
khác nhau về bản chất, và trên một màn hình dùng để quyết định chuyện tiền thì
nhầm chúng là nhầm đắt.

`None` buộc lớp hiển thị phải chọn: hiện dấu gạch, hoặc hiện cảnh báo "chưa có
giá cho model X". Cả hai đều trung thực hơn `$0.00`.
"""

from __future__ import annotations

from dataclasses import dataclass

# Ngày cập nhật bảng giá. Ghi ra để người đọc biết con số này cũ bao nhiêu —
# một bảng giá không có ngày thì không ai biết nó còn đúng hay không.
PRICING_UPDATED = "2026-08-27"

# USD cho MỘT TRIỆU token. Khai theo triệu vì đó là đơn vị nhà cung cấp niêm
# yết; chia cho 1000 ở đây là tự tạo cơ hội nhầm ba số 0.
#
# Khoá là tiền tố tên model, so khớp theo tiền tố dài nhất — `gpt-4o-mini` phải
# thắng `gpt-4o`, nếu không mọi lời gọi mini sẽ bị tính giá của bản đầy đủ và
# chi phí báo cao gấp mười lần.
PRICE_PER_MILLION: dict[str, tuple[float, float]] = {
    # model                     (input, output)
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
}


@dataclass(frozen=True)
class CostBreakdown:
    model: str
    input_tokens: int
    output_tokens: int
    # `None` = chưa có giá cho model này. KHÔNG phải 0.0.
    input_usd: float | None
    output_usd: float | None
    total_usd: float | None
    priced: bool


def resolve_price(model: str | None) -> tuple[float, float] | None:
    """Giá của model, khớp theo tiền tố DÀI NHẤT. `None` khi chưa có giá.

    Khớp tiền tố vì tên model thật thường có hậu tố phiên bản
    (`gpt-4o-mini-2024-07-18`). Khớp dài nhất vì `gpt-4o-mini` phải thắng
    `gpt-4o` — ngược lại thì mọi lời gọi mini bị tính giá bản đầy đủ, và con số
    chi phí sai gấp mười lần theo hướng đáng sợ.
    """

    if not model:
        return None

    name = model.strip().lower()
    best: str | None = None
    for prefix in PRICE_PER_MILLION:
        if name.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return PRICE_PER_MILLION[best] if best else None


def compute_cost(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> CostBreakdown:
    """Ước lượng chi phí một hoặc nhiều lời gọi cùng model."""

    safe_model = (model or "").strip()
    safe_in = max(0, int(input_tokens or 0))
    safe_out = max(0, int(output_tokens or 0))

    price = resolve_price(safe_model)
    if price is None:
        return CostBreakdown(
            model=safe_model,
            input_tokens=safe_in,
            output_tokens=safe_out,
            input_usd=None,
            output_usd=None,
            total_usd=None,
            priced=False,
        )

    in_rate, out_rate = price
    input_usd = safe_in / 1_000_000 * in_rate
    output_usd = safe_out / 1_000_000 * out_rate
    return CostBreakdown(
        model=safe_model,
        input_tokens=safe_in,
        output_tokens=safe_out,
        # 6 chữ số thập phân: một lượt gpt-4o-mini tốn khoảng $0.0004, làm tròn
        # tới 4 chữ số là biến phần lớn lời gọi thành $0.0000.
        input_usd=round(input_usd, 6),
        output_usd=round(output_usd, 6),
        total_usd=round(input_usd + output_usd, 6),
        priced=True,
    )


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    """Chỉ con số tổng. `None` khi chưa có giá cho model."""

    return compute_cost(model, input_tokens, output_tokens).total_usd


__all__ = [
    "PRICE_PER_MILLION",
    "PRICING_UPDATED",
    "CostBreakdown",
    "compute_cost",
    "cost_usd",
    "resolve_price",
]
