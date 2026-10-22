import {
  ActionIcon,
  Button,
  Card,
  Group,
  Loader,
  Menu,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconArchive, IconDots, IconPlus, IconTrash } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAccounts, useOrganization } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { DataTable } from '../../components/DataTable'
import { HistoryPanel } from '../../components/HistoryPanel'
import {
  ArchivedBadge,
  ArchiveFilter,
  DateText,
  Money,
  PageHeader,
  SearchInput,
  type ArchiveFilterValue,
} from '../../components/ui'
import { todayIso } from '../../lib/format'
import { notifyError, notifySaved } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'

type Expense = Schemas['ExpenseOut']
const LIMIT = 50
const DEFAULTS = { q: '', vendor: '', account: '', from: '', to: '', archived: 'current', offset: '0' }

export function ExpensesPage() {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const { data: accounts } = useAccounts()
  const [f, setF] = useUrlState(DEFAULTS)
  const { data, isFetching } = useQuery({
    queryKey: ['expenses', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/expenses', {
          params: {
            query: {
              q: f.q || undefined,
              vendor_party_id: f.vendor ? Number(f.vendor) : undefined,
              account_id: f.account ? Number(f.account) : undefined,
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
        title="Expenses"
        subtitle="Purchases and costs"
        actions={
          canEdit && (
            <Button onClick={() => navigate('/expenses/new')} leftSection={<IconPlus size={16} />}>
              New expense
            </Button>
          )
        }
      />
      <Group mb="sm" gap="sm" wrap="wrap">
        <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Description or reference" />
        <ContactSelect
          placeholder="Any vendor"
          role="vendor"
          w={240}
          value={f.vendor ? Number(f.vendor) : null}
          onChange={(id) => setF({ vendor: id ? String(id) : '' })}
        />
        <Select
          placeholder="Any account"
          clearable
          searchable
          w={240}
          value={f.account || null}
          onChange={(account) => setF({ account: account ?? '' })}
          data={(accounts ?? []).map((a) => ({ value: String(a.id), label: `${a.code} ${a.name}` }))}
        />
        <TextInput type="date" aria-label="From date" value={f.from} onChange={(e) => setF({ from: e.currentTarget.value })} />
        <Text size="sm">to</Text>
        <TextInput type="date" aria-label="To date" value={f.to} onChange={(e) => setF({ to: e.currentTarget.value })} />
        <ArchiveFilter value={f.archived as ArchiveFilterValue} onChange={(archived) => setF({ archived })} />
      </Group>
      <DataTable<Expense>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/expenses/${r.id}`)}
        empty="No expenses match"
        page={data && { total: data.total, limit: LIMIT, offset: Number(f.offset), onOffset: (o) => setF({ offset: String(o) }) }}
        columns={[
          { key: 'date', header: 'Date', render: (r) => <DateText value={r.expense_date} /> },
          { key: 'vendor', header: 'Vendor', render: (r) => r.vendor_name },
          { key: 'descr', header: 'Description', render: (r) => r.description },
          {
            key: 'accounts',
            header: 'Accounts',
            wide: true,
            render: (r) => [...new Set(r.lines.map((l) => `${l.account_code} ${l.account_name}`))].join(', '),
          },
          { key: 'arch', header: '', render: (r) => <ArchivedBadge at={r.archived_at} /> },
          { key: 'total', header: 'Total', align: 'right', render: (r) => <Money value={r.total} /> },
        ]}
      />
    </>
  )
}

interface LineForm {
  key: number
  account_id: string | null
  amount: number | string
  description: string
}

function ExpenseEditor({ expense, onSaved, onCancel }: { expense?: Expense; onSaved: (e: Expense) => void; onCancel: () => void }) {
  const queryClient = useQueryClient()
  const { data: accounts } = useAccounts()
  const { data: organization } = useOrganization()
  const [expenseDate, setExpenseDate] = useState(expense?.expense_date ?? todayIso())
  const [vendor, setVendor] = useState<number | null>(expense?.vendor_party_id ?? null)
  const [forParty, setForParty] = useState<number | null>(expense?.for_party_id ?? null)
  const [reference, setReference] = useState(expense?.reference ?? '')
  const [description, setDescription] = useState(expense?.description ?? '')
  const [lines, setLines] = useState<LineForm[]>(
    expense?.lines.map((l, i) => ({
      key: i,
      account_id: String(l.account_id),
      amount: Number(l.amount),
      description: l.description ?? '',
    })) ?? [{ key: 0, account_id: null, amount: '', description: '' }],
  )
  const total = lines.reduce((sum, l) => sum + Number(l.amount || 0), 0)
  const update = (index: number, change: Partial<LineForm>) =>
    setLines((all) => all.map((l, i) => (i === index ? { ...l, ...change } : l)))

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        expense_date: expenseDate,
        vendor_party_id: vendor,
        for_party_id: forParty,
        reference: reference.trim() || null,
        description: description.trim() || null,
        lines: lines
          .filter((l) => l.account_id && l.amount !== '')
          .map((l) => ({ account_id: Number(l.account_id), amount: String(l.amount), description: l.description.trim() || null })),
      }
      return expense
        ? unwrap(await api.PATCH('/api/expenses/{expense_id}', { params: { path: { expense_id: expense.id } }, body }))
        : unwrap(await api.POST('/api/expenses', { body }))
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(['expense', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      notifySaved('Expense saved')
      onSaved(saved)
    },
    onError: notifyError,
  })

  const accountOptions = (accounts ?? [])
    .filter((a) => a.is_active || lines.some((l) => l.account_id === String(a.id)))
    .map((a) => ({ value: String(a.id), label: `${a.code} ${a.name}` }))
  const valid = expenseDate && lines.some((l) => l.account_id && l.amount !== '')

  return (
    <Stack>
      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          <TextInput type="date" label="Date" required value={expenseDate} onChange={(e) => setExpenseDate(e.currentTarget.value)} />
          <ContactSelect label="Vendor" role="vendor" value={vendor} onChange={setVendor} />
          <ContactSelect
            label="For"
            placeholder={expense ? undefined : 'The business itself'}
            description={!expense && organization?.self_party_id ? 'Empty: the business itself' : undefined}
            value={forParty}
            onChange={setForParty}
          />
          <TextInput label="Reference" placeholder="Vendor invoice / receipt no." value={reference} onChange={(e) => setReference(e.currentTarget.value)} />
          <Textarea label="Description" autosize style={{ gridColumn: 'span 2' }} value={description} onChange={(e) => setDescription(e.currentTarget.value)} />
        </SimpleGrid>
      </Card>
      <Card withBorder>
        <Text fw={600} mb="xs">
          Split by account
        </Text>
        <Stack gap="xs">
          {lines.map((line, index) => (
            <Group key={line.key} wrap="nowrap" align="flex-start">
              <Select
                aria-label="Account"
                placeholder="Account"
                searchable
                w={280}
                data={accountOptions}
                value={line.account_id}
                onChange={(account_id) => update(index, { account_id })}
              />
              <TextInput
                aria-label="Line note"
                placeholder="Note (optional)"
                style={{ flex: 1 }}
                value={line.description}
                onChange={(e) => update(index, { description: e.currentTarget.value })}
              />
              <NumberInput aria-label="Amount" w={140} decimalScale={2} value={line.amount} onChange={(amount) => update(index, { amount })} />
              <ActionIcon variant="subtle" color="red" mt={6} aria-label="Remove line" disabled={lines.length === 1} onClick={() => setLines((all) => all.filter((_, i) => i !== index))}>
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          ))}
        </Stack>
        <Group justify="space-between" mt="sm">
          <Button
            size="xs"
            variant="subtle"
            leftSection={<IconPlus size={14} />}
            onClick={() => setLines((all) => [...all, { key: Date.now(), account_id: null, amount: '', description: '' }])}
          >
            Add account
          </Button>
          <Text fw={600}>
            Total <Money value={String(total)} strong />
          </Text>
        </Group>
      </Card>
      <Group justify="flex-end">
        <Button variant="default" onClick={onCancel}>
          Cancel
        </Button>
        <Button disabled={!valid} loading={save.isPending} onClick={() => save.mutate()}>
          Save expense
        </Button>
      </Group>
    </Stack>
  )
}

export function NewExpensePage() {
  const navigate = useNavigate()
  return (
    <>
      <PageHeader title="New expense" />
      <ExpenseEditor onSaved={(saved) => navigate(`/expenses/${saved.id}`, { replace: true })} onCancel={() => navigate(-1)} />
    </>
  )
}

export function ExpensePage() {
  const { id } = useParams()
  const expenseId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canEdit, isOwner } = useAuth()
  const [editing, setEditing] = useState(false)
  const { data: expense, error } = useQuery({
    queryKey: ['expense', expenseId],
    queryFn: async () =>
      unwrap(await api.GET('/api/expenses/{expense_id}', { params: { path: { expense_id: expenseId } } })),
  })
  const archive = useMutation({
    mutationFn: async (archived: boolean) =>
      unwrap(
        await api.POST(archived ? '/api/expenses/{expense_id}/archive' : '/api/expenses/{expense_id}/unarchive', {
          params: { path: { expense_id: expenseId } },
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(['expense', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/expenses/{expense_id}', { params: { path: { expense_id: expenseId } } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      notifySaved('Expense deleted')
      navigate('/expenses')
    },
    onError: notifyError,
  })

  if (error) return <Text c="red">{error.message}</Text>
  if (!expense) return <Loader />
  const editable = canEdit && !expense.archived_at

  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            Expense <Money value={expense.total} />
            <ArchivedBadge at={expense.archived_at} />
          </Group>
        }
        subtitle={[expense.vendor_name, expense.description].filter(Boolean).join(' · ')}
        actions={
          canEdit &&
          !editing && (
            <>
              {editable && <Button onClick={() => setEditing(true)}>Edit</Button>}
              <Menu position="bottom-end">
                <Menu.Target>
                  <ActionIcon variant="default" size="lg" aria-label="More actions">
                    <IconDots size={18} />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  {expense.archived_at ? (
                    <Menu.Item leftSection={<IconArchive size={14} />} disabled={!isOwner} onClick={() => archive.mutate(false)}>
                      Unarchive{!isOwner && ' (owner only)'}
                    </Menu.Item>
                  ) : (
                    <Menu.Item leftSection={<IconArchive size={14} />} onClick={() => archive.mutate(true)}>
                      Archive
                    </Menu.Item>
                  )}
                  {editable && (
                    <Menu.Item
                      color="red"
                      leftSection={<IconTrash size={14} />}
                      onClick={() =>
                        modals.openConfirmModal({
                          title: 'Delete this expense?',
                          labels: { confirm: 'Delete', cancel: 'Cancel' },
                          confirmProps: { color: 'red' },
                          onConfirm: () => remove.mutate(),
                        })
                      }
                    >
                      Delete
                    </Menu.Item>
                  )}
                </Menu.Dropdown>
              </Menu>
            </>
          )
        }
      />
      {editing ? (
        <ExpenseEditor expense={expense} onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} />
      ) : (
        <Stack>
          <Card withBorder>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Text size="sm">
                <Text span c="dimmed">Date </Text>
                <DateText value={expense.expense_date} />
              </Text>
              <Text size="sm">
                <Text span c="dimmed">For </Text>
                {expense.for_name ?? '—'}
              </Text>
              <Text size="sm">
                <Text span c="dimmed">Reference </Text>
                {expense.reference ?? '—'}
              </Text>
              <Text size="sm">
                <Text span c="dimmed">Entered </Text>
                <DateText value={expense.entered_date} />
              </Text>
            </SimpleGrid>
          </Card>
          <DataTable<Expense['lines'][number]>
            rows={expense.lines}
            rowKey={(l) => l.id}
            columns={[
              { key: 'account', header: 'Account', render: (l) => `${l.account_code} ${l.account_name}` },
              { key: 'note', header: 'Note', render: (l) => l.description },
              { key: 'amount', header: 'Amount', align: 'right', render: (l) => <Money value={l.amount} /> },
            ]}
          />
          <Tabs defaultValue="history">
            <Tabs.List mb="md">
              <Tabs.Tab value="history">History</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="history">
              <HistoryPanel entityType="expense" entityId={expense.id} />
            </Tabs.Panel>
          </Tabs>
        </Stack>
      )}
    </>
  )
}
