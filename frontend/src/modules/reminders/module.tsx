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

import { IconBell, IconChecklist } from '@tabler/icons-react'

import { OwnerOnly } from '../admin/AdminPages'
import type { AppModule } from '../types'
import { ReminderSettingsPage } from './ReminderSettingsPage'
import { ToDoPage } from './ToDoPage'

export const remindersModule: AppModule = {
  name: 'reminders',
  routes: [
    { path: '/todo', element: <ToDoPage /> },
    { path: '/admin/reminders', element: <OwnerOnly><ReminderSettingsPage /></OwnerOnly> },
  ],
  nav: [
    { to: '/todo', label: 'To do', icon: IconChecklist, section: 'home', order: 10 },
    { to: '/admin/reminders', label: 'Reminders', icon: IconBell, section: 'admin', order: 35, ownerOnly: true },
  ],
}
