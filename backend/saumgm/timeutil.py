from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Current time in UTC without tzinfo, which is how timestamps are stored."""
    return datetime.now(UTC).replace(tzinfo=None)


def today() -> date:
    return utcnow().date()


def today_in(timezone: str) -> date:
    """Today's date where the business is (its configured time zone)."""
    return datetime.now(ZoneInfo(timezone)).date()
