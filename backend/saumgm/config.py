# SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
# Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details. You should have received a copy of the
# GNU General Public License along with this program (the LICENSE file); if not, see
# <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
    # Login sessions
    session_days: int = 14
    # Send cookies only over HTTPS. Defaults to on in production, off in development.
    cookie_secure: bool | None = None
    # Email (saumgm/email.py): console:// logs messages instead of sending; resend:// sends them
    # through Resend with RESEND_API_KEY. The sender is a business setting (Admin -> Email);
    # EMAIL_FROM is the default until it is set. EMAIL_REDIRECT_TO sends every message to that
    # address instead of the real recipients (development and test installations).
    email_url: str = "console://"
    resend_api_key: str | None = None
    email_from: str | None = None
    email_redirect_to: str | None = None
    # The address users open the app at (https://saumgm.example.com), for links in emails such
    # as the reminders digest. Without it the digest has no links.
    app_url: str | None = None

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment == "production"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from env / .env
