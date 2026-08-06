"""DB tối thiểu cho auth: 1 bảng users (id, username, password_hash, role).

SQLite, tạo bảng qua create_all() (không dùng Alembic — bảng duy nhất
này không cần versioned migration ở quy mô V2). Seed vài tài khoản demo
lúc khởi động nếu bảng đang trống, để hoạt động ổn định kể cả khi disk
trên Render bị reset (free tier không có persistent disk).
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import get_settings
from src.services.auth import hash_password

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "patient" | "doctor"


DEMO_USERS = [
    {"username": "benhnhan", "password": "benhnhan123", "role": "patient"},
    {"username": "bacsi", "password": "bacsi123", "role": "doctor"},
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(User).count() == 0:
            for u in DEMO_USERS:
                db.add(
                    User(
                        username=u["username"],
                        password_hash=hash_password(u["password"]),
                        role=u["role"],
                    )
                )
            try:
                db.commit()
            except IntegrityError:
                # count()==0 không atomic giữa các process — nếu chạy nhiều
                # worker, process khác có thể đã seed xong giữa lúc mình
                # check và commit. Bỏ qua an toàn, không phải lỗi thật.
                db.rollback()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Gọi ngay lúc import: đảm bảo bảng + seed tồn tại kể cả khi ASGI lifespan
# không được kích hoạt (vd. httpx.ASGITransport trong test không luôn chạy
# lifespan). init_db() idempotent (kiểm tra count()==0), gọi lại từ
# main.py's lifespan vẫn an toàn.
init_db()
