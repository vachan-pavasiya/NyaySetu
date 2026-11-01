"""Application configuration module.

Role: Loads environment variables and provides typed settings across the app.
Data flow: .env file / environment -> Pydantic Settings -> imported by modules.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for Court-Order Compliance Radar."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-flash-lite-latest"
    GEMINI_FALLBACK_MODEL: str = "gemini-1.5-flash"
    DAILY_GEMINI_BUDGET: int = 250

    # AWS S3 Settings (Open Dataset)
    S3_BUCKET: str = "indian-high-court-judgments"
    AWS_DEFAULT_REGION: str = "ap-south-1"

    # Compliance & Ledger Calculations
    SERVICE_LAG_DAYS: int = 30

    # Persistence & Networking
    DATABASE_URL: str = "sqlite:///./compliance_radar.db"
    ALLOWED_ORIGINS: str = "*"
    ENVIRONMENT: str = "production"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()

