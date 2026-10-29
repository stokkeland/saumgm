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
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconCalendarDollar, IconPlus } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { DataTable } from '../../components/DataTable'
import { DateText, Money, PageHeader, SearchInput } from '../../components/ui'
import { todayIso } from '../../lib/format'
import { notifyError, notifySaved } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'

type Sub = Schemas['SubscriptionOut']
const LIMIT = 50
const STATUS_COLORS: Record<string, string> = { active: 'green', paused: 'yellow', cancelled: 'gray' }

function endOfMonth(): string {
  const now = new Date()
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  return `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, '0')}-${String(last.getDate()).padStart(2, '0')}`
}

function SubscriptionForm({ sub, onClose }: { sub?: Sub; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: items } = useQuery({
    queryKey: ['catalog-options'],
    queryFn: async () =>
      unwrap(await api.GET('/api/catalog', { params: { query: { active: true, limit: 500 } } })).items,
  })
  const form = useForm({
    initialValues: {
      party_id: sub?.party_id ?? null,
      catalog_item_id: sub ? String(sub.catalog_item_id) : null,
      service_identifier: sub?.service_identifier ?? '',
      quantity: Number(sub?.quantity ?? 1),
      price_override: sub?.price_override === null || sub?.price_override === undefined ? ('' as number | '') : Number(sub.price_override),
      discount_pct: sub?.discount_pct === null || sub?.discount_pct === undefined ? ('' as number | '') : Number(sub.discount_pct),
      billing_interval_months: sub?.billing_interval_months ?? ('' as number | ''),
      start_date: sub?.start_date ?? todayIso(),
      next_bill_date: sub?.next_bill_date ?? '',
      end_date: sub?.end_date ?? '',
      auto_renew: sub?.auto_renew ?? true,
      status: sub?.status ?? 'active',
      vendor_party_id: sub?.vendor_party_id ?? null,
      vendor_renewal_date: sub?.vendor_renewal_date ?? '',
      unit_cost: sub?.unit_cost === null || sub?.unit_cost === undefined ? ('' as number | '') : Number(sub.unit_cost),
      notes: sub?.notes ?? '',
    },
    validate: {
      party_id: (v) => (v ? null : 'Choose a client'),
      catalog_item_id: (v) => (v ? null : 'Choose an item'),
    },
  })
  const v = form.values
  const item = items?.find((i) => String(i.id) === v.catalog_item_id)
  const save = useMutation({
    mutationFn: async () => {
      const num = (x: number | '') => (x === '' ? null : String(x))
      const body = {
        catalog_item_id: Number(v.catalog_item_id),
        service_identifier: v.service_identifier.trim() || null,
        quantity: String(v.quantity || 1),
        price_override: num(v.price_override),
        discount_pct: num(v.discount_pct),
        billing_interval_months: v.billing_interval_months === '' ? null : v.billing_interval_months,
        start_date: v.start_date,
        next_bill_date: v.next_bill_date || null,
        end_date: v.end_date || null,
        auto_renew: v.auto_renew,
        status: v.status as Sub['status'],
        vendor_party_id: v.vendor_party_id,
        vendor_renewal_date: v.vendor_renewal_date || null,
        unit_cost: num(v.unit_cost),
        notes: v.notes.trim() || null,
      }
      return sub
        ? unwrap(await api.PATCH('/api/subscriptions/{subscription_id}', { params: { path: { subscription_id: sub.id } }, body }))
        : unwrap(await api.POST('/api/subscriptions', { body: { ...body, party_id: v.party_id! } }))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      notifySaved('Subscription saved')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={sub ? 'Edit subscription' : 'New subscription'} size="lg">
      <form onSubmit={form.onSubmit(() => save.mutate())}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <ContactSelect label="Client" role="client" required disabled={!!sub} value={v.party_id} onChange={(id) => form.setFieldValue('party_id', id)} error={form.errors.party_id} />
            <Select
              label="Item"
              required
              searchable
              data={(items ?? []).map((i) => ({ value: String(i.id), label: i.name }))}
              {...form.getInputProps('catalog_item_id')}
            />
            <TextInput label="For (domain, account, server…)" {...form.getInputProps('service_identifier')} />
            <Select
              label="Status"
              data={[
                { value: 'active', label: 'Active' },
                { value: 'paused', label: 'Paused' },
                { value: 'cancelled', label: 'Cancelled' },
              ]}
              {...form.getInputProps('status')}
            />
            <NumberInput label="Quantity" min={0} decimalScale={4} {...form.getInputProps('quantity')} />
            <NumberInput
              label="Price per period"
              description={item ? `Empty: catalog price ${item.price}` : undefined}
              min={0}
              decimalScale={4}
              {...form.getInputProps('price_override')}
            />
            <NumberInput label="Discount %" min={0} max={100} decimalScale={4} {...form.getInputProps('discount_pct')} />
            <NumberInput
              label="Every (months)"
              description={item?.billing_interval_months ? `Empty: ${item.billing_interval_months}` : undefined}
              min={1}
              max={120}
              allowDecimal={false}
              {...form.getInputProps('billing_interval_months')}
            />
            <TextInput type="date" label="Start" required {...form.getInputProps('start_date')} />
            <TextInput type="date" label="Next bill date" description={sub ? undefined : 'Empty: the start date'} {...form.getInputProps('next_bill_date')} />
            <TextInput type="date" label="End" {...form.getInputProps('end_date')} />
            <Checkbox mt="lg" label="Renews automatically" {...form.getInputProps('auto_renew', { type: 'checkbox' })} />
          </SimpleGrid>
          <Text size="sm" fw={600}>
            Vendor side (optional)
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <ContactSelect label="Vendor" role="vendor" value={v.vendor_party_id} onChange={(id) => form.setFieldValue('vendor_party_id', id)} />
            <TextInput type="date" label="Vendor renewal" {...form.getInputProps('vendor_renewal_date')} />
            <NumberInput label="Our cost" min={0} decimalScale={4} {...form.getInputProps('unit_cost')} />
          </SimpleGrid>
          <Textarea label="Notes" autosize {...form.getInputProps('notes')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

function BillingRun({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [through, setThrough] = useState(endOfMonth())
  const run = useMutation({
    mutationFn: async (dryRun: boolean) =>
      unwrap(await api.POST('/api/subscriptions/billing-run', { body: { through, dry_run: dryRun } })),
    onSuccess: (result) => {
      if (!result.dry_run) {
        queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
        queryClient.invalidateQueries({ queryKey: ['invoices'] })
        queryClient.invalidateQueries({ queryKey: ['dashboard'] })
        notifySaved(`${result.invoices.length} draft invoice(s) created`)
        onClose()
        navigate('/invoices?view=draft')
      }
    },
    onError: notifyError,
  })
  const preview = run.data?.dry_run ? run.data : null
  return (
    <Modal opened onClose={onClose} title="Bill subscriptions" size="lg">
      <Stack>
        <Text size="sm">
          Creates one draft invoice per client for every subscription period due up to the date
          below. Review the drafts, then issue them.
        </Text>
        <Group align="flex-end">
          <TextInput type="date" label="Bill everything due through" value={through} onChange={(e) => setThrough(e.currentTarget.value)} />
          <Button variant="light" loading={run.isPending && run.variables} onClick={() => run.mutate(true)}>
            Preview
          </Button>
        </Group>
        {preview &&
          (preview.invoices.length === 0 ? (
            <Alert variant="light">Nothing is due through this date.</Alert>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Client</Table.Th>
                  <Table.Th ta="right">Draft total</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {preview.invoices.map((i) => (
                  <Table.Tr key={i.party_id}>
                    <Table.Td>{i.party_name}</Table.Td>
                    <Table.Td ta="right">
                      <Money value={i.total} />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          ))}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!preview?.invoices.length} loading={run.isPending && !run.variables} onClick={() => run.mutate(false)}>
            Create draft invoices
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export function SubscriptionsPage() {
  const { canEdit } = useAuth()
  const [editing, setEditing] = useState<Sub | 'new' | null>(null)
  const [billing, setBilling] = useState(false)
  const [f, setF] = useUrlState({ q: '', status: 'active', due: '', offset: '0' })
  const { data, isFetching } = useQuery({
    queryKey: ['subscriptions', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/subscriptions', {
          params: {
            query: {
              q: f.q || undefined,
              status: (f.status || undefined) as Sub['status'] | undefined,
              due_through: f.due || undefined,
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
        title="Subscriptions"
        subtitle="Recurring services billed to clients"
        actions={
          canEdit && (
            <>
              <Button variant="light" leftSection={<IconCalendarDollar size={16} />} onClick={() => setBilling(true)}>
                Bill subscriptions
              </Button>
              <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>
                New subscription
              </Button>
            </>
          )
        }
      />
      <Group mb="sm" gap="sm">
        <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Domain, account, server…" />
        <Select
          w={140}
          value={f.status}
          onChange={(status) => setF({ status: status ?? '' })}
          data={[
            { value: 'active', label: 'Active' },
            { value: 'paused', label: 'Paused' },
            { value: 'cancelled', label: 'Cancelled' },
            { value: '', label: 'All' },
          ]}
        />
        <TextInput type="date" aria-label="Due through" placeholder="Due through" value={f.due} onChange={(e) => setF({ due: e.currentTarget.value })} />
      </Group>
      <DataTable<Sub>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={canEdit ? (r) => setEditing(r) : undefined}
        empty="No subscriptions yet — add one for each client's hosting, domains or support agreement."
        page={data && { total: data.total, limit: LIMIT, offset: Number(f.offset), onOffset: (o) => setF({ offset: String(o) }) }}
        columns={[
          { key: 'next', header: 'Next bill', render: (r) => <DateText value={r.next_bill_date} /> },
          { key: 'client', header: 'Client', render: (r) => r.party_name },
          { key: 'item', header: 'Item', render: (r) => r.item_name },
          { key: 'for', header: 'For', render: (r) => r.service_identifier },
          { key: 'every', header: 'Every', wide: true, render: (r) => `${r.billing_interval_months} mo.` },
          { key: 'status', header: 'Status', render: (r) => <Badge variant="light" color={STATUS_COLORS[r.status]}>{r.status}</Badge> },
          { key: 'price', header: 'Per period', align: 'right', render: (r) => <Money value={String(Number(r.unit_price) * Number(r.quantity))} /> },
        ]}
      />
      {editing && <SubscriptionForm sub={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
      {billing && <BillingRun onClose={() => setBilling(false)} />}
    </>
  )
}
