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

"""Assets (equipment and licenses), their categories, and their attachments."""

from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from saumgm.api.common import LimitParam, OffsetParam, Page, conflict, get_owned, paginate
from saumgm.api.deps import Auth, DbSession, Editor, Owner, Reader
from saumgm.enums import AssetStatus
from saumgm.models import (
    Asset,
    AssetAttachment,
    AssetCategory,
    Expense,
    Organization,
    Party,
    StoredFile,
)
from saumgm.schemas.assets import (
    AssetAttachmentOut,
    AssetCategoryCreate,
    AssetCategoryOut,
    AssetCategoryPatch,
    AssetCreate,
    AssetFieldDef,
    AssetOut,
    AssetPatch,
)
from saumgm.services import assets as service
from saumgm.services.numbering import next_number
from saumgm.storage import MAX_UPLOAD_BYTES, store_file

router = APIRouter(tags=["assets"])


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


# -- categories -----------------------------------------------------------------------------------


def category_out(db: Session, category: AssetCategory) -> AssetCategoryOut:
    count = db.scalar(
        select(func.count()).select_from(Asset).where(Asset.category_id == category.id)
    )
    return AssetCategoryOut(
        id=category.id,
        name=category.name,
        sort_order=category.sort_order,
        is_active=category.is_active,
        fields=[AssetFieldDef(**f) for f in category.fields or []],
        assets=count or 0,
    )


@router.get("/asset-categories")
def list_categories(auth: Reader, db: DbSession) -> list[AssetCategoryOut]:
    rows = db.scalars(
        select(AssetCategory)
        .where(AssetCategory.organization_id == auth.organization_id)
        .order_by(AssetCategory.sort_order, AssetCategory.name)
    )
    return [category_out(db, c) for c in rows]


@router.post("/asset-categories", status_code=status.HTTP_201_CREATED)
def create_category(body: AssetCategoryCreate, auth: Owner, db: DbSession) -> AssetCategoryOut:
    fields = [f.model_dump(mode="json") for f in body.fields]
    try:
        service.check_fields(fields)
    except service.AssetError as exc:
        raise _unprocessable(exc) from None
    category = AssetCategory(
        organization_id=auth.organization_id,
        name=body.name.strip(),
        sort_order=body.sort_order,
        is_active=body.is_active,
        fields=fields,
    )
    db.add(category)
    db.commit()
    return category_out(db, category)


@router.patch("/asset-categories/{category_id}")
def update_category(
    category_id: int, body: AssetCategoryPatch, auth: Owner, db: DbSession
) -> AssetCategoryOut:
    """Removing a field keeps the values already stored with assets, hidden, until the field
    comes back or the asset is saved with other values."""
    category = get_owned(db, AssetCategory, category_id, auth.organization_id)
    if body.name is not None:
        category.name = body.name.strip()
    if body.sort_order is not None:
        category.sort_order = body.sort_order
    if body.is_active is not None:
        category.is_active = body.is_active
    if body.fields is not None:
        fields = [f.model_dump(mode="json") for f in body.fields]
        try:
            service.check_fields(fields)
        except service.AssetError as exc:
            raise _unprocessable(exc) from None
        category.fields = fields
    db.commit()
    return category_out(db, category)


@router.delete("/asset-categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, auth: Owner, db: DbSession) -> None:
    category = get_owned(db, AssetCategory, category_id, auth.organization_id)
    if category_out(db, category).assets:
        raise conflict("Assets are in this category; mark it inactive instead")
    db.delete(category)
    db.commit()


# -- assets ---------------------------------------------------------------------------------------


def assets_out(db: Session, assets: list[Asset]) -> list[AssetOut]:
    party_ids = {p for a in assets for p in (a.owner_party_id, a.vendor_party_id) if p}
    names = dict(db.execute(select(Party.id, Party.name).where(Party.id.in_(party_ids))).all())
    category_ids = {a.category_id for a in assets if a.category_id}
    categories = dict(
        db.execute(
            select(AssetCategory.id, AssetCategory.name).where(AssetCategory.id.in_(category_ids))
        ).all()
    )
    file_ids = {att.file_id for a in assets for att in a.attachments}
    files = {f.id: f for f in db.scalars(select(StoredFile).where(StoredFile.id.in_(file_ids)))}
    out = []
    for a in assets:
        out.append(
            AssetOut(
                id=a.id,
                tag=a.tag,
                name=a.name,
                category_id=a.category_id,
                category_name=categories.get(a.category_id) if a.category_id else None,
                manufacturer=a.manufacturer,
                model=a.model,
                serial_number=a.serial_number,
                status=a.status,
                owner_party_id=a.owner_party_id,
                owner_name=names.get(a.owner_party_id) if a.owner_party_id else None,
                location=a.location,
                assigned_to=a.assigned_to,
                purchase_date=a.purchase_date,
                purchase_price=a.purchase_price,
                vendor_party_id=a.vendor_party_id,
                vendor_name=names.get(a.vendor_party_id) if a.vendor_party_id else None,
                expense_id=a.expense_id,
                warranty_expires=a.warranty_expires,
                support_ends=a.support_ends,
                notes=a.notes,
                attributes=a.attributes or {},
                attachments=[
                    AssetAttachmentOut(
                        id=att.id,
                        file_id=att.file_id,
                        name=files[att.file_id].original_name,
                        content_type=files[att.file_id].content_type,
                        size=files[att.file_id].size_bytes,
                        uploaded_at=files[att.file_id].created_at,
                    )
                    for att in a.attachments
                ],
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
        )
    return out


def _check_refs(db: Session, auth: Auth, body: AssetCreate | AssetPatch) -> None:
    for party_id in (body.owner_party_id, body.vendor_party_id):
        if party_id is not None:
            get_owned(db, Party, party_id, auth.organization_id)
    if body.category_id is not None:
        get_owned(db, AssetCategory, body.category_id, auth.organization_id)
    if body.expense_id is not None:
        get_owned(db, Expense, body.expense_id, auth.organization_id)


def _tag_taken(db: Session, org_id: int, tag: str, asset_id: int | None = None) -> bool:
    stmt = select(Asset.id).where(Asset.organization_id == org_id, Asset.tag == tag)
    return any(found != asset_id for found in db.scalars(stmt))


@router.get("/assets")
def list_assets(
    auth: Reader,
    db: DbSession,
    q: str | None = Query(
        None, description="Tag, name, make, model, serial, place, person, and the extra fields"
    ),
    category_id: int | None = None,
    status_filter: list[AssetStatus] | None = Query(None, alias="status"),
    owner_party_id: int | None = None,
    limit: int = LimitParam,
    offset: int = OffsetParam,
) -> Page[AssetOut]:
    stmt: Any = select(Asset).where(Asset.organization_id == auth.organization_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Asset.tag.ilike(pattern),
                Asset.name.ilike(pattern),
                Asset.manufacturer.ilike(pattern),
                Asset.model.ilike(pattern),
                Asset.serial_number.ilike(pattern),
                Asset.location.ilike(pattern),
                Asset.assigned_to.ilike(pattern),
                cast(Asset.attributes, String).ilike(pattern),
            )
        )
    if category_id is not None:
        stmt = stmt.where(Asset.category_id == category_id)
    if status_filter:
        stmt = stmt.where(Asset.status.in_(status_filter))
    if owner_party_id is not None:
        stmt = stmt.where(Asset.owner_party_id == owner_party_id)
    stmt = stmt.order_by(Asset.tag)
    items, total = paginate(db, stmt, limit, offset)
    return Page(items=assets_out(db, list(items)), total=total, limit=limit, offset=offset)


@router.post("/assets", status_code=status.HTTP_201_CREATED)
def create_asset(body: AssetCreate, auth: Editor, db: DbSession) -> AssetOut:
    _check_refs(db, auth, body)
    org = db.get(Organization, auth.organization_id)
    assert org is not None
    category = db.get(AssetCategory, body.category_id) if body.category_id else None
    try:
        attributes = service.clean_attributes(category, body.attributes)
    except service.AssetError as exc:
        raise _unprocessable(exc) from None
    tag = (body.tag or "").strip()
    if tag and _tag_taken(db, org.id, tag):
        raise conflict(f"The tag {tag} is already used")
    if not tag:
        tag = next_number(db, org.id, "asset")
        while _tag_taken(db, org.id, tag):  # someone used the next number by hand
            tag = next_number(db, org.id, "asset")
    fields = body.model_dump(exclude={"tag", "attributes", "owner_party_id"})
    asset = Asset(
        organization_id=org.id,
        tag=tag,
        owner_party_id=body.owner_party_id or org.self_party_id,
        attributes=attributes or None,
        **fields,
    )
    db.add(asset)
    db.commit()
    return assets_out(db, [asset])[0]


@router.get("/assets/{asset_id}")
def get_asset(asset_id: int, auth: Reader, db: DbSession) -> AssetOut:
    return assets_out(db, [get_owned(db, Asset, asset_id, auth.organization_id)])[0]


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: int, body: AssetPatch, auth: Editor, db: DbSession) -> AssetOut:
    asset = get_owned(db, Asset, asset_id, auth.organization_id)
    _check_refs(db, auth, body)
    changes = body.model_dump(exclude_unset=True)
    for key in ("tag", "name", "status"):
        if key in changes and changes[key] is None:
            del changes[key]
    if "tag" in changes:
        changes["tag"] = changes["tag"].strip()
        if _tag_taken(db, auth.organization_id, changes["tag"], asset.id):
            raise conflict(f"The tag {changes['tag']} is already used")
    category_id = changes.get("category_id", asset.category_id)
    category = db.get(AssetCategory, category_id) if category_id else None
    values = changes.pop("attributes", None)
    try:
        if values is not None:
            asset.attributes = service.clean_attributes(category, values) or None
        elif "category_id" in changes and changes["category_id"] != asset.category_id:
            asset.attributes = service.keep_for(category, asset.attributes) or None
    except service.AssetError as exc:
        raise _unprocessable(exc) from None
    for key, value in changes.items():
        setattr(asset, key, value)
    db.commit()
    db.refresh(asset)
    return assets_out(db, [asset])[0]


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: int, auth: Owner, db: DbSession) -> None:
    """For mistakes; an asset sold or scrapped is marked disposed instead."""
    db.delete(get_owned(db, Asset, asset_id, auth.organization_id))
    db.commit()


@router.post("/assets/{asset_id}/attachments", status_code=status.HTTP_201_CREATED)
async def add_attachment(
    asset_id: int, file: Annotated[UploadFile, File()], auth: Editor, db: DbSession
) -> AssetOut:
    """A receipt, photo or configuration file (any type, at most 20 MB). Viewers cannot open
    them: configurations can hold passwords."""
    asset = get_owned(db, Asset, asset_id, auth.organization_id)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is larger than 20 MB")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty")
    stored = store_file(
        db, auth.organization_id, data, file.filename or "file",
        file.content_type or "application/octet-stream", auth.user.id,
    )  # fmt: skip
    asset.attachments.append(AssetAttachment(file_id=stored.id))
    db.commit()
    db.refresh(asset)
    return assets_out(db, [asset])[0]


@router.delete(
    "/assets/{asset_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_attachment(asset_id: int, attachment_id: int, auth: Editor, db: DbSession) -> None:
    asset = get_owned(db, Asset, asset_id, auth.organization_id)
    attachment = db.get(AssetAttachment, attachment_id)
    if attachment is None or attachment.asset_id != asset.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    db.delete(attachment)
    db.commit()
