import os

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRETS = {
    "change-me-in-production",
    "dev-secret-change-me",
    "replace-with-a-long-random-secret",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.getenv("ENV_FILE", ".env.dev"))

    APP_NAME: str = "Saved Content Graveyard"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "dev"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./graveyard.db"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    OPENAI_API_KEY: str | None = None
    GOOGLE_VISION_API_KEY: str | None = None
    GOOGLE_GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_MODEL_FALLBACK: str = "gemini-2.0-flash-lite"

    RATE_LIMIT_FREE_TIER: int = 10
    RATE_LIMIT_PRO_TIER: int = 100
    RATE_LIMIT_AUTH_TRIES: int = 10

    TRUST_X_FORWARDED_FOR: bool = False

    IMAGE_UPLOAD_MAX_SIZE_MB: int = 10
    IMAGE_RETENTION_SECONDS: int = 30
    IMAGE_TEMP_DIR: str = "/tmp/scg_uploads"

    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost", "http://localhost:3000"]
    )

    @model_validator(mode="after")
    def _guard_production_secrets(self) -> "Settings":
        """Fail fast in production rather than ship forgeable tokens/admin access."""
        if self.APP_ENV.lower() != "production":
            return self
        if self.SECRET_KEY in _INSECURE_SECRETS:
            raise ValueError(
                "SECRET_KEY must be a strong random value in production (APP_ENV=production)"
            )
        if self.ADMIN_PASSWORD in ("", "admin", "password", "replace-with-a-strong-password"):
            raise ValueError(
                "ADMIN_PASSWORD must be a strong value in production (APP_ENV=production)"
            )
        return self


settings = Settings()