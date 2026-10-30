/*
 * SauMGM - Sauen Management System: billing, sales tax and bookkeeping for small businesses
 * Copyright (C) 2026 J. Thomas Stokkeland - https://www.saumgm.com/
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU General Public License as published by the Free Software Foundation, either version 3 of
 * the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
 * without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU General Public License for more details. You should have received a copy of the
 * GNU General Public License along with this program (the LICENSE file); if not, see
 * <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

import { IconCalendarRepeat, IconRepeat } from '@tabler/icons-react'

import type { AppModule } from '../types'
import { SubscriptionsPage } from './SubscriptionsPage'
import { VendorSubscriptionsPage } from './VendorSubscriptionsPage'

export const subscriptionsModule: AppModule = {
  name: 'subscriptions',
  routes: [
    { path: '/subscriptions', element: <SubscriptionsPage /> },
    { path: '/vendor-subscriptions', element: <VendorSubscriptionsPage /> },
  ],
  nav: [
    { to: '/subscriptions', label: 'Subscriptions', icon: IconCalendarRepeat, section: 'sales', order: 40 },
    { to: '/vendor-subscriptions', label: 'Vendor subscriptions', icon: IconRepeat, section: 'money', order: 40 },
  ],
}
