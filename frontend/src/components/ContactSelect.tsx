import { Select, type SelectProps } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap, type Schemas } from '../api/client'

type Role = Schemas['PartySummary']['roles'][number]

/** Pick a contact by typing part of its name, code or number (searches the server). */
export function ContactSelect({
  value,
  onChange,
  role,
  ...props
}: Omit<SelectProps, 'value' | 'onChange' | 'data'> & {
  value: number | null
  onChange: (id: number | null) => void
  role?: Role
}) {
  const [search, setSearch] = useState('')
  const [q] = useDebouncedValue(search, 250)

  const { data: options } = useQuery({
    queryKey: ['contact-options', role, q],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/contacts', {
          params: { query: { q: q || undefined, role, active: true, limit: 25 } },
        }),
      ).items,
    placeholderData: keepPreviousData,
  })
  const { data: selected } = useQuery({
    queryKey: ['contact', value],
    queryFn: async () =>
      unwrap(await api.GET('/api/contacts/{party_id}', { params: { path: { party_id: value! } } })),
    enabled: value !== null,
  })

  const rows = [...(options ?? [])]
  if (selected && !rows.some((r) => r.id === selected.id)) rows.unshift(selected)

  return (
    <Select
      searchable
      clearable
      nothingFoundMessage="No matching contacts"
      filter={({ options: all }) => all}
      searchValue={search}
      onSearchChange={setSearch}
      value={value === null ? null : String(value)}
      onChange={(v) => onChange(v ? Number(v) : null)}
      data={rows.map((r) => ({ value: String(r.id), label: `${r.name} (${r.short_code})` }))}
      {...props}
    />
  )
}
