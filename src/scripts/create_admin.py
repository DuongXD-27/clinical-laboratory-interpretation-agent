"""Cấp tài khoản admin — không có endpoint public, giống hệt đường của bác sĩ.

Admin xem được màn hình trace vận hành: độ trễ, số lần gọi LLM, mã lỗi của mọi
request. Nếu để `/auth/register` nhận `role` từ client thì bất kỳ ai cũng tự
khai mình là admin, nên đường tạo tài khoản nằm ở đây, chạy trên máy hoặc
container có quyền truy cập DB.

    python -m src.scripts.create_admin --username admin.duy --random-password
    python -m src.scripts.create_admin --username admin.duy --reset-password

Cố ý KHÔNG seed sẵn tài khoản admin nào trong `DEMO_USERS`: mật khẩu demo là
công khai với cả cohort, một admin seed sẵn là cửa hậu ai cũng đăng nhập được.

Quyền của admin dừng ở dữ liệu vận hành. Không endpoint nào cho admin đọc bệnh
án — `/history` vẫn chỉ nhận `patient` và `doctor`. Người lo hạ tầng không cần,
và không nên, đọc được kết quả xét nghiệm của bệnh nhân.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from src.models.db import ROLE_ADMIN, SessionLocal, User, init_db
from src.services.auth import hash_password


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tạo hoặc đặt lại tài khoản admin")
    parser.add_argument("--username", required=True, help="Tên đăng nhập của admin")
    parser.add_argument(
        "--password",
        default=None,
        help="Mật khẩu; bỏ trống để nhập ẩn qua bàn phím hoặc sinh ngẫu nhiên (--random-password)",
    )
    parser.add_argument(
        "--random-password",
        action="store_true",
        help="Sinh mật khẩu ngẫu nhiên và in ra một lần duy nhất",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Nếu tài khoản đã tồn tại thì đặt lại mật khẩu thay vì báo lỗi",
    )
    return parser.parse_args(argv)


def _resolve_password(args: argparse.Namespace) -> str:
    if args.password:
        return args.password
    if args.random_password:
        return secrets.token_urlsafe(12)
    pw = getpass.getpass("Mật khẩu cho tài khoản admin: ")
    if len(pw) < 6:
        raise SystemExit("Mật khẩu phải có ít nhất 6 ký tự.")
    if pw != getpass.getpass("Nhập lại mật khẩu: "):
        raise SystemExit("Hai lần nhập mật khẩu không khớp.")
    return pw


def main(argv: list[str] | None = None) -> int:
    # Console Windows mac dinh la cp1252, khong in duoc tieng Viet co dau. Thieu
    # dong nay thi script TAO XONG tai khoan roi moi chet o buoc print — nguoi
    # chay thay traceback va tuong that bai, chay lai lan nua thi dinh "da ton
    # tai". Ca nhom deu dung Windows nen day khong phai truong hop hiem.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = _parse_args(argv)
    init_db()

    with SessionLocal() as db:
        existing = db.query(User).filter(User.username == args.username).first()

        if existing is not None and not args.reset_password:
            print(
                f"Tài khoản '{args.username}' đã tồn tại (role={existing.role}). "
                "Dùng --reset-password nếu muốn đặt lại mật khẩu.",
                file=sys.stderr,
            )
            return 1

        password = _resolve_password(args)

        if existing is not None:
            existing.password_hash = hash_password(password)
            existing.role = ROLE_ADMIN
            action = "Đã đặt lại mật khẩu"
        else:
            db.add(
                User(
                    username=args.username,
                    password_hash=hash_password(password),
                    role=ROLE_ADMIN,
                )
            )
            action = "Đã tạo tài khoản admin"

        db.commit()

    print(f"{action}: {args.username} (role={ROLE_ADMIN})")
    if args.random_password:
        # In đúng một lần: mật khẩu chỉ tồn tại ở dạng hash trong DB, mất là
        # phải chạy lại với --reset-password.
        print(f"Mật khẩu (chỉ hiển thị lần này): {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
