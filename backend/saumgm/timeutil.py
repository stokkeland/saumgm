from datetime import UTC, date, datetime


def utcnow() -> datetime:
    """Current time in UTC without tzinfo, which is how timestamps are stored."""
    return datetime.now(UTC).replace(tzinfo=None)


def today() -> date:
    return utcnow().date()
