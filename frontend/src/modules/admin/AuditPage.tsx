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

import { Badge, Button, Code, Group, Select, Text, TextInput } from '@mantine/core'
import { IconDownload } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DataTable } from '../../components/DataTable'
import { PageHeader } from '../../components/ui'
import { formatDateTime } from '../../lib/format'
import { useUrlState } from '../../lib/useUrlState'

type Entry = Schemas['AuditEntry']
const LIMIT = 100

const ENTITY_TYPES = [
  'party', 'invoice', 'invoice_line', 'payment', 'deposit', 'expense', 'catalog_item',
  'subscription', 'account', 'organization', 'app_user', 'tax_rate', 'login',
]
const ACTIONS = [
  'create', 'update', 'delete', 'issue', 'void', 'revise', 'archive', 'login', 'login_failed',
  'logout', 'password_change', 'export', 'import', 'email',
]

function summary(entry: Entry): string {
  const changes = Object.entries(entry.changes ?? {})
  if (!changes.length) return ''
  if (entry.action !== 'update') return changes.map(([k]) => k).slice(0, 6).join(', ')
  return (changes as [string, [unknown, unknown]][])
    .map(([field, [before, after]]) => `${field}: ${String(before)} → ${String(after)}`)
    .slice(0, 3)
    .join('; ')
}

export function AuditPage() {
  const { locale } = useAuth()
  const [f, setF] = useUrlState({ entity: '', action: '', from: '', to: '', offset: '0' })
  const query = {
    entity_type: f.entity || undefined,
    action: f.action || undefined,
    date_from: f.from || undefined,
    date_to: f.to || undefined,
  }
  const { data, isFetching } = useQuery({
    queryKey: ['audit', f],
    queryFn: async () =>
      unwrap(await api.GET('/api/audit', { params: { query: { ...query, limit: LIMIT, offset: Number(f.offset) } } })),
    placeholderData: keepPreviousData,
  })
  const exportUrl = `/api/audit/export.csv?${new URLSearchParams(
    Object.entries(query).filter(([, v]) => v) as [string, string][],
  )}`

  return (
    <>
      <PageHeader
        title="Audit log"
        subtitle="Every change and sign-in, newest first"
        actions={
          <Button component="a" href={exportUrl} variant="light" leftSection={<IconDownload size={16} />}>
            Export CSV
          </Button>
        }
      />
      <Group mb="sm" gap="sm">
        <Select placeholder="Any record type" clearable w={180} value={f.entity || null} onChange={(entity) => setF({ entity: entity ?? '' })} data={ENTITY_TYPES} />
        <Select placeholder="Any action" clearable w={160} value={f.action || null} onChange={(action) => setF({ action: action ?? '' })} data={ACTIONS} />
        <TextInput type="date" aria-label="From date" value={f.from} onChange={(e) => setF({ from: e.currentTarget.value })} />
        <Text size="sm">to</Text>
        <TextInput type="date" aria-label="To date" value={f.to} onChange={(e) => setF({ to: e.currentTarget.value })} />
      </Group>
      <DataTable<Entry>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        page={data && { total: data.total, limit: LIMIT, offset: Number(f.offset), onOffset: (o) => setF({ offset: String(o) }) }}
        columns={[
          { key: 'when', header: 'When', render: (r) => formatDateTime(r.occurred_at, locale.locale) },
          { key: 'who', header: 'Who', render: (r) => r.user_name ?? r.actor },
          { key: 'action', header: 'Action', render: (r) => <Badge variant="light">{r.action}</Badge> },
          {
            key: 'what',
            header: 'Record',
            render: (r) => [r.entity_type?.replaceAll('_', ' '), r.entity_id].filter(Boolean).join(' #'),
          },
          {
            key: 'changes',
            header: 'Changes',
            wide: true,
            render: (r) => (
              <Text size="xs" lineClamp={2}>
                {r.reason && <b>{r.reason} — </b>}
                <Code>{summary(r)}</Code>
              </Text>
            ),
          },
          { key: 'ip', header: 'IP', wide: true, render: (r) => r.ip_address },
        ]}
      />
    </>
  )
}
