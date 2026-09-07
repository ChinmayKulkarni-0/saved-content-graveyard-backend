import json
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.getenv("ENV_FILE", ".env.dev"))

    APP_NAME: str = "Saved Content Graveyard"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./graveyard.db"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    OPENAI_API_KEY: str | None = None
    GOOGLE_VISION_API_KEY: str | None = None
    GOOGLE_GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_MODEL_FALLBACK: str = "gemini-2.0-flash-lite"

    RATE_LIMIT_FREE_TIER: int = 10
    RATE_LIMIT_PRO_TIER: int = 100

    IMAGE_UPLOAD_MAX_SIZE_MB: int = 10
    IMAGE_RETENTION_SECONDS: int = 30

    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost", "http://localhost:3000"]
    )


settings = Settings()