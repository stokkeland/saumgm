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

from datetime import datetime

from pydantic import BaseModel, Field

from saumgm.enums import EmailKind, EmailStatus


class EmailSettingsOut(BaseModel):
    from_address: str | None
    from_name: str | None
    reply_to: str | None
    # What goes out now: the business's sender, or EMAIL_FROM from the server's .env.
    sender: str | None
    default_from: str | None
    backend: str
    redirect_to: str | None


class EmailSettingsPatch(BaseModel):
    from_address: str | None = Field(None, max_length=255)
    from_name: str | None = Field(None, max_length=200)
    reply_to: str | None = Field(None, max_length=255)


class TemplateOut(BaseModel):
    kind: EmailKind
    subject: str
    body: str
    customized: bool
    placeholders: dict[str, str]


class TemplateIn(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)


class DraftOut(BaseModel):
    kind: EmailKind
    to: list[str]
    cc: list[str]
    subject: str
    body: str
    attachments: list[str]
    # Set on installations where EMAIL_REDIRECT_TO sends everything to one address.
    redirect_to: str | None


class SendIn(BaseModel):
    to: list[str] = Field(min_length=1, max_length=20)
    cc: list[str] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)


class TestIn(BaseModel):
    to: str | None = Field(None, max_length=255)


class MessageOut(BaseModel):
    id: int
    created_at: datetime
    sent_by: str | None
    kind: EmailKind
    entity_type: str | None
    entity_id: str | None
    from_address: str
    to_addresses: str
    cc_addresses: str | None
    redirected_to: str | None
    subject: str
    body_text: str
    attachments: list[str]
    provider: str
    provider_message_id: str | None
    status: EmailStatus
    error: str | None
