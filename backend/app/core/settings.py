from pathlib import Path
from typing import Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
# Explanation:
# app/core/settings.py -> parents[0]=core, [1]=app, [2]=backend

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    RIOT_API_KEY: str
    DATABASE_URL: str = "postgresql://esports:esports@localhost:5432/esports"

    # Request behavior
    HTTP_TIMEOUT_SECONDS: float = 15.0
    RIOT_MAX_RETRIES: int = 6
    RIOT_BACKOFF_BASE_SECONDS: float = 1.0

    # CORS - can be set via env as comma-separated string or JSON array
    CORS_ORIGINS: Union[list[str], str] = "http://localhost:5173"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # If it's a comma-separated string, split it
            return [origin.strip() for origin in v.split(",")]
        return v


settings = Settings()