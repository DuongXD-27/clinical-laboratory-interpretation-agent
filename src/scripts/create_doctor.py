"""Cấp tài khoản bác sĩ (chỉ admin chạy được, không có endpoint public).

Theo ma trận phân quyền đã chốt: bệnh nhân tự đăng ký, bác sĩ "được cấp sẵn bởi
admin". Nếu để `/auth/register` nhận `role` từ client thì bất kỳ ai cũng tự khai
mình là bác sĩ và đọc được lịch sử của mọi bệnh nhân — nên đường tạo tài khoản
bác sĩ nằm ở đây, chạy trên máy/container có quyền truy cập DB.

    python -m src.scripts.create_doctor --username bs.nam
    python -m src.scripts.create_doctor --username bs.nam --password '...'
    python -m src.scripts.create_doctor --username bs.nam --reset-password

Không truyền --password thì script sinh mật khẩu ngẫu nhiên và in ra một lần.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from src.models.db import ROLE_DOCTOR, SessionLocal, User, init_db
from src.services.auth import hash_password


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tạo hoặc đặt lại tài khoản bác sĩ")
    parser.add_argument("--username", required=True, help="Tên đăng nhập của bác sĩ")
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
    pw = getpass.getpass("Mật khẩu cho tài khoản bác sĩ: ")
    if len(pw) < 6:
        raise SystemExit("Mật khẩu phải có ít nhất 6 ký tự.")
    if pw != getpass.getpass("Nhập lại mật khẩu: "):
        raise SystemExit("Hai lần nhập mật khẩu không khớp.")
    return pw


def main(argv: list[str] | None = None) -> int:
    # Console Windows mac dinh cp1252 khong in duoc tieng Viet co dau; thieu dong
    # nay thi script tao xong tai khoan roi chet o buoc print. Xem create_admin.py.
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
            existing.role = ROLE_DOCTOR
            action = "Đã đặt lại mật khẩu"
        else:
            db.add(
                User(
                    username=args.username,
                    password_hash=hash_password(password),
                    role=ROLE_DOCTOR,
                )
            )
            action = "Đã tạo tài khoản bác sĩ"

        db.commit()

    print(f"{action}: {args.username} (role={ROLE_DOCTOR})")
    if args.random_password:
        # In đúng một lần: mật khẩu chỉ tồn tại ở dạng hash trong DB, mất là
        # phải chạy lại với --reset-password.
        print(f"Mật khẩu (chỉ hiển thị lần này): {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
