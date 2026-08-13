"""Hash mật khẩu + tạo/xác thực JWT. Không phụ thuộc DB (tránh import vòng).

Ba loại chủ thể dùng chung một cơ chế token:

- patient / doctor — có bản ghi trong bảng `users`; token mang `uid` là khoá
  chính thật, không phải username, để đổi tên đăng nhập sau này không làm hỏng
  liên kết lịch sử.
- guest — KHÔNG có bản ghi trong DB. Token mang `sid` (session id sinh ngẫu
  nhiên) và `uid = None`. Hết hạn token là hết phiên: không có gì để truy lại,
  đúng yêu cầu "kết thúc session thì dữ liệu mất".
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from src.config import get_settings

settings = get_settings()

ROLE_GUEST = "guest"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(*, username: str, role: str, user_id: int | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict = {"sub": username, "role": role, "exp": expire}
    if user_id is not None:
        payload["uid"] = user_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_guest_token() -> tuple[str, str, int]:
    """Cấp token cho một phiên khách ẩn danh.

    Trả về (token, session_id, expires_in_seconds). Không ghi gì xuống DB —
    session_id chỉ nằm trong token, dùng để phân biệt phiên trong log và để
    gắn review token của luồng OCR.
    """
    session_id = secrets.token_hex(8)
    expire_minutes = settings.guest_session_expire_minutes
    expire = datetime.now(UTC) + timedelta(minutes=expire_minutes)
    payload = {
        "sub": f"guest-{session_id}",
        "role": ROLE_GUEST,
        "sid": session_id,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, session_id, expire_minutes * 60


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
