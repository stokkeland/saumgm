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

/** Reference lists used by forms (cached; they change rarely). */

import { useQuery } from '@tanstack/react-query'

import { api, unwrap } from './client'

const LONG = 5 * 60_000

export function useAccounts() {
  return useQuery({
    queryKey: ['accounts'],
    queryFn: async () => unwrap(await api.GET('/api/accounts')),
    staleTime: LONG,
  })
}

export function useJurisdictions() {
  return useQuery({
    queryKey: ['jurisdictions'],
    queryFn: async () => unwrap(await api.GET('/api/tax/jurisdictions')),
    staleTime: LONG,
  })
}

export function useTaxCategories() {
  return useQuery({
    queryKey: ['tax-categories'],
    queryFn: async () => unwrap(await api.GET('/api/tax/categories')),
    staleTime: LONG,
  })
}

export function useRevenueCategories() {
  return useQuery({
    queryKey: ['revenue-categories'],
    queryFn: async () => unwrap(await api.GET('/api/revenue-categories')),
    staleTime: LONG,
  })
}

export function useOrganization() {
  return useQuery({
    queryKey: ['organization'],
    queryFn: async () => unwrap(await api.GET('/api/settings/organization')),
    staleTime: LONG,
  })
}

/** Select options "Code — Name" for jurisdictions, sorted by code. */
export function jurisdictionOptions(
  rows: { id: number; code: string; name: string }[] | undefined,
) {
  return (rows ?? []).map((j) => ({ value: String(j.id), label: `${j.code} — ${j.name}` }))
}
