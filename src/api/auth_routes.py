from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, get_current_user
from src.models.db import ROLE_PATIENT, User, get_db
from src.models.schemas import (
    CurrentUserResponse,
    GuestSessionResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from src.services.auth import (
    create_access_token,
    create_guest_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """Đăng ký tài khoản bệnh nhân mới (role luôn là `patient`)."""
    user = User(
        username=request.username,
        password_hash=hash_password(request.password),
        role=ROLE_PATIENT,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Ràng buộc UNIQUE trên username là nơi quyết định, không phải câu
        # SELECT kiểm tra trước — hai request đăng ký cùng tên chạy song song
        # vẫn chỉ có đúng một bản ghi được tạo.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tên đăng nhập đã tồn tại, vui lòng chọn tên khác.",
        ) from None

    db.refresh(user)
    return RegisterResponse(id=user.id, username=user.username, role=ROLE_PATIENT)


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.username == request.username).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sai tên đăng nhập hoặc mật khẩu")

    # Role lấy từ bản ghi DB, không phải từ dữ liệu client gửi lên — frontend
    # chỉ đọc lại role trong response để chọn giao diện.
    token = create_access_token(username=user.username, role=user.role, user_id=user.id)
    return LoginResponse(access_token=token, role=user.role, username=user.username)


@router.post("/guest", response_model=GuestSessionResponse)
async def guest_session() -> GuestSessionResponse:
    """Mở phiên khách: dùng thử được, không tạo tài khoản, không lưu lịch sử."""
    token, session_id, expires_in = create_guest_token()
    return GuestSessionResponse(
        access_token=token,
        username=f"guest-{session_id}",
        session_id=session_id,
        expires_in_seconds=expires_in,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        username=current_user.username,
        role=current_user.role,
        is_guest=current_user.is_guest,
    )
