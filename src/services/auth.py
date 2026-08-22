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


# Hash cua mot mat khau ngau nhien khong ai biet, bam mot lan roi dung lai.
# Chi phuc vu `verify_password_or_dummy` — khong tai khoan nao co hash nay.
_DUMMY_HASH: str | None = None


def verify_password_or_dummy(plain: str, hashed: str | None) -> bool:
    """Kiem mat khau, va khi khong co tai khoan thi VAN chay bcmt mot lan.

    Do that truoc khi sua, tren server dang chay:

        email co tai khoan   315 ms
        email khong ton tai   10 ms

    Chenh 31 lan. `if user is None or not verify_password(...)` ngan mach o ve
    trai, nen khong co tai khoan la tra ve gan nhu tuc thi, con co tai khoan thi
    ton ~300ms cho bcrypt. Bat ky ai cung liet ke duoc email nao da co tai khoan
    o day chi bang cach bam gio — va "nguoi nay co kham o day" tu no da la thong
    tin khong nen de lo.

    Thong bao loi giong nhau la chua du: no chi bit kenh ro thu nhat. Ham nay
    bit kenh thu hai bang cach luon tra gia bcrypt nhu nhau.
    """

    global _DUMMY_HASH

    if hashed is not None:
        return verify_password(plain, hashed)

    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(32))

    # Ket qua chac chan False; goi de tieu ton dung luong thoi gian cua mot lan
    # kiem that. KHONG duoc bo qua "cho nhanh".
    verify_password(plain, _DUMMY_HASH)
    return False


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
