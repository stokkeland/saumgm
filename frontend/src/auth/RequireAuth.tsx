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
