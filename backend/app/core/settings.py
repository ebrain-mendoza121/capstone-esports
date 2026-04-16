from functools import lru_cache
from pathlib import Path
from typing import Annotated, Union, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
# Explanation:
# app/core/settings.py -> parents[0]=core, [1]=app, [2]=backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    cors_origins: Annotated[List[str], NoDecode] = ["https://capstone-esports-production-6e32.up.railway.app"]
    riot_api_key: str = ""

    # Request behavior
    http_timeout_seconds: float = 15.0
    riot_max_retries: int = 6
    riot_backoff_base_seconds: float = 1.0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
