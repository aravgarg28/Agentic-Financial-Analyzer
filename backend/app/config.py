import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


class Settings(BaseSettings):
    # LLM
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:password@db:5432/financial_db",
    )
    sync_database_url: str = os.getenv(
        "SYNC_DATABASE_URL",
        "postgresql+psycopg2://user:password@db:5432/financial_db",
    )

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379")

    # App
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key")
    environment: str = os.getenv("ENVIRONMENT", "development")

    # Sessions / auth cookie (T-011). Lifetimes in seconds.
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "afa_session")
    session_idle_seconds: int = int(os.getenv("SESSION_IDLE_SECONDS", str(14 * 24 * 3600)))
    session_absolute_seconds: int = int(
        os.getenv("SESSION_ABSOLUTE_SECONDS", str(30 * 24 * 3600))
    )
    # Cookie Secure flag: on by default; disabled automatically in development
    # so local http testing works. Never disable in production.
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "").lower() in ("1", "true", "yes")
    # Optional explicit cookie domain (e.g. ".example.com") for cross-subdomain
    # Render deploys; empty means host-only cookie.
    cookie_domain: str = os.getenv("COOKIE_DOMAIN", "")

    # CSV import (T-070). Per-file size cap and per-household total document quota.
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    household_document_quota_bytes: int = int(
        os.getenv("HOUSEHOLD_DOCUMENT_QUOTA_BYTES", str(50 * 1024 * 1024))
    )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cookie_secure_effective(self) -> bool:
        # Force Secure in production regardless of the env toggle.
        return self.cookie_secure or self.is_production

    class Config:
        env_file = ".env"


settings = Settings()
