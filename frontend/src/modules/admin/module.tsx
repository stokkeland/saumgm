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

import { IconHistory, IconInfoCircle, IconMail, IconSettings, IconUserShield } from '@tabler/icons-react'
import { Navigate } from 'react-router'

import type { AppModule } from '../types'
import { AboutPage, MovedTo, OwnerOnly, UsersPage } from './AdminPages'
import { AuditPage } from './AuditPage'
import { EmailPage } from './EmailPage'
import { SettingsPage } from './SettingsPage'

export const adminModule: AppModule = {
  name: 'admin',
  routes: [
    { path: '/admin', element: <Navigate to="/admin/settings" replace /> },
    { path: '/admin/settings', element: <SettingsPage /> },
    { path: '/admin/users', element: <OwnerOnly><UsersPage /></OwnerOnly> },
    { path: '/admin/email', element: <OwnerOnly><EmailPage /></OwnerOnly> },
    { path: '/admin/audit', element: <OwnerOnly><AuditPage /></OwnerOnly> },
    { path: '/admin/about', element: <AboutPage /> },
    { path: '/settings', element: <MovedTo to="/admin/settings" /> },
    { path: '/audit', element: <MovedTo to="/admin/audit" /> },
  ],
  // Settings stays readable for everyone, as in 1.0 (only the owner can change it).
  nav: [
    { to: '/admin/settings', label: 'Settings', icon: IconSettings, section: 'admin', order: 10 },
    { to: '/admin/users', label: 'Users', icon: IconUserShield, section: 'admin', order: 20, ownerOnly: true },
    { to: '/admin/email', label: 'Email', icon: IconMail, section: 'admin', order: 30, ownerOnly: true },
    { to: '/admin/audit', label: 'Audit log', icon: IconHistory, section: 'admin', order: 40, ownerOnly: true },
    { to: '/admin/about', label: 'About', icon: IconInfoCircle, section: 'admin', order: 90 },
  ],
}
