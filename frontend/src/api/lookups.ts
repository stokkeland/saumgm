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
