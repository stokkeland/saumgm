import { Button, Group, SegmentedControl, Select, Text, TextInput } from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
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
  PaymentStatusBadge,
  SearchInput,
  type ArchiveFilterValue,
} from '../../components/ui'
import { useUrlState } from '../../lib/useUrlState'

type Row = Schemas['InvoiceListItem']
const LIMIT = 50
const DEFAULTS = {
  q: '',
  view: 'open',
  kind: '',
  from: '',
  to: '',
  archived: 'current',
  offset: '0',
}

const VIEWS = [
  { value: 'open', label: 'Open' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'paid', label: 'Paid' },
  { value: 'draft', label: 'Drafts' },
  { value: 'void', label: 'Void' },
  { value: 'all', label: 'All' },
]

export function InvoicesPage() {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const [f, setF] = useUrlState(DEFAULTS)

  const payment = ['open', 'overdue', 'paid'].includes(f.view) ? f.view : undefined
  const status = ['draft', 'void'].includes(f.view) ? f.view : undefined

  const { data, isFetching } = useQuery({
    queryKey: ['invoices', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/invoices', {
          params: {
            query: {
              q: f.q || undefined,
              payment: payment as 'open' | 'overdue' | 'paid' | undefined,
              status: status as 'draft' | 'void' | undefined,
              kind: (f.kind || undefined) as Row['kind'] | undefined,
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
        title="Invoices"
        subtitle="Invoices and credit notes"
        actions={
          canEdit && (
            <Button component={Link} to="/invoices/new" leftSection={<IconPlus size={16} />}>
              New invoice
            </Button>
          )
        }
      />
      <Group mb="sm" gap="sm" wrap="wrap">
        <SegmentedControl value={f.view} onChange={(view) => setF({ view })} data={VIEWS} />
        <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Number, client, bill-to" />
        <Select
          w={150}
          value={f.kind}
          onChange={(kind) => setF({ kind: kind ?? '' })}
          data={[
            { value: '', label: 'All kinds' },
            { value: 'invoice', label: 'Invoices' },
            { value: 'credit_note', label: 'Credit notes' },
          ]}
        />
        <TextInput type="date" aria-label="From date" value={f.from} onChange={(e) => setF({ from: e.currentTarget.value })} />
        <Text size="sm">to</Text>
        <TextInput type="date" aria-label="To date" value={f.to} onChange={(e) => setF({ to: e.currentTarget.value })} />
        <ArchiveFilter value={f.archived as ArchiveFilterValue} onChange={(archived) => setF({ archived })} />
      </Group>
      <DataTable<Row>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/invoices/${r.id}`)}
        empty="No invoices match"
        page={
          data && {
            total: data.total,
            limit: LIMIT,
            offset: Number(f.offset),
            onOffset: (offset) => setF({ offset: String(offset) }),
          }
        }
        columns={[
          {
            key: 'no',
            header: 'No.',
            render: (r) => (
              <Text size="sm" fw={500}>
                {r.number ?? 'Draft'}
                {r.kind === 'credit_note' && (
                  <Text span size="xs" c="teal">
                    {' '}
                    credit
                  </Text>
                )}
              </Text>
            ),
          },
          { key: 'date', header: 'Date', render: (r) => <DateText value={r.issue_date} /> },
          { key: 'party', header: 'Client', render: (r) => r.party_name },
          {
            key: 'status',
            header: 'Status',
            render: (r) => (
              <Group gap={4}>
                <PaymentStatusBadge status={r.payment_status} overdue={r.is_overdue} />
                <ArchivedBadge at={r.archived_at} />
              </Group>
            ),
          },
          { key: 'due', header: 'Due', wide: true, render: (r) => <DateText value={r.due_date} /> },
          { key: 'total', header: 'Total', align: 'right', render: (r) => <Money value={r.total} /> },
          {
            key: 'balance',
            header: 'Balance',
            align: 'right',
            render: (r) => <Money value={r.balance_due} strong={Number(r.balance_due) > 0} />,
          },
        ]}
      />
    </>
  )
}
