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
