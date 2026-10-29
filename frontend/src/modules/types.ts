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

import type { Icon } from '@tabler/icons-react'
import type { RouteObject } from 'react-router'

/** Where a menu entry goes. The shell decides the order and labels of the sections. */
export type NavSection = 'home' | 'sales' | 'money' | 'operations' | 'reports' | 'admin'

export interface NavItem {
  to: string
  label: string
  icon: Icon
  section: NavSection
  /** Position within the section (lower first). */
  order: number
  ownerOnly?: boolean
}

/** One area of the app: its pages and menu entries. Listed in modules/index.ts. */
export interface AppModule {
  name: string
  routes: RouteObject[]
  nav: NavItem[]
}
