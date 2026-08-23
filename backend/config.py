"""
Configuration management for FinSage AI.
Uses Pydantic v2 settings for environment variable validation.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.security.startup import dev_secret

ENV_FILE_PATH = str(Path(__file__).resolve().parent.parent / ".env")


class DatabaseSettings(BaseSettings):
    """PostgreSQL configuration"""
    url: str = Field(default="postgresql+asyncpg://user:pass@localhost:5432/finsage")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=20)
    max_overflow: int = Field(default=10)

    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class RedisSettings(BaseSettings):
    """Redis configuration"""
    url: str = Field(default="redis://localhost:6379")
    db: int = Field(default=0)

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class QdrantSettings(BaseSettings):
    """Qdrant vector database configuration"""
    url: str = Field(default="http://localhost:6333")
    api_key: str | None = Field(default=None)
    collection_names: dict = Field(
        default={
            "income_tax": "income_tax_corpus",
            "gst": "gst_corpus",
            "schemes": "govt_schemes",
            "sebi": "sebi_regulations",
        }
    )

    model_config = SettingsConfigDict(
        env_prefix="QDRANT_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class LLMSettings(BaseSettings):
    """Groq LLM configuration"""
    api_key: str = Field(default="")
    # `llama-3.3-70b-versatile` was retired from Groq's catalog — every LLM
    # call in the live app was 404ing on "model does not exist", found by
    # actually running the AGT-005 fixture generator against a live key
    # rather than the (necessarily offline) replay-mode test suite. This is
    # exactly the class of drift `python -m backend.evals.runner --live`'s
    # nightly run exists to catch, but nothing had actually run it live yet.
    # `openai/gpt-oss-120b` is confirmed on Groq's free plan (30 RPM / 1,000
    # RPD / 8,000 TPM — the observed rate-limit headers on this key matched
    # those exactly), not the metered paid tier.
    model: str = Field(default="openai/gpt-oss-120b")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=2048)
    timeout: int = Field(default=30)

    model_config = SettingsConfigDict(
        env_prefix="GROQ_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class SearchSettings(BaseSettings):
    """Web search configuration"""
    tavily_api_key: str = Field(default="")
    serper_api_key: str = Field(default="")
    max_results: int = Field(default=5)

    model_config = SettingsConfigDict(
        env_prefix="SEARCH_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class AuthSettings(BaseSettings):
    """JWT and authentication configuration"""
    # No shared default, deliberately — PRD-005.
    #
    # This shipped as "your-super-secret-key-change-in-production", which is a
    # published secret: any deployment that never set the variable signed its
    # JWTs with a constant anyone could read in the repository. The app started
    # and every test passed, so nothing ever surfaced it.
    #
    # In development the key is now random PER PROCESS, so there is no constant
    # to leak and none to accidentally deploy. A dev login does not survive a
    # restart, which is a small price and arguably right. Production sets the
    # variable or `backend.security.startup.enforce` refuses to boot.
    secret_key: str = Field(default_factory=dev_secret)
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15)
    refresh_token_expire_days: int = Field(default=7)

    model_config = SettingsConfigDict(
        env_prefix="JWT_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class TelegramSettings(BaseSettings):
    """Telegram bot configuration"""
    bot_token: str = Field(default="")
    webhook_url: str | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_prefix="TELEGRAM_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class EmailSettings(BaseSettings):
    """Email notification configuration"""
    smtp_host: str = Field(default="smtp.resend.com")
    smtp_port: int = Field(default=465)
    sender_email: str = Field(default="")
    sender_name: str = Field(default="FinSage AI")
    resend_api_key: str | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_prefix="EMAIL_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class S3Settings(BaseSettings):
    """AWS S3 configuration for document vault"""
    access_key_id: str = Field(default="")
    secret_access_key: str = Field(default="")
    bucket_name: str = Field(default="finsage-documents")
    region: str = Field(default="ap-south-1")
    endpoint_url: str | None = Field(default=None)  # For MinIO self-hosted

    model_config = SettingsConfigDict(
        env_prefix="AWS_",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class MetricsSettings(BaseSettings):
    """PRD-004. The scrape endpoint's bearer token.

    Empty by default and NOT given a placeholder: in production an empty token
    means `/metrics` returns 404 rather than serving request volumes, error
    rates and withheld-answer counts to anyone who asks. In development it is
    served openly, because a token on a local Prometheus is friction people
    route around rather than accept.
    """

    token: str = Field(default="")

    model_config = SettingsConfigDict(
        env_prefix="METRICS__",
        env_file=ENV_FILE_PATH,
        extra="ignore",
    )


class AppSettings(BaseSettings):
    """Main application configuration"""
    environment: str = Field(default="development")
    debug: bool = Field(default=True)
    app_name: str = Field(default="FinSage AI")
    api_version: str = Field(default="v1")
    allowed_origins: Any = Field(default=["http://localhost:5173", "http://localhost:3000"])
    log_level: str = Field(default="INFO")
    log_file: str | None = Field(default="logs/finsage.log")

    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def postgres_url(self) -> str:
        return self.database.url

    @property
    def redis_url(self) -> str:
        return self.redis.url


# Singleton pattern for configuration
@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Get application settings (cached singleton)"""
    return AppSettings()


# Export for easy import
settings = get_settings()
