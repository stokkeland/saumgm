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

import { Anchor, Badge, Button, Card, Checkbox, Group, Loader, Select, SimpleGrid, Text, TextInput, Tooltip } from '@mantine/core'
import { IconArrowsExchange, IconChecks, IconPencil, IconPlus } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { api, unwrap } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DataTable } from '../../components/DataTable'
import { DateText, Money, PageHeader, SearchInput } from '../../components/ui'
import {
  BANK_ACCOUNT_KINDS,
  BANK_ENTRY_KINDS,
  BANK_ENTRY_STATUS_COLORS,
  BANK_ENTRY_STATUSES,
  labelOf,
} from '../../lib/labels'
import { notifyError } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'
import { AccountForm, EntryForm, TransferForm } from './forms'
import { invalidateBanking, isCard, type BankAccount, type BankEntry } from './shared'
import { ReconcileModal } from './Reconcile'

const LIMIT = 100

/** A card shows what is owed (a positive number) instead of a negative balance. */
function BalanceText({ account, value }: { account: BankAccount; value: string }) {
  if (isCard(account)) {
    const owed = -Number(value)
    return (
      <Text span size="sm" c={owed > 0 ? 'red' : undefined}>
        <Money value={Math.abs(owed).toFixed(4)} /> {owed > 0 ? 'owed' : owed < 0 ? 'credit' : ''}
      </Text>
    )
  }
  return <Money value={value} />
}

export function BankAccountsPage() {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const [f, setF] = useUrlState({ closed: '' })
  const [creating, setCreating] = useState(false)
  const [transferring, setTransferring] = useState(false)
  const { data, isFetching } = useQuery({
    queryKey: ['bank-accounts', f.closed ? 'all' : 'open'],
    queryFn: async () =>
      unwrap(await api.GET('/api/bank-accounts', { params: { query: { active: f.closed ? null : true } } })),
  })
  return (
    <>
      <PageHeader
        title="Bank accounts"
        subtitle="Checking, savings and credit cards, with their registers"
        actions={
          canEdit && (
            <>
              <Button variant="light" leftSection={<IconArrowsExchange size={16} />} onClick={() => setTransferring(true)}>
                Transfer
              </Button>
              <Button leftSection={<IconPlus size={16} />} onClick={() => setCreating(true)}>
                New account
              </Button>
            </>
          )
        }
      />
      <Group mb="sm">
        <Checkbox label="Show closed accounts" checked={!!f.closed} onChange={(e) => setF({ closed: e.currentTarget.checked ? '1' : '' })} />
      </Group>
      <DataTable<BankAccount>
        rows={data}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/banking/${r.id}`)}
        empty="No bank accounts yet. Add your checking account and cards; each one starts at an opening balance on a day you choose."
        columns={[
          {
            key: 'name',
            header: 'Account',
            render: (r) => (
              <>
                {r.name}
                {r.number_last4 && <Text span c="dimmed"> …{r.number_last4}</Text>}
                {!r.is_active && <Badge ml="xs" variant="light" color="gray">closed</Badge>}
              </>
            ),
          },
          { key: 'bank', header: 'Bank', render: (r) => r.bank_name },
          { key: 'kind', header: 'Kind', render: (r) => labelOf(BANK_ACCOUNT_KINDS, r.kind) },
          {
            key: 'rec',
            header: 'Reconciled through',
            render: (r) => (r.last_reconciled_date ? <DateText value={r.last_reconciled_date} /> : <Text span c="dimmed" size="sm">never</Text>),
          },
          { key: 'unc', header: 'Uncleared', align: 'right', render: (r) => r.uncleared_count || '' },
          { key: 'cleared', header: 'Cleared', align: 'right', render: (r) => <BalanceText account={r} value={r.cleared_balance} /> },
          { key: 'balance', header: 'Balance', align: 'right', render: (r) => <BalanceText account={r} value={r.balance} /> },
        ]}
      />
      {creating && <AccountForm onClose={() => setCreating(false)} />}
      {transferring && <TransferForm onClose={() => setTransferring(false)} />}
    </>
  )
}

function Describe({ entry }: { entry: BankEntry }) {
  const text = [entry.payee, entry.description].filter(Boolean).join(' – ')
  const link =
    entry.deposit_id ? `/deposits/${entry.deposit_id}`
    : entry.expense_id ? `/expenses/${entry.expense_id}`
    : entry.transfer_account_id ? `/banking/${entry.transfer_account_id}`
    : null
  return (
    <>
      {text || labelOf(BANK_ENTRY_KINDS, entry.kind)}
      {link && entry.kind !== 'manual' && (
        <Anchor component={Link} to={link} size="xs" ml="xs" onClick={(e) => e.stopPropagation()}>
          {entry.kind === 'transfer' ? entry.transfer_account_name : labelOf(BANK_ENTRY_KINDS, entry.kind).toLowerCase()}
        </Anchor>
      )}
      {entry.kind === 'adjustment' && (
        <Badge ml="xs" size="xs" variant="light" color="grape">
          adjustment
        </Badge>
      )}
    </>
  )
}

function StatusBadge({ entry, canEdit }: { entry: BankEntry; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const flip = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.PATCH('/api/bank-entries/{entry_id}', {
          params: { path: { entry_id: entry.id } },
          body: { status: entry.status === 'cleared' ? 'uncleared' : 'cleared' },
        }),
      ),
    onSuccess: () => invalidateBanking(queryClient),
    onError: notifyError,
  })
  const badge = (
    <Badge
      variant="light"
      color={BANK_ENTRY_STATUS_COLORS[entry.status]}
      style={{ cursor: canEdit && entry.status !== 'reconciled' ? 'pointer' : undefined }}
      onClick={(e) => {
        e.stopPropagation()
        if (canEdit && entry.status !== 'reconciled' && !flip.isPending) flip.mutate()
      }}
    >
      {labelOf(BANK_ENTRY_STATUSES, entry.status)}
    </Badge>
  )
  return canEdit && entry.status !== 'reconciled' ? (
    <Tooltip label={entry.status === 'cleared' ? 'Mark uncleared' : 'Mark cleared'}>{badge}</Tooltip>
  ) : (
    badge
  )
}

export function RegisterPage() {
  const { id } = useParams()
  const accountId = Number(id)
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const [f, setF] = useUrlState({ q: '', status: '', from: '', to: '', offset: '0' })
  const [editing, setEditing] = useState(false)
  const [entry, setEntry] = useState<BankEntry | 'new' | null>(null)
  const [transferring, setTransferring] = useState(false)
  const [reconciling, setReconciling] = useState(false)

  const { data: account, error } = useQuery({
    queryKey: ['bank-account', accountId],
    queryFn: async () => unwrap(await api.GET('/api/bank-accounts/{account_id}', { params: { path: { account_id: accountId } } })),
  })
  const { data: entries, isFetching } = useQuery({
    queryKey: ['bank-entries', accountId, f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/bank-accounts/{account_id}/entries', {
          params: {
            path: { account_id: accountId },
            query: {
              q: f.q || undefined,
              status: (f.status || undefined) as BankEntry['status'] | undefined,
              date_from: f.from || undefined,
              date_to: f.to || undefined,
              limit: LIMIT,
              offset: Number(f.offset),
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })

  if (error) return <Text c="red">{error.message}</Text>
  if (!account) return <Loader />
  const card = isCard(account)
  const open = (e: BankEntry) => {
    if (e.kind === 'deposit' && e.deposit_id) navigate(`/deposits/${e.deposit_id}`)
    else if (e.kind === 'expense' && e.expense_id) navigate(`/expenses/${e.expense_id}`)
    else if (canEdit) setEntry(e)
  }
  return (
    <>
      <PageHeader
        title={
          <Group gap="xs">
            {account.name}
            {account.number_last4 && <Text span c="dimmed" size="lg">…{account.number_last4}</Text>}
            {!account.is_active && <Badge variant="light" color="gray">closed</Badge>}
          </Group>
        }
        subtitle={[account.bank_name, labelOf(BANK_ACCOUNT_KINDS, account.kind)].filter(Boolean).join(' · ')}
        actions={
          canEdit && (
            <>
              <Button variant="default" leftSection={<IconPencil size={16} />} onClick={() => setEditing(true)}>
                Edit account
              </Button>
              <Button variant="light" leftSection={<IconChecks size={16} />} onClick={() => setReconciling(true)}>
                Reconcile
              </Button>
              <Button variant="light" leftSection={<IconArrowsExchange size={16} />} onClick={() => setTransferring(true)}>
                Transfer
              </Button>
              <Button leftSection={<IconPlus size={16} />} disabled={!account.is_active} onClick={() => setEntry('new')}>
                New entry
              </Button>
            </>
          )
        }
      />
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="md">
        <Card withBorder>
          <Text size="sm" c="dimmed">{card ? 'Owed now' : 'Balance'}</Text>
          <Text size="xl" fw={700}>
            <BalanceText account={account} value={account.balance} />
          </Text>
        </Card>
        <Card withBorder>
          <Text size="sm" c="dimmed">Cleared at the bank</Text>
          <Text size="xl" fw={700}>
            <BalanceText account={account} value={account.cleared_balance} />
          </Text>
          <Text size="xs" c="dimmed">{account.uncleared_count} line(s) not cleared yet</Text>
        </Card>
        <Card withBorder>
          <Text size="sm" c="dimmed">Reconciled through</Text>
          <Text size="xl" fw={700}>
            {account.last_reconciled_date ? <DateText value={account.last_reconciled_date} /> : 'never'}
          </Text>
          {account.last_statement_balance && (
            <Text size="xs" c="dimmed">
              statement balance <Money value={account.last_statement_balance} />
            </Text>
          )}
        </Card>
        <Card withBorder>
          <Text size="sm" c="dimmed">Register starts</Text>
          <Text size="xl" fw={700}>
            <DateText value={account.opening_date} />
          </Text>
          <Text size="xs" c="dimmed">
            opening balance <Money value={account.opening_balance} />
          </Text>
        </Card>
      </SimpleGrid>
      <Group mb="sm" gap="sm">
        <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Payee, description, check no." />
        <Select w={150} aria-label="Status" placeholder="Any status" clearable value={f.status || null} onChange={(status) => setF({ status: status ?? '' })} data={BANK_ENTRY_STATUSES} />
        <TextInput type="date" aria-label="From" value={f.from} onChange={(e) => setF({ from: e.currentTarget.value })} />
        <TextInput type="date" aria-label="To" value={f.to} onChange={(e) => setF({ to: e.currentTarget.value })} />
      </Group>
      <DataTable<BankEntry>
        rows={entries?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={open}
        empty="No lines yet. Deposits into this account, expenses paid from it and transfers appear here by themselves; add anything else with New entry."
        page={entries && { total: entries.total, limit: LIMIT, offset: Number(f.offset), onOffset: (o) => setF({ offset: String(o) }) }}
        columns={[
          { key: 'date', header: 'Date', render: (r) => <DateText value={r.entry_date} /> },
          { key: 'what', header: 'Payee / description', wide: true, render: (r) => <Describe entry={r} /> },
          { key: 'ref', header: 'Ref.', render: (r) => r.reference },
          { key: 'cat', header: 'Category', render: (r) => r.account_name },
          { key: 'status', header: 'Status', render: (r) => <StatusBadge entry={r} canEdit={canEdit} /> },
          { key: 'in', header: card ? 'Payment' : 'In', align: 'right', render: (r) => (Number(r.amount) > 0 ? <Money value={r.amount} /> : null) },
          {
            key: 'out',
            header: card ? 'Charge' : 'Out',
            align: 'right',
            render: (r) => (Number(r.amount) < 0 ? <Money value={(-Number(r.amount)).toFixed(4)} /> : null),
          },
          { key: 'bal', header: card ? 'Owed' : 'Balance', align: 'right', render: (r) => <BalanceText account={account} value={r.running_balance} /> },
        ]}
      />
      {editing && <AccountForm account={account} onClose={() => setEditing(false)} />}
      {entry && <EntryForm account={account} entry={entry === 'new' ? undefined : entry} onClose={() => setEntry(null)} />}
      {transferring && <TransferForm fromId={account.id} onClose={() => setTransferring(false)} />}
      {reconciling && <ReconcileModal account={account} onClose={() => setReconciling(false)} />}
    </>
  )
}
