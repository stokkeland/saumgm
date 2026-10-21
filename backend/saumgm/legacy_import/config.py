"""Import settings: business details that are not stored in the Access database."""

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from saumgm.models.enums import AddressType
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


def load_config(path: Path) -> ImportConfig:
    with path.open("rb") as fh:
        raw: dict[str, Any] = tomllib.load(fh)
    org = dict(raw["organization"])
    self_party_no = str(org.pop("self_party_no"))
    addresses = [
        AddressConfig(**{**addr, "address_type": AddressType(addr["address_type"])})
        for addr in org.pop("addresses", [])
    ]
    return ImportConfig(
        organization=OrganizationSetup(**org),
        self_party_no=self_party_no,
        addresses=addresses,
    )
