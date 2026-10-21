"""Small, pure conversions from Access values to SauMGM values."""

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from saumgm.models.enums import ItemType, PaymentChannel, PaymentMethod
from saumgm.seed import CA_PROVINCES, US_STATES

FOUR_PLACES = Decimal("0.0001")


def dec(value: Any) -> Decimal | None:
    """Access CURRENCY arrives as Decimal; DOUBLE/SINGLE as float (0.95 as 0.949999988...).
    Normalize everything to 4 decimal places."""
    if value is None:
        return None
    if isinstance(value, float):
        value = repr(value)
    return Decimal(value).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def dec0(value: Any) -> Decimal:
    return dec(value) or Decimal("0.0000")


def to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"not a date: {value!r}")


def int_date(value: Any) -> date | None:
    """Some tables store dates as integers like 20040808; 0 means none."""
    if not value:
        return None
    try:
        text = str(int(value))
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except (ValueError, IndexError):
        return None


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def pad_file_no(value: Any) -> str | None:
    """File numbers are 8 digits; a few entries lost their leading zeros (10068 -> 00010068)."""
    text = clean(value)
    if text is None:
        return None
    return text.zfill(8) if text.isdigit() else text


_DAYS = re.compile(r"(\d+)\s*days?", re.IGNORECASE)
_DUE_ON_RECEIPT = {"cash", "cod", "dop", "due on receipt"}


def parse_terms(text: str | None) -> int | None:
    """'Net per 30 days' -> 30, '20 Days' -> 20, 'Cash' -> 0; free-form terms -> None."""
    if not text:
        return None
    match = _DAYS.search(text)
    if match:
        return int(match.group(1))
    if text.strip().lower() in _DUE_ON_RECEIPT:
        return 0
    return None


def country_code(country: Any, region: Any) -> str | None:
    name = (clean(country) or "").lower()
    if name in {"usa", "us", "united states", "u.s.a."}:
        return "US"
    if name in {"canada", "ca"}:
        return "CA"
    if name:
        return None
    state = (clean(region) or "").upper()
    if state in US_STATES:
        return "US"
    if state in CA_PROVINCES:
        return "CA"
    return None


def guess_item_type(unit: str | None, recurrable: bool) -> ItemType:
    """Best guess from the old product data; reviewed by the user after import."""
    if recurrable:
        return ItemType.SUBSCRIPTION
    normalized = (unit or "").strip().lower()
    if normalized in {"hour", "hours", "hr", "hrs"}:
        return ItemType.SERVICE_HOURLY
    if not normalized:
        return ItemType.SERVICE_FIXED
    return ItemType.GOODS


def billing_interval(unit: str | None, recurrable: bool, period: int | None) -> int | None:
    if not recurrable:
        return None
    normalized = (unit or "").strip().lower()
    if normalized in {"year", "yr"}:
        return 12
    if period in (1, 3, 6, 12):
        return period
    return None


def discount_pct(multiplier: Any) -> Decimal:
    """Old products store a price multiplier (1 = full price, 0.95 = 5% off)."""
    value = dec(multiplier)
    if value is None:
        return Decimal("0.0000")
    return ((Decimal(1) - value) * 100).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


CHANNELS = {
    "postal mail": PaymentChannel.MAIL,
    "personally delivered": PaymentChannel.IN_PERSON,
    "electronic transfer": PaymentChannel.ELECTRONIC,
}

METHODS = {
    "check": PaymentMethod.CHECK,
    "cash": PaymentMethod.CASH,
    "moneyorder": PaymentMethod.MONEY_ORDER,
    "paypal": PaymentMethod.PAYPAL,
    "credit card": PaymentMethod.CARD,
    "electronic": PaymentMethod.BANK_TRANSFER,
}

_CHECK_NO = re.compile(r"check\s*(?:#|no\.?|number)?\s*([0-9][0-9-]+)", re.IGNORECASE)


def check_number(text: str | None) -> str | None:
    if not text:
        return None
    match = _CHECK_NO.search(text)
    return match.group(1) if match else None


def line_total(price: Decimal, discount: Decimal, quantity: Decimal) -> Decimal:
    return ((price - discount) * quantity).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def jsonable(value: Any) -> Any:
    """Values for legacy_data JSON columns."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value
