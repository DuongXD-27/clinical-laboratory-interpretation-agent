"""Chuẩn hoá và kiểm tra email — một nguồn duy nhất cho mọi chỗ chạm vào email.

Ba đường ghi email vào DB (đăng ký, cập nhật hồ sơ) và một đường đọc (đăng nhập)
đều phải chuẩn hoá **giống hệt nhau**. Mỗi chỗ tự làm một kiểu là sinh ra lỗi
kinh điển: đăng ký `Duy@Gmail.com`, đăng nhập `duy@gmail.com`, không vào được,
mà thông báo lại là "sai mật khẩu".

Chuẩn hoá về chữ thường. Về lý thuyết phần trước `@` phân biệt hoa thường theo
RFC 5321, nhưng không nhà cung cấp thật nào làm vậy. Quan trọng hơn: nếu không
hạ chữ thường thì UNIQUE index vô dụng — `A@x.com` và `a@x.com` lọt thành hai
tài khoản khác nhau, và đăng nhập bằng email lại mơ hồ đúng như trước.
"""

from __future__ import annotations

import re

# Cố ý KHÔNG đúng chuẩn RFC 5322 — biểu thức đúng chuẩn dài hàng nghìn ký tự và
# vẫn chấp nhận những địa chỉ không ai gõ. Cái cần ở đây là chặn lỗi gõ thật:
# thiếu @, thiếu tên miền, thiếu chấm, có khoảng trắng, hai @.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# Giới hạn theo RFC 5321. Cột DB là String(320) nên chặn ở đây để lỗi hiện ra
# dưới dạng thông báo đọc được, không phải lỗi cắt chuỗi ở tầng driver.
MAX_EMAIL_LENGTH = 320


class InvalidEmailError(ValueError):
    """Email sai định dạng, kèm câu thông báo đọc được cho người dùng."""


def normalise_email(value: str | None) -> str | None:
    """Trả email đã chuẩn hoá, hoặc `None` khi bỏ trống.

    Chuỗi rỗng và chuỗi chỉ có khoảng trắng đều thành `None` chứ không thành
    `""`. Lý do: cột email cho phép NULL, và UNIQUE index chấp nhận nhiều NULL
    nhưng chỉ chấp nhận **một** chuỗi rỗng — để lọt `""` là người thứ hai bỏ
    trống email sẽ dính 409 mà không hiểu vì sao.
    """

    if value is None:
        return None

    cleaned = value.strip().lower()
    if not cleaned:
        return None

    if len(cleaned) > MAX_EMAIL_LENGTH:
        raise InvalidEmailError("Email quá dài.")

    if not _EMAIL_RE.match(cleaned):
        raise InvalidEmailError("Email chưa hợp lệ.")

    return cleaned


def looks_like_email(value: str) -> bool:
    """Đoán xem người dùng vừa gõ email hay tên đăng nhập.

    Chỉ dùng để chọn thông báo lỗi cho thân thiện. **Không** dùng để chọn cột
    tra cứu: `login()` luôn tra cả `username` lẫn `email` trong một câu truy
    vấn, nên một tên đăng nhập có ký tự `@` vẫn vào được bình thường.
    """

    return "@" in value


__all__ = [
    "MAX_EMAIL_LENGTH",
    "InvalidEmailError",
    "looks_like_email",
    "normalise_email",
]
