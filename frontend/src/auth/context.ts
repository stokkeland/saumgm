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

import { useQuery } from '@tanstack/react-query'
import { createContext, useContext } from 'react'

import { api, ApiError, unwrap, type Schemas } from '../api/client'
import type { Locale } from '../lib/format'

export type Me = Schemas['Me']
export type Role = Me['role']

export interface AuthContextValue {
  me: Me
  locale: Locale
  /** May change data (owner or bookkeeper). */
  canEdit: boolean
  isOwner: boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export const ME_KEY = ['auth', 'me']

export function useMeQuery() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return unwrap(await api.GET('/api/auth/me'))
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
    staleTime: 5 * 60_000,
  })
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth outside of <RequireAuth>')
  return value
}
