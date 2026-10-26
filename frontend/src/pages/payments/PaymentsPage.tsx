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

import { Badge, Button, Group, SegmentedControl, Text, TextInput } from '@mantine/core'
import { IconBuildingBank, IconPlus } from '@tabler/icons-react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DataTable } from '../../components/DataTable'
import {
  ArchivedBadge,
  ArchiveFilter,
  DateText,
  Money,
  PageHeader,
  SearchInput,
  type ArchiveFilterValue,
} from '../../components/ui'
import { labelOf, PAYMENT_METHODS } from '../../lib/labels'
import { useUrlState } from '../../lib/useUrlState'

type Row = Schemas['PaymentOut']
const LIMIT = 50
const DEFAULTS = { q: '', view: 'all', from: '', to: '', archived: 'current', offset: '0' }

export function PaymentStateBadge({ payment }: { payment: Row }) {
  if (payment.is_historical) return <Badge variant="outline" color="gray" size="sm">Imported</Badge>
  if (payment.deposit_id) return <Badge variant="light" color="green" size="sm">Deposited</Badge>
  return <Badge variant="light" color="yellow" size="sm">Not deposited</Badge>
}

export function PaymentsPage() {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const [f, setF] = useUrlState(DEFAULTS)

  const { data, isFetching } = useQuery({
    queryKey: ['payments', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/payments', {
          params: {
            query: {
              q: f.q || undefined,
              undeposited: f.view === 'undeposited',
              date_from: f.from || undefined,
              date_to: f.to || undefined,
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
        title="Payments"
        subtitle="Money received from clients"
        actions={
          canEdit && (
            <>
              <Button component={Link} to="/deposits/new" variant="light" leftSection={<IconBuildingBank size={16} />}>
                Make deposit
              </Button>
              <Button component={Link} to="/payments/new" leftSection={<IconPlus size={16} />}>
                Receive payment
              </Button>
            </>
          )
        }
      />
      <Group mb="sm" gap="sm" wrap="wrap">
        <SegmentedControl
          value={f.view}
          onChange={(view) => setF({ view })}
          data={[
            { value: 'all', label: 'All' },
            { value: 'undeposited', label: 'Not deposited' },
          ]}
        />
        <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Reference or notes" />
        <TextInput type="date" aria-label="From date" value={f.from} onChange={(e) => setF({ from: e.currentTarget.value })} />
        <Text size="sm">to</Text>
        <TextInput type="date" aria-label="To date" value={f.to} onChange={(e) => setF({ to: e.currentTarget.value })} />
        <ArchiveFilter value={f.archived as ArchiveFilterValue} onChange={(archived) => setF({ archived })} />
      </Group>
      <DataTable<Row>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/payments/${r.id}`)}
        empty="No payments match"
        page={
          data && {
            total: data.total,
            limit: LIMIT,
            offset: Number(f.offset),
            onOffset: (offset) => setF({ offset: String(offset) }),
          }
        }
        columns={[
          { key: 'date', header: 'Received', render: (r) => <DateText value={r.received_date} /> },
          { key: 'party', header: 'From', render: (r) => r.party_name },
          {
            key: 'method',
            header: 'Method',
            render: (r) => [labelOf(PAYMENT_METHODS, r.method), r.reference].filter(Boolean).join(' '),
          },
          {
            key: 'invoices',
            header: 'Invoices',
            wide: true,
            render: (r) => r.allocations.map((a) => a.invoice_number).filter(Boolean).join(', '),
          },
          {
            key: 'state',
            header: '',
            render: (r) => (
              <Group gap={4}>
                <PaymentStateBadge payment={r} />
                <ArchivedBadge at={r.archived_at} />
              </Group>
            ),
          },
          { key: 'amount', header: 'Amount', align: 'right', render: (r) => <Money value={r.amount} /> },
          {
            key: 'unapplied',
            header: 'Unapplied',
            align: 'right',
            wide: true,
            render: (r) => (Number(r.unapplied) ? <Money value={r.unapplied} /> : ''),
          },
        ]}
      />
    </>
  )
}
