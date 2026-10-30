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

"""Downloads of stored files and generated PDF documents, and the business logo."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select

from saumgm.api.common import get_owned, not_found
from saumgm.api.deps import Auth, DbSession, Owner, Reader
from saumgm.documents import deposit_slip_pdf, invoice_pdf, receipt_pdf
from saumgm.enums import UserRoleType
from saumgm.models import (
    AssetAttachment,
    Deposit,
    Invoice,
    InvoiceRevision,
    Organization,
    PartyDocument,
    Payment,
    StoredFile,
)
from saumgm.storage import MAX_UPLOAD_BYTES, read_file, store_file

router = APIRouter(tags=["documents"])

LOGO_TYPES = {"image/png", "image/jpeg", "image/gif"}


def _pdf(data: bytes, filename: str) -> Response:
    return Response(
        data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def _org(db: DbSession, auth: Auth) -> Organization:
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    return org


def _stored(db: DbSession, file_id: int, auth: Auth) -> Response:
    stored = get_owned(db, StoredFile, file_id, auth.organization_id)
    return Response(
        read_file(stored),
        media_type=stored.content_type,
        headers={"Content-Disposition": f'inline; filename="{stored.original_name}"'},
    )


@router.get("/files/{file_id}")
def download(file_id: int, auth: Reader, db: DbSession) -> Response:
    # Contact documents (W-9s...) have their own audited download for owners and bookkeepers;
    # asset attachments (configurations) can hold passwords.
    if auth.role == UserRoleType.VIEWER:
        for model in (PartyDocument, AssetAttachment):
            if db.scalar(select(model.id).where(model.file_id == file_id).limit(1)):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not allow this")
    return _stored(db, file_id, auth)


@router.get("/invoices/{invoice_id}/pdf")
def invoice_document(invoice_id: int, auth: Reader, db: DbSession) -> Response:
    """The document as issued (kept since issuing); drafts and imported ones are rendered now."""
    invoice = get_owned(db, Invoice, invoice_id, auth.organization_id)
    if invoice.pdf_file_id is not None:
        return _stored(db, invoice.pdf_file_id, auth)
    name = f"invoice-{invoice.number or 'draft'}.pdf"
    return _pdf(invoice_pdf(db, _org(db, auth), invoice), name)


@router.get("/invoices/{invoice_id}/revisions/{revision_no}/pdf")
def revision_document(invoice_id: int, revision_no: int, auth: Reader, db: DbSession) -> Response:
    invoice = get_owned(db, Invoice, invoice_id, auth.organization_id)
    revision = db.scalars(
        select(InvoiceRevision).where(
            InvoiceRevision.invoice_id == invoice.id, InvoiceRevision.revision_no == revision_no
        )
    ).one_or_none()
    if revision is None or revision.pdf_file_id is None:
        raise not_found("Document of that revision")
    return _stored(db, revision.pdf_file_id, auth)


@router.get("/payments/{payment_id}/receipt.pdf")
def payment_receipt(payment_id: int, auth: Reader, db: DbSession) -> Response:
    payment = get_owned(db, Payment, payment_id, auth.organization_id)
    return _pdf(receipt_pdf(db, _org(db, auth), payment), f"receipt-{payment.id}.pdf")


@router.get("/deposits/{deposit_id}/slip.pdf")
def deposit_slip(deposit_id: int, auth: Reader, db: DbSession) -> Response:
    deposit = get_owned(db, Deposit, deposit_id, auth.organization_id)
    return _pdf(deposit_slip_pdf(db, _org(db, auth), deposit), f"deposit-{deposit.id}.pdf")


@router.get("/settings/logo")
def get_logo(auth: Reader, db: DbSession) -> Response:
    org = _org(db, auth)
    if org.logo_file_id is None:
        raise not_found("Logo")
    return _stored(db, org.logo_file_id, auth)


@router.put("/settings/logo", status_code=status.HTTP_204_NO_CONTENT)
async def upload_logo(file: Annotated[UploadFile, File()], auth: Owner, db: DbSession) -> None:
    if file.content_type not in LOGO_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Use a PNG, JPEG or GIF image")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The image is too large")
    org = _org(db, auth)
    stored = store_file(db, org.id, data, file.filename or "logo", file.content_type, auth.user.id)
    org.logo_file_id = stored.id
    db.commit()


@router.delete("/settings/logo", status_code=status.HTTP_204_NO_CONTENT)
def remove_logo(auth: Owner, db: DbSession) -> None:
    org = _org(db, auth)
    org.logo_file_id = None
    db.commit()
