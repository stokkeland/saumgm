"""Deployment configuration, read from environment variables or backend/.env.

Business settings (company name, currency, tax setup, ...) do NOT live here; they are
stored in the database and edited in the app. See docs/design.md section 3.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    test_database_url: str | None = None
    storage_url: str = f"file:///{(BACKEND_DIR.parent / 'storage').as_posix()}"
    environment: Literal["development", "production"] = "development"
    cors_origins: Annotated[list[str], NoDecode] = []
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from env / .env
