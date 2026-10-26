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

from datetime import date, datetime

from pydantic import BaseModel, Field

from saumgm.enums import DocumentStatus, DocumentType


class DocumentPatch(BaseModel):
    """Changes to a document's details (the file itself is replaced with PUT .../file)."""

    document_type: DocumentType | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    tax_exemption_id: int | None = None
    document_date: date | None = None
    expires_on: date | None = None
    remind_days_before: int | None = Field(None, ge=0, le=3650)
    notes: str | None = None


class DocumentFile(BaseModel):
    id: int
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class DocumentOut(BaseModel):
    id: int
    party_id: int
    party_name: str
    document_type: DocumentType
    title: str
    tax_exemption_id: int | None
    document_date: date | None
    expires_on: date | None
    remind_days_before: int | None
    notes: str | None
    status: DocumentStatus
    days_to_expiry: int | None
    file: DocumentFile | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
