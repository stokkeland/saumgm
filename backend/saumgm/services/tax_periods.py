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

"""Sales-tax filing periods of a registration.

A registration files monthly, quarterly or annually, with a filing year that starts in
`period_start_month` (1 = calendar quarters/years; New York uses March: quarters Mar-May,
Jun-Aug, Sep-Nov, Dec-Feb, and an annual period March to February).
"""

from collections.abc import Iterator
from datetime import date, timedelta

from saumgm.enums import FilingFrequency
from saumgm.models import TaxRegistration
from saumgm.services.subscriptions import add_months

MONTHS = {FilingFrequency.MONTHLY: 1, FilingFrequency.QUARTERLY: 3, FilingFrequency.ANNUAL: 12}


def period_months(registration: TaxRegistration) -> int:
    return MONTHS[registration.filing_frequency or FilingFrequency.ANNUAL]


def period_containing(registration: TaxRegistration, day: date) -> tuple[date, date]:
    """The filing period that includes `day`."""
    length = period_months(registration)
    anchor = registration.period_start_month
    months_since_anchor = (day.month - anchor) % 12
    start_month_index = day.year * 12 + day.month - 1 - months_since_anchor % length
    start = date(start_month_index // 12, start_month_index % 12 + 1, 1)
    return start, add_months(start, length) - timedelta(days=1)


def periods_between(
    registration: TaxRegistration, start: date, end: date
) -> Iterator[tuple[date, date]]:
    """Every filing period overlapping [start, end], oldest first."""
    period_start, period_end = period_containing(registration, start)
    while period_start <= end:
        yield period_start, period_end
        period_start = period_end + timedelta(days=1)
        period_end = add_months(period_start, period_months(registration)) - timedelta(days=1)


def is_period_start(registration: TaxRegistration, day: date) -> bool:
    return period_containing(registration, day)[0] == day
