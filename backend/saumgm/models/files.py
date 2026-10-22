from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from saumgm.db import TABLE_ARGS, Base, IdMixin
from saumgm.models.base import OrgScopedMixin, fk


class StoredFile(IdMixin, OrgScopedMixin, Base):
    """Metadata of a file held by the storage backend. Records reference the storage key, never a
    filesystem path, so the backend (local disk, S3, Azure Blob) can change by configuration."""

    __tablename__ = "stored_file"
    __table_args__ = TABLE_ARGS

    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("app_user.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
