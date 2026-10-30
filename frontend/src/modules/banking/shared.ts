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

import type { useQueryClient } from '@tanstack/react-query'

import type { Schemas } from '../../api/client'
import { useAccounts } from '../../api/lookups'

export type BankAccount = Schemas['BankAccountOut']
export type BankEntry = Schemas['BankEntryOut']

export const isCard = (account: { kind: string }) => account.kind === 'credit_card'

/** After any change: balances, registers and the to-do list. */
export function invalidateBanking(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ['bank-accounts'] })
  queryClient.invalidateQueries({ queryKey: ['bank-account'] })
  queryClient.invalidateQueries({ queryKey: ['bank-entries'] })
  queryClient.invalidateQueries({ queryKey: ['bank-reconciliations'] })
  queryClient.invalidateQueries({ queryKey: ['reminders'] })
}

export function useCategoryOptions() {
  const { data: accounts } = useAccounts()
  return (accounts ?? []).filter((a) => a.is_active).map((a) => ({ value: String(a.id), label: `${a.code} ${a.name}` }))
}

