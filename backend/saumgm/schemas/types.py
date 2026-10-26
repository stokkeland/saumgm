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
