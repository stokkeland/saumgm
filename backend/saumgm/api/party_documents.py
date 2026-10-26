"""Documents on file for a contact: W-9s, exemption certificates, insurance, contracts...

Files can hold taxpayer ids (a sole proprietor's W-9 has their SSN), so downloading one needs the
owner or bookkeeper role and is recorded in the audit log. Viewers see the list, not the files.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select

from saumgm import audit
from saumgm.api.common import (
    ArchiveFilter,
    apply_archive_filter,
    apply_changes,
    get_owned,
    not_found,
    set_archived,
)
from saumgm.api.deps import Auth, DbSession, Editor, Owner, Reader
from saumgm.enums import DocumentType
from saumgm.models import Organization, Party, PartyDocument, TaxExemption
from saumgm.schemas.party_documents import DocumentFile, DocumentOut, DocumentPatch
from saumgm.services import party_documents as service
from saumgm.storage import MAX_UPLOAD_BYTES, read_file, store_file
from saumgm.timeutil import today_in

router = APIRouter(tags=["documents"])

ALLOWED_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/tiff",
    "image/heic",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _today(db: DbSession, auth: Auth) -> date:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    return today_in(org.timezone)


def out(doc: PartyDocument, party_name: str, today: date) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        party_id=doc.party_id,
        party_name=party_name,
        document_type=doc.document_type,
        title=doc.title,
        tax_exemption_id=doc.tax_exemption_id,
        document_date=doc.document_date,
        expires_on=doc.expires_on,
        remind_days_before=doc.remind_days_before,
        notes=doc.notes,
        status=service.status(doc, today),
        days_to_expiry=(doc.expires_on - today).days if doc.expires_on else None,
        file=DocumentFile(
            id=doc.file.id,
            original_name=doc.file.original_name,
            content_type=doc.file.content_type,
            size_bytes=doc.file.size_bytes,
            created_at=doc.file.created_at,
        )
        if doc.file
        else None,
        archived_at=doc.archived_at,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _document(db: DbSession, auth: Auth, party_id: int, document_id: int) -> PartyDocument:
    doc = get_owned(db, PartyDocument, document_id, auth.organization_id)
    if doc.party_id != party_id:
        raise not_found("Document")
    return doc


def _check_exemption(db: DbSession, party_id: int, exemption_id: int | None) -> None:
    if exemption_id is None:
        return
    exemption = db.get(TaxExemption, exemption_id)
    if exemption is None or exemption.party_id != party_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That tax exemption is not this contact's"
        )


def _check_dates(document_date: date | None, expires_on: date | None) -> None:
    if document_date and expires_on and expires_on < document_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The expiry date is before the document date"
        )


async def _read_upload(upload: UploadFile) -> bytes:
    if upload.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Use a PDF, an image or a Word document"
        )
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is larger than 20 MB")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty")
    return data


@router.get("/contacts/{party_id}/documents")
def list_documents(
    party_id: int, auth: Reader, db: DbSession, archived: ArchiveFilter = ArchiveFilter.CURRENT
) -> list[DocumentOut]:
    party = get_owned(db, Party, party_id, auth.organization_id)
    stmt = select(PartyDocument).where(PartyDocument.party_id == party.id)
    stmt = apply_archive_filter(stmt, PartyDocument, archived).order_by(
        PartyDocument.document_type, PartyDocument.id.desc()
    )
    today = _today(db, auth)
    return [out(d, party.name, today) for d in db.scalars(stmt)]


@router.post("/contacts/{party_id}/documents", status_code=status.HTTP_201_CREATED)
async def add_document(
    party_id: int,
    auth: Editor,
    db: DbSession,
    document_type: Annotated[DocumentType, Form()],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    file: Annotated[UploadFile | None, File()] = None,
    tax_exemption_id: Annotated[int | None, Form()] = None,
    document_date: Annotated[date | None, Form()] = None,
    expires_on: Annotated[date | None, Form()] = None,
    remind_days_before: Annotated[int | None, Form(ge=0, le=3650)] = None,
    notes: Annotated[str | None, Form()] = None,
    replace_previous: Annotated[
        bool, Form(description="Archive this contact's current documents of the same type")
    ] = False,
) -> DocumentOut:
    """Record a document, with or without a file (multipart form)."""
    party = get_owned(db, Party, party_id, auth.organization_id)
    _check_exemption(db, party.id, tax_exemption_id)
    _check_dates(document_date, expires_on)
    stored = None
    if file is not None and file.filename:
        data = await _read_upload(file)
        stored = store_file(
            db, auth.organization_id, data, file.filename, file.content_type, auth.user.id
        )
    if replace_previous:
        for old in db.scalars(
            select(PartyDocument).where(
                PartyDocument.party_id == party.id,
                PartyDocument.document_type == document_type,
                PartyDocument.archived_at.is_(None),
            )
        ):
            set_archived(old, True)
    doc = PartyDocument(
        organization_id=auth.organization_id,
        party_id=party.id,
        document_type=document_type,
        title=title.strip(),
        file_id=stored.id if stored else None,
        tax_exemption_id=tax_exemption_id,
        document_date=document_date,
        expires_on=expires_on,
        remind_days_before=remind_days_before,
        notes=(notes or "").strip() or None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return out(doc, party.name, _today(db, auth))


@router.patch("/contacts/{party_id}/documents/{document_id}")
def update_document(
    party_id: int, document_id: int, body: DocumentPatch, auth: Editor, db: DbSession
) -> DocumentOut:
    doc = _document(db, auth, party_id, document_id)
    _check_exemption(db, party_id, body.tax_exemption_id)
    changes = body.model_dump(exclude_unset=True)
    _check_dates(
        changes.get("document_date", doc.document_date), changes.get("expires_on", doc.expires_on)
    )
    apply_changes(doc, body)
    db.commit()
    party = db.get(Party, party_id)
    assert party is not None
    return out(doc, party.name, _today(db, auth))


@router.put("/contacts/{party_id}/documents/{document_id}/file")
async def replace_file(
    party_id: int,
    document_id: int,
    file: Annotated[UploadFile, File()],
    auth: Editor,
    db: DbSession,
) -> DocumentOut:
    """Attach a file (e.g. the scan of a paper copy), or replace a wrong one. The earlier file
    stays in storage, and the audit log records the change."""
    doc = _document(db, auth, party_id, document_id)
    data = await _read_upload(file)
    stored = store_file(
        db, auth.organization_id, data, file.filename or "document", file.content_type, auth.user.id
    )
    doc.file_id = stored.id
    db.commit()
    db.refresh(doc)
    party = db.get(Party, party_id)
    assert party is not None
    return out(doc, party.name, _today(db, auth))


@router.get("/contacts/{party_id}/documents/{document_id}/file")
def download_file(
    party_id: int,
    document_id: int,
    auth: Editor,
    db: DbSession,
    download: Annotated[bool, Query(description="Save instead of opening in the browser")] = False,
) -> Response:
    doc = _document(db, auth, party_id, document_id)
    if doc.file is None:
        raise not_found("File of this document")
    data = read_file(doc.file)
    audit.record(
        db,
        "download",
        entity_type="party_document",
        entity_id=str(doc.id),
        parent_type="party",
        parent_id=str(party_id),
    )
    db.commit()
    disposition = "attachment" if download else "inline"
    name = doc.file.original_name.replace('"', "")
    return Response(
        data,
        media_type=doc.file.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/contacts/{party_id}/documents/{document_id}/archive")
def archive_document(party_id: int, document_id: int, auth: Editor, db: DbSession) -> DocumentOut:
    """Mark as superseded: kept on file, no longer checked for expiry."""
    doc = _document(db, auth, party_id, document_id)
    set_archived(doc, True)
    db.commit()
    party = db.get(Party, party_id)
    assert party is not None
    return out(doc, party.name, _today(db, auth))


@router.post("/contacts/{party_id}/documents/{document_id}/unarchive")
def unarchive_document(party_id: int, document_id: int, auth: Editor, db: DbSession) -> DocumentOut:
    doc = _document(db, auth, party_id, document_id)
    set_archived(doc, False)
    db.commit()
    party = db.get(Party, party_id)
    assert party is not None
    return out(doc, party.name, _today(db, auth))


@router.delete(
    "/contacts/{party_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_document(party_id: int, document_id: int, auth: Owner, db: DbSession) -> None:
    """For mistakes (owner only); superseded documents should be archived instead."""
    db.delete(_document(db, auth, party_id, document_id))
    db.commit()


@router.get("/documents/attention")
def documents_needing_attention(
    auth: Reader,
    db: DbSession,
    within_days: Annotated[
        int | None,
        Query(ge=0, le=3650, description="Instead of each document's own reminder window"),
    ] = None,
) -> list[DocumentOut]:
    """Current documents of all contacts that have expired or expire soon, soonest first."""
    today = _today(db, auth)
    docs = service.needing_attention(db, auth.organization_id, today, within_days)
    names = dict(
        db.execute(
            select(Party.id, Party.name).where(Party.id.in_({d.party_id for d in docs}))
        ).all()
    )
    return [out(d, names.get(d.party_id, "?"), today) for d in docs]
