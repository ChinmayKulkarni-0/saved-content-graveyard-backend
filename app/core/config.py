from pydantic import BaseSettings, Field
import os

class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    DEBUG: bool = Field(..., env="DEBUG")

    class Config:
        env_file = os.getenv("ENV_FILE", ".env")

settings = Settings()
