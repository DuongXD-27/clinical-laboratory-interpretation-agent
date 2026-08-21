"""Xác minh ID token của Google — nền cho nút "Đăng nhập bằng Google".

## Chọn luồng nào, và vì sao

Dùng Google Identity Services: trình duyệt lấy ID token từ Google rồi POST cho
backend, backend tự xác minh chữ ký. Không dùng authorization-code flow vì:

- Không cần client secret. Ít một bí mật phải cất trên Railway là ít một chỗ
  rò.
- Không phải khai và đồng bộ redirect URI cho localhost, Vercel preview và
  Vercel production — ba môi trường, ba URI, và sai một cái là lỗi khó đoán.

Đổi lại: **bắt buộc xác minh ở server**. Token do trình duyệt gửi lên, nên mọi
thứ trong đó là dữ liệu người dùng cung cấp cho tới khi chữ ký được kiểm.

## Ba điều kiện phải kiểm, thiếu một là thủng

`verify_oauth2_token()` lo chữ ký, hạn dùng và `aud`. Hai thứ còn lại phải tự
kiểm:

- `iss` phải là Google. Thư viện có kiểm, nhưng ghi lại tường minh vì đây là
  ranh giới tin cậy.
- `email_verified` phải là `True`. Google trả `False` được ở vài cấu hình
  Workspace, và ghép tài khoản theo một email chưa xác minh chính là đường
  chiếm tài khoản: chỉ cần khai một email không phải của mình.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import get_settings
from src.services.email_identity import normalise_email

logger = logging.getLogger(__name__)

_GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


class GoogleIdentityError(Exception):
    """Token không dùng được, kèm câu thông báo đọc được cho người dùng."""


@dataclass(frozen=True)
class GoogleIdentity:
    """Danh tính đã được Google xác nhận và server này kiểm lại."""

    email: str
    subject: str
    full_name: str | None


def is_configured() -> bool:
    return bool(get_settings().google_oauth_client_id)


def verify_id_token(credential: str) -> GoogleIdentity:
    """Kiểm ID token, trả danh tính. Ném `GoogleIdentityError` nếu không hợp lệ.

    Mọi nhánh hỏng đều ném cùng một loại lỗi với câu chữ chung. Tách ra
    "token hết hạn" / "sai audience" / "email chưa xác minh" là kể cho người gọi
    biết cách sửa token giả cho đúng.
    """

    settings = get_settings()
    client_id = settings.google_oauth_client_id
    if not client_id:
        raise GoogleIdentityError("Đăng nhập bằng Google chưa được cấu hình trên máy chủ.")

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_id,
        )
    except Exception:
        # Không log nguyên token: nó là chứng chỉ đăng nhập còn hiệu lực, ai đọc
        # được log là đăng nhập được.
        logger.info("google_id_token_rejected", exc_info=False)
        raise GoogleIdentityError("Không xác thực được tài khoản Google. Vui lòng thử lại.") from None

    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise GoogleIdentityError("Không xác thực được tài khoản Google. Vui lòng thử lại.")

    # `email_verified` về dạng bool: Google từng trả chuỗi "true" ở một số
    # phiên bản, và `if "false"` trong Python là True.
    verified = claims.get("email_verified")
    if isinstance(verified, str):
        verified = verified.lower() == "true"
    if not verified:
        raise GoogleIdentityError(
            "Tài khoản Google này chưa xác minh email nên chưa dùng để đăng nhập được."
        )

    email = normalise_email(claims.get("email"))
    if not email:
        raise GoogleIdentityError("Tài khoản Google này không có email để đăng nhập.")

    subject = str(claims.get("sub") or "")
    if not subject:
        raise GoogleIdentityError("Không xác thực được tài khoản Google. Vui lòng thử lại.")

    name = claims.get("name")
    return GoogleIdentity(
        email=email,
        subject=subject,
        full_name=str(name).strip() if name else None,
    )


__all__ = ["GoogleIdentity", "GoogleIdentityError", "is_configured", "verify_id_token"]
