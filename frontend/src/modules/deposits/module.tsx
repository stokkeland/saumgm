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

import { IconBuildingBank } from '@tabler/icons-react'

import type { AppModule } from '../types'
import { DepositPage, DepositsPage, NewDepositPage } from './DepositPages'

export const depositsModule: AppModule = {
  name: 'deposits',
  routes: [
    { path: '/deposits', element: <DepositsPage /> },
    { path: '/deposits/new', element: <NewDepositPage /> },
    { path: '/deposits/:id', element: <DepositPage /> },
  ],
  nav: [{ to: '/deposits', label: 'Deposits', icon: IconBuildingBank, section: 'money', order: 20 }],
}
