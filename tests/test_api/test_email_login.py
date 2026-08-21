"""Đăng nhập bằng email — chuẩn hoá, trùng lặp, và hai kênh rò thông tin.

Nhóm test quan trọng nhất ở đây không phải "đăng nhập được", mà là **không để
endpoint đăng nhập trở thành công cụ dò xem email nào đã có tài khoản**. Với một
dịch vụ đọc kết quả xét nghiệm thì riêng việc "người này có tài khoản ở đây" đã
là thông tin không nên để lộ.

Có hai kênh rò, và bịt một kênh là chưa đủ:

1. Nội dung phản hồi — sai tên, sai email, sai mật khẩu phải cùng status và
   cùng câu chữ.
2. Thời gian phản hồi — đo trên server thật trước khi sửa: 315ms khi email có
   tài khoản, 10ms khi không. Chênh 31 lần, ai cũng đo được.
"""

from __future__ import annotations

import time

import pytest

from src.services.email_identity import InvalidEmailError, normalise_email

PASSWORD = "matkhau123"


async def _register(client, username: str, email: str | None = None):
    payload: dict[str, str] = {"username": username, "password": PASSWORD}
    if email is not None:
        payload["email"] = email
    return await client.post("/api/v1/auth/register", json=payload)


async def _login(client, identifier: str, password: str = PASSWORD):
    return await client.post(
        "/api/v1/auth/login",
        json={"username": identifier, "password": password},
    )


# --- Chuẩn hoá ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Duy@Gmail.COM", "duy@gmail.com"),
        ("  duy@gmail.com  ", "duy@gmail.com"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalise_email(raw, expected):
    assert normalise_email(raw) == expected


def test_blank_email_becomes_null_not_empty_string():
    """Chuỗi rỗng phải thành NULL, không phải `""`.

    UNIQUE index chấp nhận nhiều NULL nhưng chỉ chấp nhận MỘT chuỗi rỗng. Để
    lọt `""` thì người thứ hai bỏ trống email sẽ dính 409 mà không hiểu vì sao.
    """

    assert normalise_email("") is None


@pytest.mark.parametrize(
    "bad",
    ["khongcoa", "thieu@tenmien", "hai@@cham.com", "co khoang@trang.com", "@thieutruoc.com"],
)
def test_invalid_emails_are_rejected(bad):
    with pytest.raises(InvalidEmailError):
        normalise_email(bad)


# --- Đăng ký -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_is_stored_lowercased(client):
    response = await _register(client, "nguoidung1", "  Duy.Test@Gmail.COM ")

    assert response.status_code == 201, response.text
    assert response.json()["email"] == "duy.test@gmail.com"


@pytest.mark.asyncio
async def test_email_is_optional(client):
    """Bắt buộc email là chặn mọi người đang đăng ký bình thường hôm nay, đổi
    lấy một tính năng chưa ai dùng."""

    response = await _register(client, "khongcoemail")

    assert response.status_code == 201, response.text
    assert response.json()["email"] is None


@pytest.mark.asyncio
async def test_two_accounts_may_both_leave_email_blank(client):
    """UNIQUE trên cột nullable phải cho nhiều NULL cùng tồn tại."""

    assert (await _register(client, "trong1")).status_code == 201
    assert (await _register(client, "trong2")).status_code == 201


@pytest.mark.asyncio
async def test_duplicate_email_is_rejected_across_letter_case(client):
    """Trùng email là 409, và khác hoa thường vẫn tính là trùng.

    Không hạ chữ thường thì UNIQUE index vô dụng: `A@x.com` và `a@x.com` lọt
    thành hai tài khoản, và lúc đó đăng nhập bằng email không biết vào cái nào.
    """

    assert (await _register(client, "chu1", "trung@gmail.com")).status_code == 201

    response = await _register(client, "chu2", "TRUNG@Gmail.com")

    assert response.status_code == 409
    assert "email" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_email_at_registration_is_422(client):
    response = await _register(client, "saiemail", "khongphaiemail")

    assert response.status_code == 422


# --- Đăng nhập ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_with_username_still_works(client):
    await _register(client, "cahai", "cahai@gmail.com")

    assert (await _login(client, "cahai")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("typed", ["cahai@gmail.com", "CaHai@Gmail.COM", "  cahai@gmail.com  "])
async def test_login_with_email_in_any_letter_case(client, typed):
    await _register(client, "cahai", "cahai@gmail.com")

    response = await _login(client, typed)

    assert response.status_code == 200, response.text
    # Token luôn mang username thật, không mang email.
    assert response.json()["username"] == "cahai"


@pytest.mark.asyncio
async def test_accounts_without_an_email_can_still_log_in(client):
    """Tài khoản demo, bác sĩ và admin đều không có email.

    Nếu chuyển sang tra cứu chỉ-bằng-email thì toàn bộ số này mất quyền vào."""

    assert (await _login(client, "benhnhan", "benhnhan123")).status_code == 200
    assert (await _login(client, "bacsi", "bacsi123")).status_code == 200


@pytest.mark.asyncio
async def test_a_username_containing_at_sign_still_resolves(client):
    """Không rẽ nhánh theo việc chuỗi có `@` hay không.

    Tra cứu chạy trên CẢ HAI cột trong một câu, nên tên đăng nhập trông giống
    email vẫn vào được — dù nó không phải email của ai cả.
    """

    await _register(client, "la@ten.dangnhap")

    assert (await _login(client, "la@ten.dangnhap")).status_code == 200


# --- Không được rò thông tin -------------------------------------------------


@pytest.mark.asyncio
async def test_failed_logins_are_indistinguishable(client):
    """Kênh rò thứ nhất: nội dung phản hồi.

    Sai mật khẩu của email CÓ thật và email KHÔNG tồn tại phải trả về y hệt
    nhau. Tách ra là biến login thành công cụ dò email.
    """

    await _register(client, "cothat", "cothat@gmail.com")

    responses = [
        await _login(client, "cothat@gmail.com", "SAIMATKHAU"),
        await _login(client, "khongtontai@gmail.com", "SAIMATKHAU"),
        await _login(client, "cothat", "SAIMATKHAU"),
        await _login(client, "khong_ton_tai_gi_ca", "SAIMATKHAU"),
    ]

    assert {r.status_code for r in responses} == {401}
    assert len({r.json()["detail"] for r in responses}) == 1


@pytest.mark.asyncio
async def test_login_timing_does_not_reveal_whether_the_account_exists(client):
    """Kênh rò thứ hai: thời gian phản hồi.

    Đo trên server thật TRƯỚC khi sửa: email có tài khoản 315ms, email không
    tồn tại 10ms — chênh 31 lần vì `user is None or verify_password(...)` ngắn
    mạch, bỏ qua bcrypt khi không có tài khoản. Thông báo giống nhau không cứu
    được: chỉ cần bấm giờ là liệt kê được email nào đã đăng ký.

    Ngưỡng để rộng (hệ số 3) vì bcrypt trên máy CI dùng chung dao động mạnh.
    Cái test này bắt là chênh lệch HẠNG, không phải vài chục phần trăm.
    """

    await _register(client, "cotk", "cotk@gmail.com")

    # Làm nóng: lần đầu còn phải băm hash giả và nạp bcrypt.
    await _login(client, "lamnong@gmail.com", "SAI")

    started = time.perf_counter()
    await _login(client, "cotk@gmail.com", "SAIMATKHAU")
    with_account = time.perf_counter() - started

    started = time.perf_counter()
    await _login(client, "khongtontai@gmail.com", "SAIMATKHAU")
    without_account = time.perf_counter() - started

    assert without_account > with_account / 3, (
        f"có tài khoản {with_account * 1000:.0f}ms, không có {without_account * 1000:.0f}ms — "
        "thời gian phản hồi đang tố cáo email nào đã có tài khoản"
    )
