"""Application configuration via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import List, Literal, Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "VOLO AI"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "volo"
    postgres_password: str = Field(default="volo_secret")
    postgres_db: str = "volo_ai"
    db_pool_size: int = 20
    db_max_overflow: int = 10

    @computed_field
    @property
    def database_url(self) -> str:
        """Async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def sync_database_url(self) -> str:
        """Sync PostgreSQL connection URL for Alembic."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0

    @computed_field
    @property
    def redis_url(self) -> str:
        """Redis connection URL."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # JWT Authentication
    jwt_secret_key: str = Field(default="your-super-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Encryption (for PII)
    encryption_key: str = Field(default="your-32-byte-encryption-key-here")

    # AWS S3
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "ap-south-1"
    s3_bucket_name: str = "volo-ai-media"
    s3_endpoint_url: Optional[str] = None  # For MinIO in dev

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_prefix: str = "volo"

    # AI - Claude API
    anthropic_api_key: Optional[str] = None
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 1024

    # Payment Gateways
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    payfast_merchant_id: Optional[str] = None
    payfast_merchant_key: Optional[str] = None
    payfast_passphrase: Optional[str] = None
    payfast_sandbox: bool = True
    jazzcash_merchant_id: Optional[str] = None
    jazzcash_password: Optional[str] = None
    easypaisa_store_id: Optional[str] = None
    easypaisa_hash_key: Optional[str] = None

    # WhatsApp (Twilio)
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_whatsapp_number: Optional[str] = None

    # Email (SendGrid)
    sendgrid_api_key: Optional[str] = None
    email_from_address: str = "noreply@voloai.pk"
    email_from_name: str = "VOLO AI"

    # Push Notifications (Firebase)
    firebase_credentials_path: Optional[str] = None

    # Rate Limiting
    rate_limit_per_minute: int = 100

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Commission (flat 9% includes all gateway fees)
    marketplace_commission_percent: float = 9.0
    direct_booking_commission_percent: float = 0.0

    # Payout
    payout_time_hour: int = 6  # 6 AM PKT
    minimum_payout_amount: int = 100000  # 1000 PKR in paisa


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
