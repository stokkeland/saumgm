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

import { Center, Loader } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { onSessionExpired } from '../api/client'
import { AuthContext, ME_KEY, useMeQuery, type AuthContextValue } from './context'

/** Renders its children only for a logged-in user; otherwise goes to the login page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { data: me, isPending } = useMeQuery()
  const queryClient = useQueryClient()
  const location = useLocation()

  useEffect(
    () =>
      onSessionExpired(() => {
        queryClient.setQueryData(ME_KEY, null)
      }),
    [queryClient],
  )

  if (isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  }
  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  const value: AuthContextValue = {
    me,
    locale: { locale: me.organization.locale, currency: me.organization.currency_code },
    canEdit: me.role !== 'viewer',
    isOwner: me.role === 'owner',
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
