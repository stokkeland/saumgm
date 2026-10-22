from datetime import date
from decimal import Decimal

import pytest

from saumgm.enums import ItemType
from saumgm.legacy_import import convert as cv


def test_dec_normalizes_floats_and_currency() -> None:
    assert cv.dec(0.949999988079071) == Decimal("0.9500")
    assert cv.dec(Decimal("8088.625")) == Decimal("8088.6250")
    assert cv.dec(None) is None
    assert cv.dec0(None) == Decimal("0")


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ("Net per 30 days", 30),
        ("20 Days", 20),
        ("Net per 120 days", 120),
        ("Cash", 0),
        ("DOP", 0),
        ("50/50 Start/Completion", None),
        ("Half / Half COD", None),
        (None, None),
    ],
)
def test_parse_terms(text: str | None, days: int | None) -> None:
    assert cv.parse_terms(text) == days


def test_dates() -> None:
    assert cv.int_date(20040808) == date(2004, 8, 8)
    assert cv.int_date(0) is None
    assert cv.int_date(123) is None


def test_file_numbers_are_padded() -> None:
    assert cv.pad_file_no("10068") == "00010068"
    assert cv.pad_file_no(" 00010000 ") == "00010000"
    assert cv.pad_file_no("") is None


@pytest.mark.parametrize(
    ("country", "region", "code"),
    [("USA", "NY", "US"), ("Canada", "ON", "CA"), (None, "NY", "US"), ("", "ON", "CA"),
     (None, None, None), ("Norway", None, None)],
)  # fmt: skip
def test_country_code(country: str | None, region: str | None, code: str | None) -> None:
    assert cv.country_code(country, region) == code


def test_catalog_guesses() -> None:
    assert cv.guess_item_type("Month", True) == ItemType.SUBSCRIPTION
    assert cv.guess_item_type("Hour", False) == ItemType.SERVICE_HOURLY
    assert cv.guess_item_type(None, False) == ItemType.SERVICE_FIXED
    assert cv.guess_item_type("ea", False) == ItemType.GOODS
    assert cv.billing_interval("Year", True, 1) == 12
    assert cv.billing_interval("Month", True, 6) == 6
    assert cv.billing_interval("Month", False, 12) is None
    assert cv.discount_pct(0.949999988079071) == Decimal("5.0000")
    assert cv.discount_pct(1) == Decimal("0")


def test_check_number_and_line_total() -> None:
    assert cv.check_number("Check #3364") == "3364"
    assert cv.check_number("Received Check 12345678 (J. Doe)") == "12345678"
    assert cv.check_number("Cash") is None
    assert cv.line_total(Decimal("150"), Decimal("97.5"), Decimal("10.25")) == Decimal("538.125")
