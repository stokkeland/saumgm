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

"""File storage behind a small interface (docs/design.md 4.10).

Records keep only a storage key (`{org}/{yyyy}/{mm}/{uuid}.{ext}`), never a path, so the backend can
be swapped by configuration: `file://` now; S3-compatible or Azure Blob storage later.
"""

import hashlib
import mimetypes
import uuid
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session

from saumgm.config import get_settings
from saumgm.models import StoredFile
from saumgm.timeutil import utcnow

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class LocalStorage:
    """Files in a local directory (one server; back it up with the database)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"invalid storage key {key!r}")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


def storage_from_url(url: str) -> Storage:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        # file:///C:/data/files (Windows) or file:///var/lib/saumgm/files (Linux)
        raw = unquote(parsed.path)
        if len(raw) > 2 and raw[0] == "/" and raw[2] == ":":
            raw = raw[1:]
        return LocalStorage(Path(raw))
    raise ValueError(f"Unsupported STORAGE_URL scheme {parsed.scheme!r} (supported: file://)")


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = storage_from_url(get_settings().storage_url)
    return _storage


def set_storage(storage: Storage | None) -> None:
    """Replace the storage backend (tests)."""
    global _storage
    _storage = storage


def store_file(
    session: Session,
    organization_id: int,
    data: bytes,
    original_name: str,
    content_type: str | None = None,
    uploaded_by_user_id: int | None = None,
) -> StoredFile:
    content_type = (
        content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    )
    extension = Path(original_name).suffix.lower()[:10]
    now = utcnow()
    key = f"{organization_id}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"
    get_storage().put(key, data, content_type)
    stored = StoredFile(
        organization_id=organization_id,
        storage_key=key,
        original_name=original_name[:255],
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_by_user_id=uploaded_by_user_id,
    )
    session.add(stored)
    session.flush()
    return stored


def read_file(stored: StoredFile) -> bytes:
    return get_storage().get(stored.storage_key)
