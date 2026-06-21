"""
Configuration management for FinSage AI.
Uses Pydantic v2 settings for environment variable validation.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, Any
from functools import lru_cache
from pathlib import Path

ENV_FILE_PATH = str(Path(__file__).resolve().parent.parent / ".env")


class DatabaseSettings(BaseSettings):
    """PostgreSQL configuration"""
    url: str = Field(default="postgresql+asyncpg://user:pass@localhost:5432/finsage")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=20)
    max_overflow: int = Field(default=10)
    
    class Config:
        env_prefix = "POSTGRES_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class RedisSettings(BaseSettings):
    """Redis configuration"""
    url: str = Field(default="redis://localhost:6379")
    db: int = Field(default=0)
    
    class Config:
        env_prefix = "REDIS_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class QdrantSettings(BaseSettings):
    """Qdrant vector database configuration"""
    url: str = Field(default="http://localhost:6333")
    api_key: Optional[str] = Field(default=None)
    collection_names: dict = Field(
        default={
            "income_tax": "income_tax_corpus",
            "gst": "gst_corpus",
            "schemes": "govt_schemes",
            "sebi": "sebi_regulations",
        }
    )
    
    class Config:
        env_prefix = "QDRANT_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class LLMSettings(BaseSettings):
    """Groq LLM configuration"""
    api_key: str = Field(default="")
    model: str = Field(default="llama-3.3-70b-versatile")
    temperature: float = Field(default=0.7)
    max_tokens: int = Field(default=2048)
    timeout: int = Field(default=30)
    
    class Config:
        env_prefix = "GROQ_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class SearchSettings(BaseSettings):
    """Web search configuration"""
    tavily_api_key: str = Field(default="")
    serper_api_key: str = Field(default="")
    max_results: int = Field(default=5)
    
    class Config:
        env_prefix = "SEARCH_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class AuthSettings(BaseSettings):
    """JWT and authentication configuration"""
    secret_key: str = Field(default="your-super-secret-key-change-in-production")
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15)
    refresh_token_expire_days: int = Field(default=7)
    
    class Config:
        env_prefix = "JWT_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class TelegramSettings(BaseSettings):
    """Telegram bot configuration"""
    bot_token: str = Field(default="")
    webhook_url: Optional[str] = Field(default=None)
    
    class Config:
        env_prefix = "TELEGRAM_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class EmailSettings(BaseSettings):
    """Email notification configuration"""
    smtp_host: str = Field(default="smtp.resend.com")
    smtp_port: int = Field(default=465)
    sender_email: str = Field(default="")
    sender_name: str = Field(default="FinSage AI")
    resend_api_key: Optional[str] = Field(default=None)
    
    class Config:
        env_prefix = "EMAIL_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class S3Settings(BaseSettings):
    """AWS S3 configuration for document vault"""
    access_key_id: str = Field(default="")
    secret_access_key: str = Field(default="")
    bucket_name: str = Field(default="finsage-documents")
    region: str = Field(default="ap-south-1")
    endpoint_url: Optional[str] = Field(default=None)  # For MinIO self-hosted
    
    class Config:
        env_prefix = "AWS_"
        env_file = ENV_FILE_PATH
        extra = "ignore"


class AppSettings(BaseSettings):
    """Main application configuration"""
    environment: str = Field(default="development")
    debug: bool = Field(default=True)
    app_name: str = Field(default="FinSage AI")
    api_version: str = Field(default="v1")
    allowed_origins: Any = Field(default=["http://localhost:5173", "http://localhost:3000"])
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = Field(default="logs/finsage.log")
    
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
    
    class Config:
        env_file = ENV_FILE_PATH
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"
    
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