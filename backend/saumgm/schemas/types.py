"""Decimal types with a fixed JSON format, so amounts look the same whether they were just
calculated or read back from the database ("12.5000", never "12.5" or "12.50")."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import PlainSerializer


def _fixed(places: int) -> PlainSerializer:
    exponent = Decimal(1).scaleb(-places)

    def serialize(value: Decimal) -> str:
        return format(value.quantize(exponent, rounding=ROUND_HALF_UP), "f")

    return PlainSerializer(serialize, return_type=str, when_used="json")


# Money, quantities and percentages: 4 decimals, like the database columns.
Amount = Annotated[Decimal, _fixed(4)]
# Tax rates as fractions (0.04 = 4%): 6 decimals.
RateValue = Annotated[Decimal, _fixed(6)]
