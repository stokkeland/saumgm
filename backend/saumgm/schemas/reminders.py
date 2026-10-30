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

from datetime import date, datetime

from pydantic import BaseModel, Field

from saumgm.schemas.types import Amount


class ReminderItem(BaseModel):
    title: str
    date: date | None
    # A path in the app (/invoices/12); the digest puts APP_URL in front of it.
    link: str
    amount: Amount | None
    note: str | None
    flag: str | None = Field(description="overdue, autopay, expired or expiring")


class ReminderSection(BaseModel):
    key: str = Field(description="bill, pay, collect, documents")
    title: str
    summary: str
    link: str
    action_label: str | None
    action_link: str | None
    items: list[ReminderItem]


class RemindersOut(BaseModel):
    today: date
    last_sign_in: datetime | None
    idle_days: int | None = Field(description="Whole days since anyone signed in")
    # The digest's opening, e.g. "3 client subscriptions are due for billing within 14 days."
    summary: str
    count: int
    sections: list[ReminderSection]


class ReminderSettingsOut(BaseModel):
    bill_days: int
    pay_days: int
    # Who gets the digest; empty means the owners (listed in `owners`).
    recipients: list[str]
    owners: list[str]
    # APP_URL from the server's .env, for links in the digest.
    app_url: str | None


class ReminderSettingsPatch(BaseModel):
    bill_days: int | None = Field(None, ge=0, le=365)
    pay_days: int | None = Field(None, ge=0, le=365)
    recipients: list[str] | None = None
