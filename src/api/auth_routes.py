import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, get_current_user
from src.config import get_settings
from src.models.db import ROLE_PATIENT, User, get_db
from src.models.schemas import (
    CurrentUserResponse,
    GoogleLoginRequest,
    GoogleStatusResponse,
    GuestSessionResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from src.services import google_identity
from src.services.auth import (
    create_access_token,
    create_guest_token,
    hash_password,
    verify_password_or_dummy,
)
from src.services.email_identity import InvalidEmailError, normalise_email

router = APIRouter(prefix="/auth", tags=["auth"])


def normalise_email_quietly(value: str) -> str | None:
    """Chuẩn hoá email cho lượt TRA CỨU, nuốt lỗi định dạng.

    Ở đường đăng nhập, chuỗi người dùng gõ có thể là tên đăng nhập chứ không
    phải email. Ném lỗi định dạng ở đây là biến "gõ nhầm tên" thành 422 thay vì
    401 — và cũng vô tình để lộ rằng hệ thống phân biệt hai trường hợp đó.
    """

    try:
        return normalise_email(value)
    except InvalidEmailError:
        return None


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """Đăng ký tài khoản bệnh nhân mới (role luôn là `patient`).

    Email không bắt buộc. Ai điền thì đăng nhập được bằng cả tên lẫn email; ai
    bỏ trống thì mọi thứ như cũ.
    """

    try:
        email = normalise_email(request.email)
    except InvalidEmailError as exc:
        # 422 gõ thẳng: hằng số HTTP_422_UNPROCESSABLE_ENTITY của Starlette đã
        # deprecated, mà tên thay thế thì chưa có ở phiên bản đang cài.
        raise HTTPException(status_code=422, detail=str(exc)) from None

    user = User(
        username=request.username,
        password_hash=hash_password(request.password),
        role=ROLE_PATIENT,
        email=email,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Ràng buộc UNIQUE là nơi quyết định, không phải câu SELECT kiểm tra
        # trước — hai request đăng ký cùng tên (hoặc cùng email) chạy song song
        # vẫn chỉ có đúng một bản ghi được tạo.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Email này đã được dùng cho một tài khoản khác."
                if email is not None
                else "Tên đăng nhập đã tồn tại, vui lòng chọn tên khác."
            ),
        ) from None

    db.refresh(user)
    return RegisterResponse(id=user.id, username=user.username, role=ROLE_PATIENT, email=user.email)


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    # Tra CẢ HAI cột trong một câu, không rẽ nhánh theo việc chuỗi có `@` hay
    # không: một tên đăng nhập chứa `@` vẫn phải vào được bình thường.
    #
    # Email so khớp ở dạng đã hạ chữ thường, đúng như lúc ghi. Thiếu bước này
    # thì đăng ký `Duy@Gmail.com` rồi gõ `duy@gmail.com` sẽ không vào được, mà
    # thông báo lại là "sai mật khẩu" — gần như không ai lần ra.
    identifier = request.username.strip()
    email_form = normalise_email_quietly(identifier)

    user = (
        db.query(User)
        .filter(
            or_(User.username == identifier, User.email == email_form) if email_form else User.username == identifier
        )
        .first()
    )

    # Luon tra gia bcrypt nhu nhau, ke ca khi khong tim thay tai khoan — xem
    # `verify_password_or_dummy`. Thieu buoc nay thi thoi gian phan hoi to cao
    # email nao da co tai khoan, du thong bao loi giong het nhau.
    if not verify_password_or_dummy(request.password, user.password_hash if user else None):
        # Sai tên, sai email, sai mật khẩu — cùng một status và cùng một câu.
        # Tách ra là biến endpoint này thành công cụ dò xem email nào đã có tài
        # khoản, và với dữ liệu y tế thì "người này có khám ở đây" tự nó đã là
        # thông tin không nên để lộ.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai tên đăng nhập hoặc mật khẩu",
        )

    # Role lấy từ bản ghi DB, không phải từ dữ liệu client gửi lên — frontend
    # chỉ đọc lại role trong response để chọn giao diện.
    token = create_access_token(username=user.username, role=user.role, user_id=user.id)
    return LoginResponse(access_token=token, role=user.role, username=user.username)


@router.get("/google/status", response_model=GoogleStatusResponse)
async def google_status() -> GoogleStatusResponse:
    """Client id cho nut Dang nhap bang Google, va co bat hay khong.

    Khong xac thuc: frontend phai biet co nen ve cai nut do khong TRUOC khi ai
    dang nhap. Client id la thong tin cong khai — no nam san trong ma nguon moi
    trang dung Google Sign-In.

    Co endpoint nay thi khong phai nhung client id vao bundle luc build. Bien
    NEXT_PUBLIC_* bi Next.js dan cung vao JS, doi la phai build lai; doc tu API
    thi doi bien moi truong roi khoi dong lai backend la xong.
    """

    settings = get_settings()
    return GoogleStatusResponse(
        enabled=google_identity.is_configured(),
        client_id=settings.google_oauth_client_id or None,
    )


@router.post("/google", response_model=LoginResponse)
async def login_with_google(
    request: GoogleLoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Doi ID token cua Google lay phien dang nhap cua he thong nay.

    Ba quy tac dinh hinh ham nay:

    1. **Xac minh o server.** Token do trinh duyet gui len, nen truoc khi chu ky
       duoc kiem thi moi thu trong do chi la du lieu nguoi dung tu khai.

    2. **Chi tao ra role patient.** Giong het `/auth/register`. Neu Google tao
       duoc tai khoan bac si thi bat ky ai co Gmail cung doc duoc benh an nguoi
       khac — ma tai khoan bac si von duoc cap bang script co chu y.

    3. **Ghep theo email da xac minh.** Email trung mot tai khoan san co thi
       dang nhap vao chinh tai khoan do. An toan vi `verify_id_token` da bat
       buoc `email_verified`; thieu dieu kien do thi chi can khai email nguoi
       khac la chiem duoc tai khoan cua ho.
    """

    try:
        identity = google_identity.verify_id_token(request.credential)
    except google_identity.GoogleIdentityError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from None

    user = db.query(User).filter(User.email == identity.email).first()

    if user is None:
        user = User(
            username=_unique_username_from_email(db, identity.email),
            # Tai khoan Google khong dang nhap bang mat khau. Van phai co hash
            # vi cot NOT NULL — dat mot chuoi ngau nhien khong ai biet, thay vi
            # de rong hay dung mot gia tri co dinh mo duong dang nhap bang mat
            # khau cho moi tai khoan Google.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role=ROLE_PATIENT,
            email=identity.email,
            full_name=identity.full_name,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Hai lan bam nut cung luc: cai thu hai thua, doc lai ban ghi cai
            # thu nhat vua tao thay vi bao loi cho nguoi dung.
            db.rollback()
            user = db.query(User).filter(User.email == identity.email).first()
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Khong tao duoc tai khoan, vui long thu lai.",
                ) from None
        else:
            db.refresh(user)

    token = create_access_token(username=user.username, role=user.role, user_id=user.id)
    return LoginResponse(access_token=token, role=user.role, username=user.username)


def _unique_username_from_email(db: Session, email: str) -> str:
    """Dung ten dang nhap tu phan truoc dau @, them hau to neu da co nguoi dung.

    Khong dung nguyen ca email lam username: no hien len khap giao dien, va lo
    email cua benh nhan cho bac si xem lich su la khong can thiet.

    SELECT o day khong phai co che chong trung — UNIQUE tren cot moi la. No chi
    de chon mot ten de nhin; hai request song song cung ten thi mot cai dinh
    IntegrityError va duoc xu ly o tren.
    """

    base = "".join(ch for ch in email.split("@", 1)[0] if ch.isalnum() or ch in "._-")[:24]
    base = base or "nguoidung"

    if db.query(User).filter(User.username == base).first() is None:
        return base

    for _ in range(5):
        candidate = f"{base}{secrets.randbelow(9000) + 1000}"
        if db.query(User).filter(User.username == candidate).first() is None:
            return candidate

    return f"{base}{secrets.token_hex(4)}"


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
