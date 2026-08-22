from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K-Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM
    llm_provider: Literal["openai", "gemini"] = "openai"
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    openai_max_tokens: int = Field(default=2048, ge=1, le=8192)
    llm_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)

    # Vision LLM Adapter (OCR — ADR-006)
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    gemini_vision_model: str = "gemini-3.5-flash-lite"
    gemini_vision_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    gemini_vision_max_output_tokens: int = Field(default=2048, ge=100, le=4096)
    gemini_vision_thinking_level: Literal["low", "medium", "high"] = "low"
    vision_model: str = "google/gemma-4-26b-a4b-it:free"
    vision_base_url: str = "https://openrouter.ai/api/v1"
    vision_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    vision_max_image_mb: int = Field(default=10, ge=1, le=25)
    vision_timeout_seconds: float = Field(default=30.0, ge=1.0, le=60.0)
    ocr_low_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    ocr_review_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    retrieval_min_score: float = Field(default=0.4, ge=0.0, le=1.0)
    retrieval_top_k: int = Field(default=3, ge=1, le=10)
    metadata_prong_enabled: bool = True
    metadata_min_chunk_length: int = Field(default=30, ge=1)
    max_analyzer_context_chars: int = Field(default=4000, ge=200)
    max_guardrail_context_chars: int = Field(default=3000, ge=200)

    # Chính sách nhận ảnh cho bản demo public (V3). Đổi được bằng biến môi
    # trường, không phải sửa code:
    #   internal_only     — tắt hẳn /ocr/upload (503), dùng khi chưa muốn mở ra ngoài
    #   demo_only         — CHỈ nhận đúng bộ ảnh mẫu trong data/ocr_samples
    #                       (đối chiếu SHA-256), chặn người dùng đưa ảnh thật lên
    #   open_with_consent — nhận ảnh bất kỳ, nhưng bắt buộc tick consent trước
    ocr_upload_mode: Literal["internal_only", "demo_only", "open_with_consent"] = "demo_only"
    ocr_samples_dir: str = "./data/ocr_samples"

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"
    rag_enabled: bool = False
    rag_collection_name: str = "medical_kb_v4"
    rag_corpus_version: str = "medical-kb-v4"
    embedding_provider: Literal["disabled", "openai", "gemini"] = "disabled"
    embedding_model_name: str = "text-embedding-3-small"
    embedding_dimension: int = Field(default=1536, ge=1)
    embedding_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)

    # Agent Rules / Reference
    critical_thresholds_path: str = "./data/reference/critical_thresholds.json"

    # Dang nhap bang Google (Google Identity Services)
    #
    # Chi can CLIENT ID, khong can client secret: luong dung o day la trinh
    # duyet lay ID token roi backend tu kiem chu ky, khong phai authorization
    # code flow. Client ID la thong tin cong khai — no nam san trong ma nguon
    # trang web — nen dat o day khong phai la de lo bi mat.
    #
    # De trong -> tat nut Dang nhap bang Google, phan con lai chay binh thuong.
    google_oauth_client_id: str = Field(default="", alias="GOOGLE_OAUTH_CLIENT_ID")

    # Observability / Langfuse
    #
    # Trace LLM chay SONG SONG voi structured log JSON, khong thay the no.
    # Langfuse lo phan ma log JSON khong lo duoc: prompt, completion, so token,
    # chi phi tung lan goi. Con Server-Timing va X-Request-ID van do
    # request_timing dam nhiem, nen Langfuse chet hay chua cau hinh thi kha nang
    # tra loi nguoi dung van nguyen ven.
    #
    # Thieu key -> tat han, khong raise. Day la duong phu, khong duoc phep lam
    # chet duong chinh.
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # Che noi dung truoc khi gui di. Mac dinh BAT.
    #
    # Prompt cua app nhung ten chi so, gia tri, don vi, tuoi va gioi tinh benh
    # nhan. Gui nguyen sang may chu ben thu ba la dua du lieu suc khoe ra ngoai
    # ha tang cua minh. Doi lai chi con xem duoc do tre, token va ma loi — du de
    # biet LLM hong bao nhieu phan tram va o dau, khong du de doc noi dung.
    langfuse_mask_payloads: bool = True

    # Ghi mot dong trace gon cho moi request vao DB, phuc vu man hinh admin.
    # Tach khoi Langfuse co chu y: admin van xem duoc khi Langfuse chua cau hinh.
    trace_persistence_enabled: bool = True
    trace_retention_days: int = Field(default=14, ge=1, le=365)

    # Auth (JWT)
    jwt_secret: str = Field(default=_INSECURE_DEFAULT_JWT_SECRET, alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60 * 12, ge=1)
    # Phiên khách sống ngắn hơn phiên đăng nhập: khách không có gì để khôi phục
    # sau khi hết hạn, giữ token lâu chỉ kéo dài quyền gọi LLM/OCR ẩn danh.
    guest_session_expire_minutes: int = Field(default=120, ge=1)

    @model_validator(mode="after")
    def _reject_insecure_jwt_secret_in_production(self) -> "Settings":
        # Nếu quên set JWT_SECRET thật lúc deploy, app sẽ âm thầm dùng giá trị
        # mặc định — giá trị này lộ công khai trong .env.example, ai cũng có
        # thể tự ký JWT giả mạo. Fail fast lúc khởi động thay vì để lỗ hổng
        # nằm im đến khi bị khai thác.
        if self.app_env == "production" and self.jwt_secret == _INSECURE_DEFAULT_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET đang dùng giá trị mặc định không an toàn trong môi trường "
                "production — phải set biến môi trường JWT_SECRET thật trước khi deploy."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
