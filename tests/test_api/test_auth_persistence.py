"""Nghiệm thu TechDebt V3 — Duy, nhiệm vụ 1: thay auth mock bằng persistence thật.

Mã test bám đúng bảng nghiệm thu (TC-01..TC-05) để đối chiếu 1-1 khi bàn giao.
"""

import pytest

from src.models.db import User


async def register(client, username: str, password: str = "matkhau123", **extra):
    return await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password, **extra},
    )


async def login(client, username: str, password: str):
    return await client.post("/api/v1/auth/login", json={"username": username, "password": password})


def count_users(test_db, username: str) -> int:
    with test_db.session() as db:
        return db.query(User).filter(User.username == username).count()


# --- TC-01: Register ---------------------------------------------------------


@pytest.mark.asyncio
async def test_tc01_register_creates_exactly_one_user_with_correct_role(client, test_db):
    response = await register(client, "benhnhan_moi")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["username"] == "benhnhan_moi"
    assert body["role"] == "patient"

    with test_db.session() as db:
        users = db.query(User).filter(User.username == "benhnhan_moi").all()
    assert len(users) == 1
    assert users[0].role == "patient"
    assert users[0].password_hash != "matkhau123"  # không lưu mật khẩu thô


@pytest.mark.asyncio
async def test_tc01_registered_user_can_login_immediately(client):
    await register(client, "benhnhan_moi")

    response = await login(client, "benhnhan_moi", "matkhau123")

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "patient"


# --- TC-02: Persistence (điểm chứng minh đã thoát khỏi mock) ------------------


@pytest.mark.asyncio
async def test_tc02_user_survives_backend_restart(client, test_db):
    await register(client, "benhnhan_ben_vung")

    # Đóng sạch connection rồi mở lại từ file — tương đương restart backend.
    test_db.restart()

    response = await login(client, "benhnhan_ben_vung", "matkhau123")
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "benhnhan_ben_vung"


# --- TC-03: Duplicate --------------------------------------------------------


@pytest.mark.asyncio
async def test_tc03_duplicate_username_rejected_without_creating_duplicate_row(client, test_db):
    first = await register(client, "trung_ten")
    assert first.status_code == 201

    second = await register(client, "trung_ten", password="matkhaukhac")

    assert second.status_code == 409, second.text
    assert count_users(test_db, "trung_ten") == 1


@pytest.mark.asyncio
async def test_tc03_duplicate_does_not_overwrite_existing_password(client):
    await register(client, "trung_ten", password="matkhau_goc")
    await register(client, "trung_ten", password="matkhau_moi")

    assert (await login(client, "trung_ten", "matkhau_goc")).status_code == 200
    assert (await login(client, "trung_ten", "matkhau_moi")).status_code == 401


@pytest.mark.asyncio
async def test_tc03_cannot_hijack_seeded_demo_account(client, test_db):
    response = await register(client, "benhnhan", password="matkhau_cua_ke_khac")

    assert response.status_code == 409
    assert (await login(client, "benhnhan", "benhnhan123")).status_code == 200
    assert count_users(test_db, "benhnhan") == 1


# --- TC-04: Wrong password ---------------------------------------------------


@pytest.mark.asyncio
async def test_tc04_wrong_password_returns_no_token(client):
    await register(client, "benhnhan_mk")

    response = await login(client, "benhnhan_mk", "sai-mat-khau")

    assert response.status_code == 401
    assert "access_token" not in response.json()


@pytest.mark.asyncio
async def test_tc04_unknown_username_returns_same_error(client):
    """Sai tên và sai mật khẩu trả về cùng một thông điệp.

    Nếu phân biệt, kẻ tấn công dò được username nào có thật trong hệ thống.
    """
    unknown = await login(client, "khong-ton-tai", "matkhau123")
    await register(client, "co_that")
    wrong_password = await login(client, "co_that", "sai-mat-khau")

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json()["detail"] == wrong_password.json()["detail"]


# --- TC-05: Role -------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc05_patient_and_doctor_roles_come_from_database(client):
    patient = await login(client, "benhnhan", "benhnhan123")
    doctor = await login(client, "bacsi", "bacsi123")

    assert patient.json()["role"] == "patient"
    assert doctor.json()["role"] == "doctor"

    # /auth/me đọc role từ token do server ký, không nhận role từ client.
    for response, expected in ((patient, "patient"), (doctor, "doctor")):
        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["role"] == expected
        assert me.json()["is_guest"] is False


@pytest.mark.asyncio
async def test_tc05_register_cannot_self_assign_doctor_role(client, test_db):
    """Không có đường public nào tự nâng quyền lên doctor (ma trận: admin cấp)."""
    response = await register(client, "ke_gia_mao", role="doctor")

    assert response.status_code == 201
    assert response.json()["role"] == "patient"

    with test_db.session() as db:
        assert db.query(User).filter(User.username == "ke_gia_mao").one().role == "patient"


@pytest.mark.asyncio
async def test_tc05_tampered_token_is_rejected(client):
    """Role nằm trong JWT có chữ ký; sửa tay thì token hỏng."""
    token = (await login(client, "benhnhan", "benhnhan123")).json()["access_token"]
    header, payload, signature = token.split(".")
    forged = f"{header}.{payload}x.{signature}"

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_doctor_script_provisions_doctor_account(client, test_db, monkeypatch):
    """Đường cấp tài khoản bác sĩ: script admin, không phải endpoint."""
    from src.scripts import create_doctor

    monkeypatch.setattr(create_doctor, "SessionLocal", test_db.session_factory)
    monkeypatch.setattr(create_doctor, "init_db", lambda: None)

    exit_code = create_doctor.main(["--username", "bs.nam", "--password", "matkhau123"])
    assert exit_code == 0

    response = await login(client, "bs.nam", "matkhau123")
    assert response.status_code == 200
    assert response.json()["role"] == "doctor"


@pytest.mark.asyncio
async def test_create_doctor_script_refuses_existing_username_without_reset(test_db, monkeypatch):
    from src.scripts import create_doctor

    monkeypatch.setattr(create_doctor, "SessionLocal", test_db.session_factory)
    monkeypatch.setattr(create_doctor, "init_db", lambda: None)

    assert create_doctor.main(["--username", "benhnhan", "--password", "matkhau123"]) == 1

    with test_db.session() as db:
        assert db.query(User).filter(User.username == "benhnhan").one().role == "patient"
