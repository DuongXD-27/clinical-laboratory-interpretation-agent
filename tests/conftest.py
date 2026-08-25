from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.main import app
from src.models.db import DEMO_USERS, Base, User, get_db
from src.orchestrator.session_store import default_session_store
from src.services import langfuse_tracing
from src.services.auth import hash_password


@pytest.fixture(scope="session")
def demo_password_hashes() -> dict[str, str]:
    """Hash bcrypt của tài khoản demo, băm đúng một lần cho cả phiên test.

    bcrypt cố tình chậm (~200ms/lần); băm lại ở mỗi test sẽ cộng thêm hàng chục
    giây vào bộ test mà không kiểm tra thêm điều gì.
    """
    return {u["username"]: hash_password(u["password"]) for u in DEMO_USERS}


class TestDatabase:
    """SQLite trên file tạm, thay cho data/app.db thật trong lúc chạy test.

    Có `restart()` để mô phỏng việc khởi động lại backend: đóng sạch connection
    rồi mở lại từ chính file đó. Nếu dữ liệu chỉ nằm trong bộ nhớ, test dùng
    `restart()` sẽ đỏ — đó là điểm chứng minh đã thoát khỏi mock.
    """

    def __init__(self, path) -> None:
        self.path = path
        self._connect()

    def _connect(self) -> None:
        self.engine = create_engine(f"sqlite:///{self.path}", connect_args={"check_same_thread": False})
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def restart(self) -> None:
        self.engine.dispose()
        self._connect()

    def session(self):
        return self.session_factory()

    def dispose(self) -> None:
        self.engine.dispose()


@pytest.fixture(autouse=True)
def test_db(tmp_path, demo_password_hashes):
    """Mỗi test có DB riêng, đã seed sẵn 2 tài khoản demo.

    Autouse: không test nào được phép ghi vào data/app.db của máy dev, và test
    đăng ký tài khoản không được để lại rác cho test sau.
    """
    db = TestDatabase(tmp_path / "test_app.db")
    Base.metadata.create_all(bind=db.engine)

    with db.session() as session:
        for u in DEMO_USERS:
            session.add(
                User(
                    username=u["username"],
                    password_hash=demo_password_hashes[u["username"]],
                    role=u["role"],
                )
            )
        session.commit()

    def _override_get_db():
        # Đọc session_factory tại thời điểm gọi, không bắt sẵn — sau restart()
        # factory đã bị thay, request tiếp theo phải dùng cái mới.
        session = db.session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.dispose()


@pytest.fixture(autouse=True)
def reset_session_store():
    """Xoá cache context giữa các test.

    `default_session_store` là singleton ở module, còn `test_db` cấp một SQLite
    tạm mới cho từng test — nên id hội thoại lại đếm từ 1. Không xoá thì khoá
    `conv:1` của test trước còn nguyên và test sau kế thừa phần context chỉ nằm
    trong tiến trình của nó. Cùng nguyên tắc với việc mỗi test có DB riêng: bộ
    test không được để lại gì sống lâu hơn chính nó.
    """

    default_session_store.reset()
    yield
    default_session_store.reset()


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock


@pytest.fixture(autouse=True)
def langfuse_off_by_default(monkeypatch):
    """Tắt Langfuse cho mọi test, trừ test tự bật lại.

    Máy dev có key thật trong `.env`. Không có fixture này thì bất kỳ test nào
    dựng `get_llm()` cũng gắn callback thật và bắn span lên project Langfuse
    của nhóm — dữ liệu test lẫn vào dữ liệu production, và bộ test âm thầm gọi
    ra Internet ở mỗi lần chạy.

    Cùng nguyên tắc với fixture `test_db`: bộ test không được chạm vào bất cứ
    thứ gì sống ngoài thư mục tạm của chính nó. Test nào cần Langfuse thì tự
    `monkeypatch.setenv` đè lên — `monkeypatch` của test chạy sau fixture này.
    """

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    # LangSmith cũng vậy: `.env.example` bật sẵn LANGCHAIN_TRACING_V2=true, nên
    # mọi lời gọi LLM trong test sẽ cố gửi prompt sang smith.langchain.com.
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    get_settings.cache_clear()
    langfuse_tracing.reset_for_tests()
    yield
    get_settings.cache_clear()
    langfuse_tracing.reset_for_tests()
