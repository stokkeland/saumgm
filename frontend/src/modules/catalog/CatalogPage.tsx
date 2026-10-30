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
  Badge,
  Button,
  Checkbox,
  Group,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconPlus } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAccounts, useRevenueCategories, useTaxCategories } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { DataTable } from '../../components/DataTable'
import { Money, PageHeader, SearchInput } from '../../components/ui'
import { ITEM_TYPES, labelOf } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'
import { PackagesPanel } from './Packages'

type Item = Schemas['CatalogItemOut']
const LIMIT = 50

function ItemForm({ item, onClose }: { item?: Item; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: taxCategories } = useTaxCategories()
  const { data: revenueCategories } = useRevenueCategories()
  const { data: accounts } = useAccounts()
  const form = useForm({
    initialValues: {
      name: item?.name ?? '',
      sku: item?.sku ?? '',
      item_type: item?.item_type ?? 'service_fixed',
      unit: item?.unit ?? '',
      price: Number(item?.price ?? 0),
      default_discount_pct: Number(item?.default_discount_pct ?? 0),
      tax_category_id: item?.tax_category_id ? String(item.tax_category_id) : null,
      revenue_category_id: item?.revenue_category_id ? String(item.revenue_category_id) : null,
      billing_interval_months: item?.billing_interval_months ?? ('' as number | ''),
      billing_timing: item?.billing_timing ?? null,
      default_vendor_id: item?.default_vendor_id ?? null,
      unit_cost: item?.unit_cost === null || item?.unit_cost === undefined ? ('' as number | '') : Number(item.unit_cost),
      cogs_account_id: item?.cogs_account_id ? String(item.cogs_account_id) : null,
      is_active: item?.is_active ?? true,
      description: item?.description ?? '',
    },
    validate: {
      name: (v) => (v.trim() ? null : 'Required'),
      billing_interval_months: (v, values) =>
        values.item_type === 'subscription' && !v ? 'Subscriptions need a billing interval' : null,
    },
  })
  const v = form.values
  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name: v.name.trim(),
        sku: v.sku.trim() || null,
        item_type: v.item_type as Item['item_type'],
        unit: v.unit.trim() || null,
        price: String(v.price || 0),
        default_discount_pct: String(v.default_discount_pct || 0),
        tax_category_id: v.tax_category_id ? Number(v.tax_category_id) : null,
        revenue_category_id: v.revenue_category_id ? Number(v.revenue_category_id) : null,
        billing_interval_months: v.billing_interval_months === '' ? null : v.billing_interval_months,
        billing_timing: v.billing_timing as Item['billing_timing'],
        default_vendor_id: v.default_vendor_id,
        unit_cost: v.unit_cost === '' ? null : String(v.unit_cost),
        cogs_account_id: v.cogs_account_id ? Number(v.cogs_account_id) : null,
        is_active: v.is_active,
        description: v.description.trim() || null,
      }
      return item
        ? unwrap(await api.PATCH('/api/catalog/{item_id}', { params: { path: { item_id: item.id } }, body }))
        : unwrap(await api.POST('/api/catalog', { body }))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
      queryClient.invalidateQueries({ queryKey: ['catalog-options'] })
      notifySaved('Item saved')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={item ? `Edit ${item.name}` : 'New catalog item'} size="lg">
      <form onSubmit={form.onSubmit(() => save.mutate())}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <TextInput label="Name" required style={{ gridColumn: 'span 2' }} {...form.getInputProps('name')} />
            <TextInput label="SKU" {...form.getInputProps('sku')} />
            <Select label="Type" data={ITEM_TYPES} {...form.getInputProps('item_type')} />
            <TextInput label="Unit" placeholder="ea, hour, year…" {...form.getInputProps('unit')} />
            <NumberInput label="Price" min={0} decimalScale={4} {...form.getInputProps('price')} />
            <NumberInput label="Default discount %" min={0} max={100} decimalScale={4} {...form.getInputProps('default_discount_pct')} />
            <Select label="Tax category" placeholder="Taxable" clearable data={(taxCategories ?? []).map((c) => ({ value: String(c.id), label: c.name }))} {...form.getInputProps('tax_category_id')} />
            <Select label="Revenue category" clearable data={(revenueCategories ?? []).map((c) => ({ value: String(c.id), label: c.name }))} {...form.getInputProps('revenue_category_id')} />
          </SimpleGrid>
          {v.item_type === 'subscription' && (
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <NumberInput label="Billing interval (months)" min={1} max={120} allowDecimal={false} {...form.getInputProps('billing_interval_months')} />
              <Select
                label="Billed"
                data={[
                  { value: 'advance', label: 'In advance' },
                  { value: 'arrears', label: 'In arrears' },
                ]}
                placeholder="In advance"
                clearable
                {...form.getInputProps('billing_timing')}
              />
            </SimpleGrid>
          )}
          <Text size="sm" fw={600}>
            Cost (for resold items)
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <ContactSelect label="Usual vendor" role="vendor" value={v.default_vendor_id} onChange={(id) => form.setFieldValue('default_vendor_id', id)} />
            <NumberInput label="Unit cost" min={0} decimalScale={4} {...form.getInputProps('unit_cost')} />
            <Select label="Cost account" clearable searchable data={(accounts ?? []).map((a) => ({ value: String(a.id), label: `${a.code} ${a.name}` }))} {...form.getInputProps('cogs_account_id')} />
          </SimpleGrid>
          <Textarea label="Description" autosize {...form.getInputProps('description')} />
          <Checkbox label="Active (offered on new invoices)" {...form.getInputProps('is_active', { type: 'checkbox' })} />
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

export function CatalogPage() {
  const { canEdit } = useAuth()
  const [editing, setEditing] = useState<Item | 'new' | null>(null)
  const [f, setF] = useUrlState({ tab: 'items', q: '', type: '', active: 'true', offset: '0' })
  const { data, isFetching } = useQuery({
    queryKey: ['catalog', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/catalog', {
          params: {
            query: {
              q: f.q || undefined,
              item_type: (f.type || undefined) as Item['item_type'] | undefined,
              active: f.active === '' ? undefined : f.active === 'true',
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
        title="Catalog"
        subtitle="Products and services you sell"
        actions={
          canEdit &&
          f.tab === 'items' && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>
              New item
            </Button>
          )
        }
      />
      <Tabs value={f.tab} onChange={(tab) => setF({ tab: tab ?? 'items' })} mb="md">
        <Tabs.List>
          <Tabs.Tab value="items">Items</Tabs.Tab>
          <Tabs.Tab value="packages">Packages</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {f.tab === 'packages' ? (
        <PackagesPanel />
      ) : (
        <>
          <Group mb="sm" gap="sm">
            <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Name, SKU, description" />
            <Select w={180} value={f.type} onChange={(type) => setF({ type: type ?? '' })} data={[{ value: '', label: 'All types' }, ...ITEM_TYPES]} />
            <Select
              w={130}
              value={f.active}
              onChange={(active) => setF({ active: active ?? '' })}
              data={[
                { value: 'true', label: 'Active' },
                { value: 'false', label: 'Inactive' },
                { value: '', label: 'All' },
              ]}
            />
          </Group>
          <DataTable<Item>
            rows={data?.items}
            loading={isFetching}
            rowKey={(r) => r.id}
            onRowClick={canEdit ? (r) => setEditing(r) : undefined}
            page={data && { total: data.total, limit: LIMIT, offset: Number(f.offset), onOffset: (o) => setF({ offset: String(o) }) }}
            columns={[
              { key: 'sku', header: 'SKU', render: (r) => r.sku },
              {
                key: 'name',
                header: 'Name',
                render: (r) => (
                  <Group gap={6}>
                    {r.name}
                    {!r.is_active && <Badge size="xs" color="gray">Inactive</Badge>}
                  </Group>
                ),
              },
              { key: 'type', header: 'Type', render: (r) => labelOf(ITEM_TYPES, r.item_type) },
              {
                key: 'interval',
                header: 'Billing',
                wide: true,
                render: (r) => (r.billing_interval_months ? `every ${r.billing_interval_months} mo.` : ''),
              },
              { key: 'unit', header: 'Unit', wide: true, render: (r) => r.unit },
              { key: 'disc', header: 'Disc. %', align: 'right', wide: true, render: (r) => (Number(r.default_discount_pct) ? Number(r.default_discount_pct) : '') },
              { key: 'price', header: 'Price', align: 'right', render: (r) => <Money value={r.price} /> },
            ]}
          />
        </>
      )}
      {editing && <ItemForm item={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  )
}
