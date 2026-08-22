"""FastAPI dependencies dùng chung giữa các route (auth guard + phân quyền)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.models.db import ROLE_ADMIN, ROLE_DOCTOR, ROLE_PATIENT
from src.services.auth import ROLE_GUEST, decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)

# Lay tu hang so thay vi go tay chuoi: doi ten mot role ma quen sua o day thi
# moi token cua role do bi 401 hang loat, va trieu chung ("dang nhap duoc nhung
# goi API nao cung 401") khong he chi ve file nay.
_VALID_ROLES = {ROLE_PATIENT, ROLE_DOCTOR, ROLE_ADMIN, ROLE_GUEST}


class CurrentUser:
    """Chủ thể đang gọi API, dựng lại từ JWT — không truy vấn DB.

    `user_id` là None với khách: khách không có bản ghi trong bảng `users`, nên
    mọi thứ cần khoá ngoại (lưu lịch sử) phải kiểm tra `is_guest` trước.
    """

    def __init__(
        self,
        username: str,
        role: str,
        *,
        user_id: int | None = None,
        session_id: str | None = None,
    ) -> None:
        self.username = username
        self.role = role
        self.user_id = user_id
        self.session_id = session_id

    @property
    def is_guest(self) -> bool:
        return self.role == ROLE_GUEST


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa đăng nhập")

    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload or "role" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ")

    role = payload["role"]
    if role not in _VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ")

    # Token của patient/doctor bắt buộc mang uid: token cũ ký trước khi có cột
    # này không đủ thông tin để gắn lịch sử, buộc đăng nhập lại thay vì lưu
    # nhầm phiếu sang tài khoản khác.
    user_id = payload.get("uid")
    if role != ROLE_GUEST and not isinstance(user_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã cũ, vui lòng đăng nhập lại",
        )

    # Gan role len request.state de middleware trace doc duoc ma khong phai giai
    # ma JWT lan hai. Chi luu ROLE, khong luu username hay uid: bang trace co
    # tinh khong gan voi ca nhan nao — du de biet "man bac si dang cham", khong
    # du de lan ra ai da kham gi.
    request.state.user_role = role

    return CurrentUser(
        username=payload["sub"],
        role=role,
        user_id=user_id if role != ROLE_GUEST else None,
        session_id=payload.get("sid"),
    )


def require_roles(*roles: str) -> Callable:
    """Dependency factory: chỉ cho các role được liệt kê đi tiếp.

    Dùng cho nhóm endpoint lịch sử. `get_current_user` cố tình KHÔNG tự phân
    quyền — nó chỉ xác thực; quyền hạn là quyết định của từng endpoint.
    """

    allowed = set(roles)

    async def _dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed:
            detail = (
                "Chế độ khách không lưu và không xem được lịch sử. Vui lòng đăng ký tài khoản."
                if current_user.is_guest
                else "Tài khoản của bạn không có quyền truy cập chức năng này."
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        return current_user

    return _dependency
