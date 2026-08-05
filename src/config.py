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
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    model_name: str = "gemini-3.5-flash"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    openai_max_tokens: int = Field(default=2048, ge=1, le=8192)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"
    embedding_device: Literal["cpu", "cuda", "mps"] = "cpu"

    # Agent Rules / Reference
    critical_thresholds_path: str = "./data/reference/critical_thresholds.json"

    # Auth (JWT)
    jwt_secret: str = Field(default=_INSECURE_DEFAULT_JWT_SECRET, alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60 * 12, ge=1)

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
