from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    embedding_model: str = "multilingual-e5-small"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32
    local_storage_path: str = "./data/files"
    max_sessions_per_user: int = 10
    max_sources_per_session: int = 20
    max_file_size_mb: float = 25
    max_pdf_pages: int = 500
    max_text_input_chars: int = 200_000
    chunk_size: int = 500
    chunk_overlap: int = 50

    rate_limit_auth_requests: int = 10
    rate_limit_auth_window_seconds: int = 60

    @field_validator("database_url")
    @classmethod
    def use_psycopg3_driver(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
