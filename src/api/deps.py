"""FastAPI dependencies dùng chung giữa các route (auth guard)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.services.auth import decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, username: str, role: str) -> None:
        self.username = username
        self.role = role


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chưa đăng nhập")

    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload or "role" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ")

    return CurrentUser(username=payload["sub"], role=payload["role"])
