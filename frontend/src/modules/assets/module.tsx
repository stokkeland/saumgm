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

import { IconCategory, IconDevices } from '@tabler/icons-react'

import { OwnerOnly } from '../admin/AdminPages'
import type { AppModule } from '../types'
import { AssetPage, AssetsPage, NewAssetPage } from './AssetPages'
import { AssetCategoriesPage } from './CategoriesPage'

export const assetsModule: AppModule = {
  name: 'assets',
  routes: [
    { path: '/assets', element: <AssetsPage /> },
    { path: '/assets/new', element: <NewAssetPage /> },
    { path: '/assets/:id', element: <AssetPage /> },
    { path: '/admin/asset-categories', element: <OwnerOnly><AssetCategoriesPage /></OwnerOnly> },
  ],
  nav: [
    { to: '/assets', label: 'Assets', icon: IconDevices, section: 'operations', order: 10 },
    { to: '/admin/asset-categories', label: 'Asset categories', icon: IconCategory, section: 'admin', order: 25, ownerOnly: true },
  ],
}
