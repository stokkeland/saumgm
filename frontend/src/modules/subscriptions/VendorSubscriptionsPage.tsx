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

import {
  Anchor,
  Badge,
  Button,
  Checkbox,
  Group,
  List,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconCash, IconPlus } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAccounts } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { DataTable } from '../../components/DataTable'
import { DateText, Money, PageHeader, SearchInput } from '../../components/ui'
import { todayIso } from '../../lib/format'
import { everyMonths, labelOf, SUBSCRIPTION_STATUS_COLORS, SUBSCRIPTION_STATUSES } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'

type VendorSub = Schemas['VendorSubscriptionOut']
const LIMIT = 50

function useAccountOptions() {
  const { data: accounts } = useAccounts()
  return (accounts ?? [])
    .filter((a) => a.is_active)
    .map((a) => ({ value: String(a.id), label: `${a.code} ${a.name}` }))
}

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ['vendor-subscriptions'] })
  queryClient.invalidateQueries({ queryKey: ['vendor-subscription-options'] })
  queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
}

function VendorSubscriptionForm({ sub, onClose, onPay }: { sub?: VendorSub; onClose: () => void; onPay: (s: VendorSub) => void }) {
  const queryClient = useQueryClient()
  const accountOptions = useAccountOptions()
  const form = useForm({
    initialValues: {
      party_id: sub?.party_id ?? null,
      name: sub?.name ?? '',
      service_identifier: sub?.service_identifier ?? '',
      amount: sub ? Number(sub.amount) : ('' as number | ''),
      interval_months: sub?.interval_months ?? 1,
      next_due_date: sub?.next_due_date ?? '',
      end_date: sub?.end_date ?? '',
      expense_account_id: sub?.expense_account_id ? String(sub.expense_account_id) : null,
      autopay: sub?.autopay ?? false,
      auto_renew: sub?.auto_renew ?? true,
      status: sub?.status ?? 'active',
      notes: sub?.notes ?? '',
    },
    validate: {
      party_id: (v) => (v ? null : 'Choose a vendor'),
      name: (v) => (v.trim() ? null : 'Required'),
      amount: (v) => (v === '' ? 'Required' : null),
    },
  })
  const v = form.values
  const save = useMutation({
    mutationFn: async () => {
      const body = {
        party_id: v.party_id!,
        name: v.name.trim(),
        service_identifier: v.service_identifier.trim() || null,
        amount: String(v.amount),
        interval_months: v.interval_months,
        next_due_date: v.next_due_date || null,
        end_date: v.end_date || null,
        expense_account_id: v.expense_account_id ? Number(v.expense_account_id) : null,
        autopay: v.autopay,
        auto_renew: v.auto_renew,
        status: v.status as VendorSub['status'],
        notes: v.notes.trim() || null,
      }
      return sub
        ? unwrap(await api.PATCH('/api/vendor-subscriptions/{subscription_id}', { params: { path: { subscription_id: sub.id } }, body }))
        : unwrap(await api.POST('/api/vendor-subscriptions', { body }))
    },
    onSuccess: () => {
      invalidate(queryClient)
      notifySaved('Vendor subscription saved')
      onClose()
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/vendor-subscriptions/{subscription_id}', { params: { path: { subscription_id: sub!.id } } })),
    onSuccess: () => {
      invalidate(queryClient)
      notifySaved('Vendor subscription deleted')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={sub ? sub.name : 'New vendor subscription'} size="lg">
      <form onSubmit={form.onSubmit(() => save.mutate())}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <ContactSelect label="Vendor" role="vendor" required value={v.party_id} onChange={(id) => form.setFieldValue('party_id', id)} error={form.errors.party_id} />
            <TextInput label="Name" placeholder="VPS host-01, example.com registration…" required {...form.getInputProps('name')} />
            <TextInput label="For (server, domain, account…)" {...form.getInputProps('service_identifier')} />
            <Select label="Expense account" clearable searchable data={accountOptions} {...form.getInputProps('expense_account_id')} />
            <NumberInput label="Amount" min={0} decimalScale={4} required {...form.getInputProps('amount')} />
            <NumberInput label="Every (months)" min={1} max={120} allowDecimal={false} {...form.getInputProps('interval_months')} />
            <TextInput type="date" label="Next due" {...form.getInputProps('next_due_date')} />
            <TextInput type="date" label="End" {...form.getInputProps('end_date')} />
            <Select label="Status" data={SUBSCRIPTION_STATUSES} {...form.getInputProps('status')} />
            <Stack gap={6} mt="lg">
              <Checkbox label="Paid automatically (autopay)" {...form.getInputProps('autopay', { type: 'checkbox' })} />
              <Checkbox label="Renews automatically" {...form.getInputProps('auto_renew', { type: 'checkbox' })} />
            </Stack>
          </SimpleGrid>
          <Textarea label="Notes" autosize {...form.getInputProps('notes')} />
          {sub && (
            <Stack gap={4}>
              <Text size="sm" fw={600}>
                Used by
              </Text>
              {sub.used_by.length === 0 ? (
                <Text size="sm" c="dimmed">
                  No client subscription uses it. Link it from a client subscription's line ("Uses").
                </Text>
              ) : (
                <List size="sm">
                  {sub.used_by.map((u, n) => (
                    <List.Item key={n}>
                      <Anchor component={Link} to={`/contacts/${u.party_id}`}>
                        {u.party_name}
                      </Anchor>
                      {u.service_identifier ? `, ${u.service_identifier}` : ''}: {u.description}
                      {u.status !== 'active' && ` (${labelOf(SUBSCRIPTION_STATUSES, u.status).toLowerCase()})`}
                    </List.Item>
                  ))}
                </List>
              )}
              <Text size="sm" c="dimmed">
                {sub.payments ? (
                  <>
                    {sub.payments} payment(s) recorded, last on <DateText value={sub.last_paid_date} />.
                  </>
                ) : (
                  'No payments recorded yet.'
                )}
              </Text>
            </Stack>
          )}
          <Group justify="space-between">
            <Group>
              {sub && sub.payments === 0 && (
                <Button variant="subtle" color="red" loading={remove.isPending} onClick={() => remove.mutate()}>
                  Delete
                </Button>
              )}
              {sub && (
                <Button variant="light" leftSection={<IconCash size={16} />} onClick={() => onPay(sub)}>
                  Record payment
                </Button>
              )}
            </Group>
            <Group>
              <Button variant="default" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" loading={save.isPending}>
                Save
              </Button>
            </Group>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

function RecordPayment({ sub, onClose }: { sub: VendorSub; onClose: () => void }) {
  const queryClient = useQueryClient()
  const accountOptions = useAccountOptions()
  const form = useForm({
    initialValues: {
      paid_date: todayIso(),
      amount: Number(sub.amount),
      expense_account_id: sub.expense_account_id ? String(sub.expense_account_id) : null,
      reference: '',
    },
    validate: {
      expense_account_id: (v) => (v ? null : 'Choose the expense account'),
      amount: (v) => (v > 0 ? null : 'More than zero'),
    },
  })
  const v = form.values
  const pay = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/vendor-subscriptions/{subscription_id}/payments', {
          params: { path: { subscription_id: sub.id } },
          body: {
            paid_date: v.paid_date,
            amount: String(v.amount),
            expense_account_id: Number(v.expense_account_id),
            reference: v.reference.trim() || null,
          },
        }),
      ),
    onSuccess: () => {
      invalidate(queryClient)
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      notifySaved('Payment recorded as an expense')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={`Record payment: ${sub.name}`}>
      <form onSubmit={form.onSubmit(() => pay.mutate())}>
        <Stack>
          <Text size="sm">
            Books an expense to {sub.vendor_name}
            {sub.next_due_date && (
              <>
                {' '}
                and moves the next due date from <DateText value={sub.next_due_date} /> on by {sub.interval_months} month(s)
              </>
            )}
            .
          </Text>
          <SimpleGrid cols={2}>
            <TextInput type="date" label="Paid on" required {...form.getInputProps('paid_date')} />
            <NumberInput label="Amount" min={0} decimalScale={4} required {...form.getInputProps('amount')} />
          </SimpleGrid>
          <Select label="Expense account" searchable required data={accountOptions} {...form.getInputProps('expense_account_id')} />
          <TextInput label="Reference" placeholder="Vendor invoice or receipt no." {...form.getInputProps('reference')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={pay.isPending}>
              Record payment
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

export function VendorSubscriptionsPage() {
  const { canEdit } = useAuth()
  const [editing, setEditing] = useState<VendorSub | 'new' | null>(null)
  const [paying, setPaying] = useState<VendorSub | null>(null)
  const [f, setF] = useUrlState({ q: '', status: 'active', due: '', offset: '0' })
  const { data, isFetching } = useQuery({
    queryKey: ['vendor-subscriptions', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/vendor-subscriptions', {
          params: {
            query: {
              q: f.q || undefined,
              status: (f.status || undefined) as VendorSub['status'] | undefined,
              due_through: f.due || undefined,
              limit: LIMIT,
              offset: Number(f.offset),
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })
  const monthly = (data?.items ?? []).filter((s) => s.status === 'active').reduce((sum, s) => sum + Number(s.monthly_amount), 0)
  return (
    <>
      <PageHeader
        title="Vendor subscriptions"
        subtitle="What you pay for regularly: servers, domains, licenses, phone and internet"
        actions={
          canEdit && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>
              New vendor subscription
            </Button>
          )
        }
      />
      <Group mb="sm" gap="sm" justify="space-between">
        <Group gap="sm">
          <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Name, server, domain…" />
          <Select
            w={140}
            aria-label="Status"
            value={f.status}
            onChange={(status) => setF({ status: status ?? '' })}
            data={[...SUBSCRIPTION_STATUSES, { value: '', label: 'All' }]}
          />
          <TextInput type="date" aria-label="Due through" placeholder="Due through" value={f.due} onChange={(e) => setF({ due: e.currentTarget.value })} />
        </Group>
        {monthly > 0 && (
          <Text size="sm" c="dimmed">
            Active on this page: <Money value={String(monthly)} /> per month
          </Text>
        )}
      </Group>
      <DataTable<VendorSub>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={canEdit ? (r) => setEditing(r) : undefined}
        empty="No vendor subscriptions yet — add the servers, domains and services you pay for."
        page={data && { total: data.total, limit: LIMIT, offset: Number(f.offset), onOffset: (o) => setF({ offset: String(o) }) }}
        columns={[
          { key: 'due', header: 'Next due', render: (r) => <DateText value={r.next_due_date} /> },
          { key: 'vendor', header: 'Vendor', render: (r) => r.vendor_name },
          {
            key: 'name',
            header: 'Name',
            render: (r) => (
              <Group gap={6}>
                {r.name}
                {r.autopay && (
                  <Badge size="xs" variant="light">
                    Autopay
                  </Badge>
                )}
              </Group>
            ),
          },
          { key: 'for', header: 'For', wide: true, render: (r) => r.service_identifier },
          { key: 'used', header: 'Used by', wide: true, render: (r) => (r.used_by.length ? `${r.used_by.length} client line(s)` : '') },
          { key: 'every', header: 'Every', wide: true, render: (r) => everyMonths(r.interval_months) },
          {
            key: 'status',
            header: 'Status',
            render: (r) => (
              <Badge variant="light" color={SUBSCRIPTION_STATUS_COLORS[r.status]}>
                {labelOf(SUBSCRIPTION_STATUSES, r.status)}
              </Badge>
            ),
          },
          { key: 'amount', header: 'Amount', align: 'right', render: (r) => <Money value={r.amount} /> },
          ...(canEdit
            ? [
                {
                  key: 'pay',
                  header: '',
                  align: 'right' as const,
                  render: (r: VendorSub) =>
                    r.status === 'active' && (
                      <Button
                        size="compact-xs"
                        variant="light"
                        onClick={(e) => {
                          e.stopPropagation()
                          setPaying(r)
                        }}
                      >
                        Paid…
                      </Button>
                    ),
                },
              ]
            : []),
        ]}
      />
      {editing && (
        <VendorSubscriptionForm
          sub={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
          onPay={(s) => {
            setEditing(null)
            setPaying(s)
          }}
        />
      )}
      {paying && <RecordPayment sub={paying} onClose={() => setPaying(null)} />}
    </>
  )
}
