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

"""Business settings and user management (owner only for changes)."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from saumgm.api.common import apply_changes, conflict, get_owned, not_found
from saumgm.api.deps import DbSession, Owner, Reader
from saumgm.enums import UserRoleType
from saumgm.models import NumberSequence, Organization, OrganizationAddress, User, UserRole
from saumgm.schemas.settings import (
    OrgAddressIn,
    OrgAddressOut,
    OrgAddressPatch,
    OrganizationOut,
    OrganizationPatch,
    PasswordReset,
    SequenceOut,
    SequencePatch,
    UserCreate,
    UserListItem,
    UserPatch,
)
from saumgm.services import auth as auth_service

router = APIRouter(tags=["settings"])


def _org(db: DbSession, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise not_found("Organization")
    return org


@router.get("/settings/organization")
def get_organization(auth: Reader, db: DbSession) -> OrganizationOut:
    return OrganizationOut.model_validate(_org(db, auth.organization_id))


@router.patch("/settings/organization")
def update_organization(body: OrganizationPatch, auth: Owner, db: DbSession) -> OrganizationOut:
    org = _org(db, auth.organization_id)
    apply_changes(org, body)
    db.commit()
    return OrganizationOut.model_validate(org)


# -- business addresses ---------------------------------------------------------------------------


@router.get("/settings/addresses")
def list_org_addresses(auth: Reader, db: DbSession) -> list[OrgAddressOut]:
    rows = db.scalars(
        select(OrganizationAddress)
        .where(OrganizationAddress.organization_id == auth.organization_id)
        .order_by(OrganizationAddress.id)
    )
    return [OrgAddressOut.model_validate(a) for a in rows]


@router.post("/settings/addresses", status_code=status.HTTP_201_CREATED)
def add_org_address(body: OrgAddressIn, auth: Owner, db: DbSession) -> OrgAddressOut:
    address = OrganizationAddress(organization_id=auth.organization_id, **body.model_dump())
    db.add(address)
    db.flush()
    db.commit()
    return OrgAddressOut.model_validate(address)


@router.patch("/settings/addresses/{address_id}")
def update_org_address(
    address_id: int, body: OrgAddressPatch, auth: Owner, db: DbSession
) -> OrgAddressOut:
    address = get_owned(db, OrganizationAddress, address_id, auth.organization_id)
    apply_changes(address, body)
    db.commit()
    return OrgAddressOut.model_validate(address)


@router.delete("/settings/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_org_address(address_id: int, auth: Owner, db: DbSession) -> None:
    db.delete(get_owned(db, OrganizationAddress, address_id, auth.organization_id))
    db.commit()


# -- numbering ------------------------------------------------------------------------------------


@router.get("/settings/numbering")
def list_sequences(auth: Reader, db: DbSession) -> list[SequenceOut]:
    rows = db.scalars(
        select(NumberSequence)
        .where(NumberSequence.organization_id == auth.organization_id)
        .order_by(NumberSequence.name)
    )
    return [SequenceOut.model_validate(s) for s in rows]


@router.patch("/settings/numbering/{name}")
def update_sequence(name: str, body: SequencePatch, auth: Owner, db: DbSession) -> SequenceOut:
    seq = db.scalars(
        select(NumberSequence).where(
            NumberSequence.organization_id == auth.organization_id, NumberSequence.name == name
        )
    ).one_or_none()
    if seq is None:
        raise not_found("Number sequence")
    apply_changes(seq, body)
    db.commit()
    return SequenceOut.model_validate(seq)


# -- users ----------------------------------------------------------------------------------------


def _user_item(user: User, org_id: int) -> UserListItem:
    roles = [r.role for r in user.roles if r.organization_id == org_id]
    return UserListItem(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        role=max(roles, key=lambda r: auth_service.ROLE_RANK[r]),
        last_login_at=user.last_login_at,
    )


def _member(db: DbSession, user_id: int, org_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or not any(r.organization_id == org_id for r in user.roles):
        raise not_found("User")
    return user


@router.get("/users")
def list_users(auth: Owner, db: DbSession) -> list[UserListItem]:
    users = db.scalars(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.organization_id == auth.organization_id)
        .order_by(User.display_name)
        .distinct()
    )
    return [_user_item(u, auth.organization_id) for u in users]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, auth: Owner, db: DbSession) -> UserListItem:
    try:
        user = auth_service.create_user(
            db, auth.organization_id, body.email, body.display_name, body.role, body.password
        )
    except auth_service.PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    db.commit()
    return _user_item(user, auth.organization_id)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, auth: Owner, db: DbSession) -> UserListItem:
    user = _member(db, user_id, auth.organization_id)
    if user.id == auth.user.id and (
        body.is_active is False or (body.role is not None and body.role != UserRoleType.OWNER)
    ):
        raise conflict("You cannot deactivate yourself or give up your own owner role.")
    apply_changes(user, body, exclude={"role"})
    if body.role is not None:
        for role in user.roles:
            if role.organization_id == auth.organization_id:
                role.role = body.role
    if body.is_active is False:
        auth_service.end_all_sessions(db, user.id)
    db.commit()
    return _user_item(user, auth.organization_id)


@router.post("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(user_id: int, body: PasswordReset, auth: Owner, db: DbSession) -> None:
    user = _member(db, user_id, auth.organization_id)
    try:
        auth_service.set_password(db, user, body.new_password)
    except auth_service.PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    auth_service.end_all_sessions(db, user.id)
    db.commit()
