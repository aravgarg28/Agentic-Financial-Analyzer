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

    class Config:
        env_file = ".env"


settings = Settings()
