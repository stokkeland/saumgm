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

"""Import settings: business details that are not stored in the Access database."""

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from saumgm.enums import AddressType
from saumgm.seed import OrganizationSetup


@dataclass
class AddressConfig:
    address_type: AddressType
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    phone: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass
class ImportConfig:
    organization: OrganizationSetup
    self_party_no: str
    addresses: list[AddressConfig] = field(default_factory=list)
    # Archive records dated on or before this day right after the import.
    archive_through: date | None = None
    # Image file to use as the business logo (relative to the config file).
    logo: Path | None = None


def load_config(path: Path) -> ImportConfig:
    with path.open("rb") as fh:
        raw: dict[str, Any] = tomllib.load(fh)
    org = dict(raw["organization"])
    self_party_no = str(org.pop("self_party_no"))
    logo = org.pop("logo", None)
    addresses = [
        AddressConfig(**{**addr, "address_type": AddressType(addr["address_type"])})
        for addr in org.pop("addresses", [])
    ]
    return ImportConfig(
        organization=OrganizationSetup(**org),
        self_party_no=self_party_no,
        addresses=addresses,
        archive_through=raw.get("import", {}).get("archive_through"),
        logo=(path.parent / logo) if logo else None,
    )
