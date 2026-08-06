from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, get_current_user
from src.models.db import User, get_db
from src.models.schemas import CurrentUserResponse, LoginRequest, LoginResponse
from src.services.auth import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.username == request.username).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sai tên đăng nhập hoặc mật khẩu")

    token = create_access_token(username=user.username, role=user.role)
    return LoginResponse(access_token=token, role=user.role, username=user.username)


@router.get("/me", response_model=CurrentUserResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(username=current_user.username, role=current_user.role)
