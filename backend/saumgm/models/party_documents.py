from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from saumgm.db import TABLE_ARGS, Base, IdMixin, TimestampMixin
from saumgm.enums import DocumentType
from saumgm.models.base import ArchivableMixin, OrgScopedMixin, fk, str_enum

if TYPE_CHECKING:
    from saumgm.models.files import StoredFile


class PartyDocument(IdMixin, OrgScopedMixin, ArchivableMixin, TimestampMixin, Base):
    """A document kept on file for a contact (W-9, exemption certificate, insurance, contract...).

    The file is optional, so a paper copy can be recorded too. Archived = superseded by a newer
    document; kept for the record but no longer checked for expiry.
    """

    __tablename__ = "party_document"
    __table_args__ = TABLE_ARGS

    party_id: Mapped[int] = mapped_column(
        BigInteger, fk("party.id", ondelete="CASCADE"), index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(str_enum(DocumentType), index=True)
    title: Mapped[str] = mapped_column(String(200))
    file_id: Mapped[int | None] = mapped_column(BigInteger, fk("stored_file.id"), index=True)
    # The tax exemption this certificate supports (the exemption is what the tax engine uses).
    tax_exemption_id: Mapped[int | None] = mapped_column(
        BigInteger, fk("tax_exemption.id", ondelete="SET NULL"), index=True
    )
    document_date: Mapped[date | None] = mapped_column(Date)  # signed / issued
    expires_on: Mapped[date | None] = mapped_column(Date, index=True)
    # How many days before expiry it counts as "expiring" (and, later, when reminders go out).
    remind_days_before: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    file: Mapped["StoredFile | None"] = relationship(lazy="joined")
