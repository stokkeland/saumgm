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

import type { AppModule } from './types'
import { adminModule } from './admin/module'
import { assetsModule } from './assets/module'
import { bankingModule } from './banking/module'
import { catalogModule } from './catalog/module'
import { contactsModule } from './contacts/module'
import { dashboardModule } from './dashboard/module'
import { depositsModule } from './deposits/module'
import { expensesModule } from './expenses/module'
import { invoicesModule } from './invoices/module'
import { paymentsModule } from './payments/module'
import { remindersModule } from './reminders/module'
import { reportsModule } from './reports/module'
import { subscriptionsModule } from './subscriptions/module'

/** Every module of the app. A new module is a folder with a module.tsx, plus one line here. */
export const MODULES: AppModule[] = [
  dashboardModule,
  remindersModule,
  contactsModule,
  invoicesModule,
  paymentsModule,
  subscriptionsModule,
  catalogModule,
  bankingModule,
  depositsModule,
  expensesModule,
  assetsModule,
  reportsModule,
  adminModule,
]
