"""Money arithmetic: always Decimal, rounded half-up to the currency's minor units."""

from decimal import ROUND_HALF_UP, Decimal

# ISO 4217 currencies whose minor unit is not 2 decimals.
_MINOR_UNITS = {
    "BIF": 0, "CLP": 0, "DJF": 0, "GNF": 0, "ISK": 0, "JPY": 0, "KMF": 0, "KRW": 0, "PYG": 0,
    "RWF": 0, "UGX": 0, "UYI": 0, "VND": 0, "VUV": 0, "XAF": 0, "XOF": 0, "XPF": 0,
    "BHD": 3, "IQD": 3, "JOD": 3, "KWD": 3, "LYD": 3, "OMR": 3, "TND": 3,
}  # fmt: skip

ZERO = Decimal(0)
FOUR_PLACES = Decimal("0.0001")


def minor_units(currency: str) -> int:
    return _MINOR_UNITS.get(currency.upper(), 2)


def round_money(amount: Decimal, currency: str) -> Decimal:
    return amount.quantize(Decimal(1).scaleb(-minor_units(currency)), rounding=ROUND_HALF_UP)


def line_total(
    unit_price: Decimal, unit_discount: Decimal, quantity: Decimal, currency: str
) -> Decimal:
    return round_money((unit_price - unit_discount) * quantity, currency)


def discount_amount(unit_price: Decimal, percent: Decimal) -> Decimal:
    """Per-unit discount amount for a percentage, kept at 4 decimals like stored prices."""
    return (unit_price * percent / 100).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
