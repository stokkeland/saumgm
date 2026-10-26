"""Documents kept on file for contacts: expiry status, and what is expiring across the business."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from saumgm.enums import DocumentStatus
from saumgm.models import PartyDocument

# Used when a document has an expiry date but no reminder window of its own.
DEFAULT_REMIND_DAYS = 30


def remind_days(doc: PartyDocument) -> int:
    return doc.remind_days_before if doc.remind_days_before is not None else DEFAULT_REMIND_DAYS


def status(doc: PartyDocument, today: date) -> DocumentStatus:
    if doc.expires_on is None:
        return DocumentStatus.NO_EXPIRY
    if doc.expires_on < today:
        return DocumentStatus.EXPIRED
    if doc.expires_on <= today + timedelta(days=remind_days(doc)):
        return DocumentStatus.EXPIRING
    return DocumentStatus.VALID


def needing_attention(
    session: Session, organization_id: int, today: date, within_days: int | None = None
) -> list[PartyDocument]:
    """Current (not superseded) documents that have expired or are inside their reminder window.

    With `within_days`, the window is that many days for every document instead.
    """
    widest = within_days if within_days is not None else 3650
    candidates = session.scalars(
        select(PartyDocument)
        .where(
            PartyDocument.organization_id == organization_id,
            PartyDocument.archived_at.is_(None),
            PartyDocument.expires_on.is_not(None),
            PartyDocument.expires_on <= today + timedelta(days=widest),
        )
        .order_by(PartyDocument.expires_on, PartyDocument.id)
    )
    if within_days is not None:
        return list(candidates)
    return [d for d in candidates if status(d, today) != DocumentStatus.VALID]
