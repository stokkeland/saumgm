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

import { Badge, Button, Group, Select, Stack, Text } from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DataTable } from '../../components/DataTable'
import {
  ArchivedBadge,
  ArchiveFilter,
  PageHeader,
  SearchInput,
  type ArchiveFilterValue,
} from '../../components/ui'
import { ROLE_COLORS, ROLE_LABELS } from '../../lib/labels'
import { useUrlState } from '../../lib/useUrlState'
import { ContactForm } from './ContactForm'

type Row = Schemas['PartySummary']
const LIMIT = 50
const DEFAULTS = { q: '', role: '', active: '', archived: 'current', offset: '0' }

export function RoleBadges({ roles }: { roles: string[] }) {
  return (
    <Group gap={4}>
      {roles.map((r) => (
        <Badge key={r} size="sm" variant="light" color={ROLE_COLORS[r]}>
          {ROLE_LABELS[r] ?? r}
        </Badge>
      ))}
    </Group>
  )
}

export function ContactsPage() {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const [creating, setCreating] = useState(false)
  const [f, setF] = useUrlState(DEFAULTS)

  const { data, isFetching } = useQuery({
    queryKey: ['contacts', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/contacts', {
          params: {
            query: {
              q: f.q || undefined,
              role: (f.role || undefined) as Row['roles'][number] | undefined,
              active: f.active === '' ? undefined : f.active === 'true',
              archived: f.archived as ArchiveFilterValue,
              limit: LIMIT,
              offset: Number(f.offset),
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })

  return (
    <>
      <PageHeader
        title="Contacts"
        subtitle="Clients, vendors, banks and everyone else"
        actions={
          canEdit && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setCreating(true)}>
              New contact
            </Button>
          )
        }
      />
      <Group mb="sm" gap="sm" wrap="wrap">
        <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Name, code, number, email" />
        <Select
          placeholder="All roles"
          clearable
          w={170}
          value={f.role || null}
          onChange={(role) => setF({ role: role ?? '' })}
          data={Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))}
        />
        <Select
          w={130}
          value={f.active}
          onChange={(active) => setF({ active: active ?? '' })}
          data={[
            { value: '', label: 'Any status' },
            { value: 'true', label: 'Active' },
            { value: 'false', label: 'Inactive' },
          ]}
        />
        <ArchiveFilter value={f.archived as ArchiveFilterValue} onChange={(archived) => setF({ archived })} />
      </Group>
      <DataTable<Row>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/contacts/${r.id}`)}
        empty="No contacts match"
        page={
          data && {
            total: data.total,
            limit: LIMIT,
            offset: Number(f.offset),
            onOffset: (offset) => setF({ offset: String(offset) }),
          }
        }
        columns={[
          { key: 'no', header: 'No.', render: (r) => <Text size="sm" ff="monospace">{r.party_no}</Text>, wide: true },
          { key: 'code', header: 'Code', render: (r) => r.short_code },
          {
            key: 'name',
            header: 'Name',
            render: (r) => (
              <Stack gap={0}>
                <Group gap={6}>
                  <Text fw={500} size="sm">
                    {r.name}
                  </Text>
                  {!r.is_active && (
                    <Badge size="xs" color="gray">
                      Inactive
                    </Badge>
                  )}
                  <ArchivedBadge at={r.archived_at} />
                </Group>
                {r.email && (
                  <Text size="xs" c="dimmed">
                    {r.email}
                  </Text>
                )}
              </Stack>
            ),
          },
          { key: 'roles', header: 'Roles', render: (r) => <RoleBadges roles={r.roles} /> },
          {
            key: 'place',
            header: 'Location',
            wide: true,
            render: (r) => [r.city, r.region].filter(Boolean).join(', '),
          },
          { key: 'phone', header: 'Phone', wide: true, render: (r) => r.phone },
        ]}
      />
      {creating && (
        <ContactForm
          onClose={() => setCreating(false)}
          onSaved={(saved) => navigate(`/contacts/${saved.id}`)}
        />
      )}
    </>
  )
}
