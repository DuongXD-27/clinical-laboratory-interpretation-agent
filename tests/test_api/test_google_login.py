"""Đăng nhập bằng Google — ranh giới tin cậy giữa token của client và tài khoản.

Token do trình duyệt gửi lên, nên trước khi chữ ký được kiểm thì mọi thứ trong
đó chỉ là dữ liệu người dùng tự khai. Bộ test này dựng đúng các cách khai gian
và kiểm rằng không cách nào lọt:

- token giả / hết hạn / sai audience
- `email_verified: false` — ghép tài khoản theo email chưa xác minh là đường
  chiếm tài khoản người khác
- tự khai `role: doctor`

Không gọi mạng: `verify_oauth2_token` được thay bằng stub, vì cái đang kiểm là
**logic quanh** việc xác minh, không phải bản thân thư viện của Google.
"""

from __future__ import annotations

import pytest

from src.models.db import ROLE_DOCTOR, User
from src.services import google_identity
from src.services.auth import hash_password

CLIENT_ID = "test-client-id.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def google_configured(monkeypatch):
    from src.config import get_settings

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", CLIENT_ID)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def fake_claims(**overrides):
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1234567890",
        "email": "Nguoi.Dung@Gmail.COM",
        "email_verified": True,
        "name": "Nguoi Dung",
    }
    claims.update(overrides)
    return claims


@pytest.fixture
def google_returns(monkeypatch):
    """Thay chỗ xác minh của Google bằng stub trả về claims cho trước."""

    def _install(claims=None, *, raises: Exception | None = None):
        def _verify(credential, request, client_id):  # noqa: ARG001
            if raises is not None:
                raise raises
            return claims

        monkeypatch.setattr(
            "google.oauth2.id_token.verify_oauth2_token",
            _verify,
        )

    return _install


async def _google_login(client, credential: str = "token-gia-lap"):
    return await client.post("/api/v1/auth/google", json={"credential": credential})


# --- Cấu hình ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_reports_client_id_when_configured(client):
    response = await client.get("/api/v1/auth/google/status")

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "client_id": CLIENT_ID}


@pytest.mark.asyncio
async def test_status_is_public(client):
    """Không cần token: frontend phải biết có nên vẽ nút hay không TRƯỚC khi
    có ai đăng nhập."""

    assert (await client.get("/api/v1/auth/google/status")).status_code == 200


@pytest.mark.asyncio
async def test_disabled_when_client_id_is_missing(client, monkeypatch):
    from src.config import get_settings

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "")
    get_settings.cache_clear()

    status_response = await client.get("/api/v1/auth/google/status")
    assert status_response.json() == {"enabled": False, "client_id": None}

    # Và endpoint đăng nhập cũng phải từ chối, không phải chỉ ẩn nút ở UI.
    assert (await _google_login(client)).status_code == 401


# --- Token không hợp lệ ------------------------------------------------------


@pytest.mark.asyncio
async def test_forged_token_is_rejected(client, google_returns):
    google_returns(raises=ValueError("chu ky sai"))

    response = await _google_login(client)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_from_another_issuer_is_rejected(client, google_returns):
    """`iss` phải là Google. Đây là ranh giới tin cậy nên kiểm tường minh."""

    google_returns(fake_claims(iss="https://ke-tan-cong.example.com"))

    assert (await _google_login(client)).status_code == 401


@pytest.mark.asyncio
async def test_unverified_email_is_rejected(client, google_returns):
    """Điều kiện quan trọng nhất của cả file này.

    Ghép tài khoản theo một email CHƯA xác minh nghĩa là chỉ cần khai email của
    người khác là chiếm được tài khoản của họ. Google trả `email_verified:
    false` được ở vài cấu hình Workspace, nên đây không phải trường hợp giả
    định.
    """

    google_returns(fake_claims(email_verified=False))

    response = await _google_login(client)

    assert response.status_code == 401
    assert "xác minh" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_email_verified_as_the_string_false_is_still_rejected(client, google_returns):
    """Google từng trả chuỗi thay vì bool, và `if "false"` trong Python là True."""

    google_returns(fake_claims(email_verified="false"))

    assert (await _google_login(client)).status_code == 401


@pytest.mark.asyncio
async def test_token_without_email_is_rejected(client, google_returns):
    google_returns(fake_claims(email=None))

    assert (await _google_login(client)).status_code == 401


# --- Tạo và ghép tài khoản ---------------------------------------------------


@pytest.mark.asyncio
async def test_first_sign_in_creates_a_patient_account(client, google_returns):
    google_returns(fake_claims())

    response = await _google_login(client)

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "patient"


@pytest.mark.asyncio
async def test_google_can_never_create_a_privileged_account(client, google_returns):
    """Client tự khai `role` thì bị bỏ qua hoàn toàn.

    Cùng bảo đảm với `/auth/register`. Nếu Google tạo được tài khoản bác sĩ thì
    bất kỳ ai có Gmail cũng đọc được bệnh án người khác.
    """

    google_returns(fake_claims(role="doctor", is_admin=True))

    response = await client.post(
        "/api/v1/auth/google",
        json={"credential": "token-gia-lap", "role": "doctor"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "patient"


@pytest.mark.asyncio
async def test_username_is_derived_from_the_email_local_part(client, google_returns):
    """Không dùng cả email làm tên đăng nhập.

    Tên đăng nhập hiện khắp giao diện; để lộ email bệnh nhân cho bác sĩ xem lịch
    sử là không cần thiết.
    """

    google_returns(fake_claims(email="nguoi.dung@gmail.com"))

    response = await _google_login(client)

    assert response.json()["username"] == "nguoi.dung"


@pytest.mark.asyncio
async def test_second_sign_in_reuses_the_same_account(client, google_returns):
    google_returns(fake_claims())

    first = await _google_login(client)
    second = await _google_login(client)

    assert first.json()["username"] == second.json()["username"]


@pytest.mark.asyncio
async def test_sign_in_links_to_an_existing_account_with_the_same_email(client, test_db, google_returns):
    """Ghép vào tài khoản sẵn có thay vì tạo bản sao.

    An toàn vì `email_verified` đã bắt buộc ở trên. Không ghép thì một người
    đăng ký bằng mật khẩu rồi bấm Google sẽ có hai tài khoản, và lịch sử xét
    nghiệm nằm ở tài khoản kia.
    """

    with test_db.session() as session:
        session.add(
            User(
                username="dacoroi",
                password_hash=hash_password("matkhau123"),
                role="patient",
                email="nguoi.dung@gmail.com",
            )
        )
        session.commit()

    google_returns(fake_claims(email="Nguoi.Dung@Gmail.com"))

    response = await _google_login(client)

    assert response.status_code == 200
    assert response.json()["username"] == "dacoroi"


@pytest.mark.asyncio
async def test_linking_preserves_an_existing_doctor_role(client, test_db, google_returns):
    """Ghép chỉ XÁC THỰC, không cấp thêm quyền và cũng không tước quyền.

    Bác sĩ đã có email thì đăng nhập bằng Google vẫn vào đúng tài khoản bác sĩ
    của mình. Hạ role xuống patient ở đây là âm thầm khoá bác sĩ khỏi việc của
    họ.
    """

    with test_db.session() as session:
        session.add(
            User(
                username="bs.email",
                password_hash=hash_password("matkhau123"),
                role=ROLE_DOCTOR,
                email="bacsi@benhvien.vn",
            )
        )
        session.commit()

    google_returns(fake_claims(email="bacsi@benhvien.vn"))

    response = await _google_login(client)

    assert response.json()["role"] == "doctor"
    assert response.json()["username"] == "bs.email"


@pytest.mark.asyncio
async def test_username_collision_gets_a_suffix(client, test_db, google_returns):
    """Tên rút từ email có thể trùng người đã đăng ký bằng mật khẩu."""

    with test_db.session() as session:
        session.add(
            User(
                username="trungten",
                password_hash=hash_password("matkhau123"),
                role="patient",
                email="ai.do.khac@gmail.com",
            )
        )
        session.commit()

    google_returns(fake_claims(email="trungten@gmail.com"))

    response = await _google_login(client)

    assert response.status_code == 200
    assert response.json()["username"] != "trungten"
    assert response.json()["username"].startswith("trungten")


# --- Đơn vị: lớp xác minh ----------------------------------------------------


def test_verify_returns_a_normalised_email(google_returns):
    google_returns(fake_claims(email="  Nguoi.Dung@GMAIL.com "))

    identity = google_identity.verify_id_token("token-gia-lap")

    assert identity.email == "nguoi.dung@gmail.com"
    assert identity.subject == "1234567890"
    assert identity.full_name == "Nguoi Dung"


def test_verify_refuses_when_not_configured(monkeypatch):
    from src.config import get_settings

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "")
    get_settings.cache_clear()

    with pytest.raises(google_identity.GoogleIdentityError):
        google_identity.verify_id_token("token-gia-lap")
