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

from pathlib import Path

from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response

from saumgm.email import EmailError, Message

BACKEND_DIR = Path(__file__).resolve().parent.parent

PASSWORD = "correct horse battery"


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


def login(client: TestClient, email: str, password: str = PASSWORD) -> Response:
    """Log in and send the CSRF token on every later request, like the frontend does."""
    response: Response = client.post("/api/auth/login", json={"email": email, "password": password})
    if response.status_code == 200:
        client.headers["X-CSRF-Token"] = client.cookies["saumgm_csrf"]
    return response


class Outbox:
    """Records messages instead of sending them; can be told to fail (the `outbox` fixture)."""

    name = "test"

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.fail_with: str | None = None

    def send(self, message: Message) -> str | None:
        if self.fail_with:
            raise EmailError(self.fail_with)
        self.messages.append(message)
        return f"msg-{len(self.messages)}"
