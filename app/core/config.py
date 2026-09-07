from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Saved Content Graveyard API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite:///./graveyard.db"

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    OPENAI_API_KEY: str = ""
    GOOGLE_VISION_API_KEY: str = ""
    GOOGLE_GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_MODEL_FALLBACK: str = "gemini-2.0-flash-lite"

    RATE_LIMIT_FREE_TIER: int = 10
    RATE_LIMIT_PRO_TIER: int = 100

    IMAGE_UPLOAD_MAX_SIZE_MB: int = 10
    IMAGE_RETENTION_SECONDS: int = 30

    CORS_ORIGINS: list[str] = ["http://localhost", "http://localhost:3000"]

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
