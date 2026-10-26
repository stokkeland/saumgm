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
