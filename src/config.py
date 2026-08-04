from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Vision LLM Adapter (OCR — ADR-006)
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    vision_model: str = "google/gemma-4-26b-a4b-it:free"
    vision_base_url: str = "https://openrouter.ai/api/v1"
    vision_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    vision_max_image_mb: int = Field(default=10, ge=1, le=25)
    vision_timeout_seconds: float = Field(default=90.0, ge=1.0, le=300.0)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"
    embedding_device: Literal["cpu", "cuda", "mps"] = "cpu"

    # Agent Rules / Reference
    critical_thresholds_path: str = "./data/reference/critical_thresholds.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
