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

"""Assets: the extra fields a category defines, and what needs attention (warranties and
support contracts ending)."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from saumgm.enums import AssetFieldType, AssetStatus
from saumgm.models import Asset, AssetCategory

# Assets still around: retired and disposed ones are not checked for warranties.
ACTIVE = (AssetStatus.IN_USE, AssetStatus.IN_STOCK, AssetStatus.IN_REPAIR)
MAX_TEXT = 500


class AssetError(ValueError):
    """An extra field value that does not fit its category."""


def check_fields(fields: list[dict[str, Any]]) -> None:
    keys = [f["key"] for f in fields]
    if len(keys) != len(set(keys)):
        raise AssetError("Two extra fields have the same key")


def _value(field: dict[str, Any], value: Any) -> Any:
    label, kind = field["label"], AssetFieldType(field["type"])
    if value is None or value == "":
        return None
    if kind == AssetFieldType.BOOL:
        if not isinstance(value, bool):
            raise AssetError(f"{label}: yes or no")
        return value
    if kind == AssetFieldType.NUMBER:
        if isinstance(value, bool):
            raise AssetError(f"{label}: a number")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise AssetError(f"{label}: a number") from None
        return int(number) if number.is_integer() else number
    if kind == AssetFieldType.DATE:
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise AssetError(f"{label}: a date (YYYY-MM-DD)") from None
    text = str(value).strip()
    if len(text) > MAX_TEXT:
        raise AssetError(f"{label}: at most {MAX_TEXT} characters")
    return text or None


def clean_attributes(category: AssetCategory | None, values: dict[str, Any]) -> dict[str, Any]:
    """The values checked against the category's fields; empty ones are left out."""
    fields = {f["key"]: f for f in (category.fields if category else [])}
    unknown = sorted(set(values) - set(fields))
    if unknown:
        where = f"the category {category.name}" if category else "an asset without a category"
        raise AssetError(f"Not a field of {where}: {', '.join(unknown)}")
    cleaned = {key: _value(fields[key], value) for key, value in values.items()}
    return {k: v for k, v in cleaned.items() if v is not None}


def keep_for(category: AssetCategory | None, values: dict[str, Any] | None) -> dict[str, Any]:
    """When the category changes: the values of fields the new category also has."""
    keys = {f["key"] for f in (category.fields if category else [])}
    return {k: v for k, v in (values or {}).items() if k in keys}


def ending(session: Session, org_id: int, today: date, days: int) -> list[tuple[Asset, str, date]]:
    """(asset, "warranty" or "support", date) for active assets whose warranty or support
    contract ends within `days`, or ended within the last `days`."""
    start, end = today - timedelta(days=days), today + timedelta(days=days)
    assets = session.scalars(
        select(Asset).where(
            Asset.organization_id == org_id,
            Asset.status.in_(ACTIVE),
            or_(
                Asset.warranty_expires.between(start, end),
                Asset.support_ends.between(start, end),
            ),
        )
    ).all()
    out = []
    for asset in assets:
        for what, day in (("warranty", asset.warranty_expires), ("support", asset.support_ends)):
            if day is not None and start <= day <= end:
                out.append((asset, what, day))
    return sorted(out, key=lambda row: (row[2], row[0].tag))
