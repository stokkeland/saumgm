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
  ActionIcon,
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Modal,
  MultiSelect,
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
import { IconCalendarDollar, IconPlus, IconTrash } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { DataTable } from '../../components/DataTable'
import { DateText, Money, PageHeader, SearchInput } from '../../components/ui'
import { todayIso } from '../../lib/format'
import { everyMonths, labelOf, SUBSCRIPTION_STATUS_COLORS, SUBSCRIPTION_STATUSES } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'

type Sub = Schemas['SubscriptionOut']
type Item = Schemas['CatalogItemOut']
const LIMIT = 50

function endOfMonth(): string {
  const now = new Date()
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0)
  return `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, '0')}-${String(last.getDate()).padStart(2, '0')}`
}

const optional = (x: string | null | undefined) => (x === null || x === undefined ? ('' as number | '') : Number(x))

interface LineValues {
  key: string
  catalog_item_id: string | null
  description: string
  quantity: number
  price_override: number | ''
  discount_pct: number | ''
  uses: string[]
}

let nextKey = 0
function newLine(values: Partial<LineValues> = {}): LineValues {
  nextKey += 1
  return { key: `line-${nextKey}`, catalog_item_id: null, description: '', quantity: 1, price_override: '', discount_pct: '', uses: [], ...values }
}

/** What a line bills per period, as the server computes it (for the running total). */
function lineTotal(line: LineValues, item: Item | undefined): number {
  const price = line.price_override === '' ? Number(item?.price ?? 0) : line.price_override
  const pct = line.discount_pct === '' ? Number(item?.default_discount_pct ?? 0) : line.discount_pct
  return Math.round(price * (1 - pct / 100) * (line.quantity || 0) * 100) / 100
}

function SubscriptionForm({ sub, onClose }: { sub?: Sub; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: items } = useQuery({
    queryKey: ['catalog-options'],
    queryFn: async () =>
      unwrap(await api.GET('/api/catalog', { params: { query: { active: true, limit: 500 } } })).items,
  })
  const { data: packages } = useQuery({
    queryKey: ['packages', 'active'],
    queryFn: async () => unwrap(await api.GET('/api/packages', { params: { query: { active: true } } })),
  })
  const { data: vendorSubs } = useQuery({
    queryKey: ['vendor-subscription-options'],
    queryFn: async () =>
      unwrap(await api.GET('/api/vendor-subscriptions', { params: { query: { limit: 500 } } })).items,
  })
  const form = useForm({
    initialValues: {
      party_id: sub?.party_id ?? null,
      service_identifier: sub?.service_identifier ?? '',
      billing_interval_months: sub?.billing_interval_months ?? ('' as number | ''),
      start_date: sub?.start_date ?? todayIso(),
      next_bill_date: sub?.next_bill_date ?? '',
      end_date: sub?.end_date ?? '',
      auto_renew: sub?.auto_renew ?? true,
      status: sub?.status ?? 'active',
      notes: sub?.notes ?? '',
      lines: sub
        ? sub.lines.map((l) =>
            newLine({
              catalog_item_id: String(l.catalog_item_id),
              description: l.description,
              quantity: Number(l.quantity),
              price_override: optional(l.price_override),
              discount_pct: optional(l.discount_pct),
              uses: l.uses.map((u) => String(u.vendor_subscription_id)),
            }),
          )
        : [newLine()],
    },
    validate: {
      party_id: (v) => (v ? null : 'Choose a client'),
      lines: {
        catalog_item_id: (v) => (v ? null : 'Choose an item'),
      },
    },
  })
  const v = form.values
  const itemOf = (id: string | null) => items?.find((i) => String(i.id) === id)
  const firstItem = itemOf(v.lines[0]?.catalog_item_id ?? null)
  const total = v.lines.reduce((sum, line) => sum + lineTotal(line, itemOf(line.catalog_item_id)), 0)

  const chooseItem = (index: number, id: string | null) => {
    const line = v.lines[index]
    const before = itemOf(line.catalog_item_id)
    form.setFieldValue(`lines.${index}.catalog_item_id`, id)
    // Keep a description someone typed; follow the item when it was just the item's name.
    if (!line.description || line.description === before?.name) {
      form.setFieldValue(`lines.${index}.description`, itemOf(id)?.name ?? '')
    }
  }

  const fillFromPackage = (id: string | null) => {
    const pkg = packages?.find((p) => String(p.id) === id)
    if (!pkg) return
    const lines = pkg.items.map((i) =>
      newLine({
        catalog_item_id: String(i.catalog_item_id),
        description: i.item_name,
        quantity: Number(i.quantity),
        price_override: optional(i.price),
        discount_pct: optional(i.discount_pct),
      }),
    )
    const kept = v.lines.filter((l) => l.catalog_item_id)
    form.setFieldValue('lines', [...kept, ...lines])
  }

  const save = useMutation({
    mutationFn: async () => {
      const num = (x: number | '') => (x === '' ? null : String(x))
      const body = {
        service_identifier: v.service_identifier.trim() || null,
        billing_interval_months: v.billing_interval_months === '' ? null : v.billing_interval_months,
        start_date: v.start_date,
        next_bill_date: v.next_bill_date || null,
        end_date: v.end_date || null,
        auto_renew: v.auto_renew,
        status: v.status as Sub['status'],
        notes: v.notes.trim() || null,
        lines: v.lines.map((l) => ({
          catalog_item_id: Number(l.catalog_item_id),
          description: l.description.trim() || null,
          quantity: String(l.quantity || 1),
          price_override: num(l.price_override),
          discount_pct: num(l.discount_pct),
          uses: l.uses.map(Number),
        })),
      }
      return sub
        ? unwrap(await api.PATCH('/api/subscriptions/{subscription_id}', { params: { path: { subscription_id: sub.id } }, body }))
        : unwrap(await api.POST('/api/subscriptions', { body: { ...body, party_id: v.party_id! } }))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
      queryClient.invalidateQueries({ queryKey: ['vendor-subscriptions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      notifySaved('Subscription saved')
      onClose()
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE('/api/subscriptions/{subscription_id}', { params: { path: { subscription_id: sub!.id } } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      notifySaved('Subscription deleted')
      onClose()
    },
    onError: notifyError,
  })
  const vendorOptions = (vendorSubs ?? []).map((s) => ({
    value: String(s.id),
    label: `${s.name}${s.service_identifier ? ` (${s.service_identifier})` : ''} - ${s.vendor_name}`,
  }))

  return (
    <Modal opened onClose={onClose} title={sub ? `Subscription: ${sub.party_name}` : 'New subscription'} size={1080}>
      <form onSubmit={form.onSubmit(() => save.mutate())}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 4 }}>
            <ContactSelect
              label="Client"
              role="client"
              required
              disabled={!!sub}
              style={{ gridColumn: 'span 2' }}
              value={v.party_id}
              onChange={(id) => form.setFieldValue('party_id', id)}
              error={form.errors.party_id}
            />
            <TextInput label="For (domain, account, server…)" style={{ gridColumn: 'span 2' }} {...form.getInputProps('service_identifier')} />
            <NumberInput
              label="Every (months)"
              description={!sub && firstItem?.billing_interval_months ? `Empty: ${firstItem.billing_interval_months}` : undefined}
              min={1}
              max={120}
              allowDecimal={false}
              {...form.getInputProps('billing_interval_months')}
            />
            <TextInput type="date" label="Start" required {...form.getInputProps('start_date')} />
            <TextInput type="date" label="Next bill date" description={sub ? undefined : 'Empty: the start date'} {...form.getInputProps('next_bill_date')} />
            <TextInput type="date" label="End" {...form.getInputProps('end_date')} />
            <Select label="Status" data={SUBSCRIPTION_STATUSES} {...form.getInputProps('status')} />
            <Checkbox mt="lg" label="Renews automatically" style={{ gridColumn: 'span 3' }} {...form.getInputProps('auto_renew', { type: 'checkbox' })} />
          </SimpleGrid>

          <Group justify="space-between" align="flex-end">
            <Text size="sm" fw={600}>
              Lines (billed together on one invoice)
            </Text>
            {(packages?.length ?? 0) > 0 && (
              <Select
                w={240}
                size="xs"
                aria-label="Add a package"
                placeholder="Add a package…"
                value={null}
                data={(packages ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
                onChange={fillFromPackage}
              />
            )}
          </Group>
          <Table.ScrollContainer minWidth={900}>
            <Table verticalSpacing={4}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={210}>Item</Table.Th>
                  <Table.Th>Description</Table.Th>
                  <Table.Th w={70}>Qty</Table.Th>
                  <Table.Th w={100}>Price</Table.Th>
                  <Table.Th w={70}>Disc. %</Table.Th>
                  <Table.Th w={220}>Uses</Table.Th>
                  <Table.Th w={36} />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {v.lines.map((line, index) => {
                  const item = itemOf(line.catalog_item_id)
                  return (
                    <Table.Tr key={line.key}>
                      <Table.Td>
                        <Select
                          aria-label={`Item, line ${index + 1}`}
                          searchable
                          data={(items ?? []).map((i) => ({ value: String(i.id), label: i.name }))}
                          value={line.catalog_item_id}
                          onChange={(id) => chooseItem(index, id)}
                          error={form.errors[`lines.${index}.catalog_item_id`]}
                        />
                      </Table.Td>
                      <Table.Td>
                        <TextInput aria-label={`Description, line ${index + 1}`} placeholder={item?.name} {...form.getInputProps(`lines.${index}.description`)} />
                      </Table.Td>
                      <Table.Td>
                        <NumberInput aria-label={`Quantity, line ${index + 1}`} min={0} decimalScale={4} hideControls {...form.getInputProps(`lines.${index}.quantity`)} />
                      </Table.Td>
                      <Table.Td>
                        <NumberInput aria-label={`Price, line ${index + 1}`} placeholder={item ? String(Number(item.price)) : undefined} min={0} decimalScale={4} hideControls {...form.getInputProps(`lines.${index}.price_override`)} />
                      </Table.Td>
                      <Table.Td>
                        <NumberInput aria-label={`Discount, line ${index + 1}`} min={0} max={100} decimalScale={4} hideControls {...form.getInputProps(`lines.${index}.discount_pct`)} />
                      </Table.Td>
                      <Table.Td>
                        <MultiSelect
                          aria-label={`Uses, line ${index + 1}`}
                          placeholder={line.uses.length ? undefined : 'Vendor subscriptions'}
                          searchable
                          data={vendorOptions}
                          {...form.getInputProps(`lines.${index}.uses`)}
                        />
                      </Table.Td>
                      <Table.Td>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          aria-label={`Remove line ${index + 1}`}
                          disabled={v.lines.length === 1}
                          onClick={() => form.removeListItem('lines', index)}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group justify="space-between">
            <Button variant="subtle" size="xs" leftSection={<IconPlus size={14} />} onClick={() => form.insertListItem('lines', newLine())}>
              Add line
            </Button>
            <Text size="sm">
              Per period: <Money value={String(total)} strong />
            </Text>
          </Group>
          {sub && Number(sub.monthly_cost) > 0 && (
            <Text size="sm" c="dimmed">
              Per month: <Money value={sub.monthly_revenue} /> billed, <Money value={sub.monthly_cost} /> share of the vendor
              subscriptions it uses, <Money value={String(Number(sub.monthly_revenue) - Number(sub.monthly_cost))} /> margin.
            </Text>
          )}
          <Textarea label="Notes" autosize {...form.getInputProps('notes')} />
          <Group justify="space-between">
            {sub && !sub.billed ? (
              <Button variant="subtle" color="red" loading={remove.isPending} onClick={() => remove.mutate()}>
                Delete
              </Button>
            ) : (
              <span />
            )}
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

function BillingRun({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [through, setThrough] = useState(endOfMonth())
  const [combine, setCombine] = useState(false)
  const run = useMutation({
    mutationFn: async (dryRun: boolean) =>
      unwrap(await api.POST('/api/subscriptions/billing-run', { body: { through, combine, dry_run: dryRun } })),
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
          Creates a draft invoice for each subscription with periods due up to the date below. Review the drafts, then
          issue them.
        </Text>
        <Group align="flex-end">
          <TextInput type="date" label="Bill everything due through" value={through} onChange={(e) => setThrough(e.currentTarget.value)} />
          <Button variant="light" loading={run.isPending && run.variables} onClick={() => run.mutate(true)}>
            Preview
          </Button>
        </Group>
        <Checkbox
          label="One invoice per client for subscriptions due on the same day"
          checked={combine}
          onChange={(e) => {
            setCombine(e.currentTarget.checked)
            run.reset()
          }}
        />
        {preview &&
          (preview.invoices.length === 0 ? (
            <Alert variant="light">Nothing is due through this date.</Alert>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Client</Table.Th>
                  <Table.Th>Lines</Table.Th>
                  <Table.Th ta="right">Draft total</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {preview.invoices.map((i, n) => (
                  <Table.Tr key={n}>
                    <Table.Td>{i.party_name}</Table.Td>
                    <Table.Td>
                      {i.lines.map((line, k) => (
                        <Text key={k} size="xs">
                          {line}
                        </Text>
                      ))}
                    </Table.Td>
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
        <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Domain, account, item…" />
        <Select
          w={140}
          aria-label="Status"
          value={f.status}
          onChange={(status) => setF({ status: status ?? '' })}
          data={[...SUBSCRIPTION_STATUSES, { value: '', label: 'All' }]}
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
          { key: 'for', header: 'For', render: (r) => r.service_identifier },
          { key: 'lines', header: 'Lines', render: (r) => r.summary },
          { key: 'every', header: 'Every', wide: true, render: (r) => everyMonths(r.billing_interval_months) },
          {
            key: 'status',
            header: 'Status',
            render: (r) => (
              <Badge variant="light" color={SUBSCRIPTION_STATUS_COLORS[r.status]}>
                {labelOf(SUBSCRIPTION_STATUSES, r.status)}
              </Badge>
            ),
          },
          { key: 'price', header: 'Per period', align: 'right', render: (r) => <Money value={r.total} /> },
        ]}
      />
      {editing && <SubscriptionForm sub={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
      {billing && <BillingRun onClose={() => setBilling(false)} />}
    </>
  )
}
