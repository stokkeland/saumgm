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

/** Packages: named sets of catalog items that fill a new subscription's lines. */

import { ActionIcon, Badge, Button, Checkbox, Group, Modal, NumberInput, Select, Stack, Table, Text, Textarea, TextInput } from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DataTable } from '../../components/DataTable'
import { Money } from '../../components/ui'
import { notifyError, notifySaved } from '../../lib/notify'

type Package = Schemas['PackageOut']

interface ItemValues {
  key: string
  catalog_item_id: string | null
  quantity: number
  price: number | ''
  discount_pct: number | ''
}

let nextKey = 0
function newItem(values: Partial<ItemValues> = {}): ItemValues {
  nextKey += 1
  return { key: `item-${nextKey}`, catalog_item_id: null, quantity: 1, price: '', discount_pct: '', ...values }
}

const optional = (x: string | null | undefined) => (x === null || x === undefined ? ('' as number | '') : Number(x))

function PackageForm({ pkg, onClose }: { pkg?: Package; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: items } = useQuery({
    queryKey: ['catalog-options'],
    queryFn: async () =>
      unwrap(await api.GET('/api/catalog', { params: { query: { active: true, limit: 500 } } })).items,
  })
  const form = useForm({
    initialValues: {
      name: pkg?.name ?? '',
      description: pkg?.description ?? '',
      is_active: pkg?.is_active ?? true,
      items: pkg
        ? pkg.items.map((i) =>
            newItem({
              catalog_item_id: String(i.catalog_item_id),
              quantity: Number(i.quantity),
              price: optional(i.price),
              discount_pct: optional(i.discount_pct),
            }),
          )
        : [newItem(), newItem()],
    },
    validate: {
      name: (v) => (v.trim() ? null : 'Required'),
      items: { catalog_item_id: (v) => (v ? null : 'Choose an item') },
    },
  })
  const v = form.values
  const save = useMutation({
    mutationFn: async () => {
      const num = (x: number | '') => (x === '' ? null : String(x))
      const body = {
        name: v.name.trim(),
        description: v.description.trim() || null,
        is_active: v.is_active,
        items: v.items.map((i) => ({
          catalog_item_id: Number(i.catalog_item_id),
          quantity: String(i.quantity || 1),
          price: num(i.price),
          discount_pct: num(i.discount_pct),
        })),
      }
      return pkg
        ? unwrap(await api.PATCH('/api/packages/{package_id}', { params: { path: { package_id: pkg.id } }, body }))
        : unwrap(await api.POST('/api/packages', { body }))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packages'] })
      notifySaved('Package saved')
      onClose()
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE('/api/packages/{package_id}', { params: { path: { package_id: pkg!.id } } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packages'] })
      notifySaved('Package deleted')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={pkg ? `Edit ${pkg.name}` : 'New package'} size="lg">
      <form onSubmit={form.onSubmit(() => save.mutate())}>
        <Stack>
          <TextInput label="Name" placeholder="Hosting + domain" required {...form.getInputProps('name')} />
          <Table verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Item</Table.Th>
                <Table.Th w={80}>Qty</Table.Th>
                <Table.Th w={110}>Price</Table.Th>
                <Table.Th w={80}>Disc. %</Table.Th>
                <Table.Th w={36} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {v.items.map((entry, index) => {
                const item = items?.find((i) => String(i.id) === entry.catalog_item_id)
                return (
                  <Table.Tr key={entry.key}>
                    <Table.Td>
                      <Select
                        aria-label={`Item ${index + 1}`}
                        searchable
                        data={(items ?? []).map((i) => ({ value: String(i.id), label: i.name }))}
                        {...form.getInputProps(`items.${index}.catalog_item_id`)}
                      />
                    </Table.Td>
                    <Table.Td>
                      <NumberInput aria-label={`Quantity ${index + 1}`} min={0} decimalScale={4} hideControls {...form.getInputProps(`items.${index}.quantity`)} />
                    </Table.Td>
                    <Table.Td>
                      <NumberInput aria-label={`Price ${index + 1}`} placeholder={item ? String(Number(item.price)) : undefined} min={0} decimalScale={4} hideControls {...form.getInputProps(`items.${index}.price`)} />
                    </Table.Td>
                    <Table.Td>
                      <NumberInput aria-label={`Discount ${index + 1}`} min={0} max={100} decimalScale={4} hideControls {...form.getInputProps(`items.${index}.discount_pct`)} />
                    </Table.Td>
                    <Table.Td>
                      <ActionIcon variant="subtle" color="red" aria-label={`Remove item ${index + 1}`} disabled={v.items.length === 1} onClick={() => form.removeListItem('items', index)}>
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
          <Group>
            <Button variant="subtle" size="xs" leftSection={<IconPlus size={14} />} onClick={() => form.insertListItem('items', newItem())}>
              Add item
            </Button>
          </Group>
          <Text size="xs" c="dimmed">
            An empty price uses the catalog price. Subscriptions keep their own lines: changing a package later does not
            change them.
          </Text>
          <Textarea label="Description" autosize {...form.getInputProps('description')} />
          <Checkbox label="Active (offered on new subscriptions)" {...form.getInputProps('is_active', { type: 'checkbox' })} />
          <Group justify="space-between">
            {pkg ? (
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

export function PackagesPanel() {
  const { canEdit } = useAuth()
  const [editing, setEditing] = useState<Package | 'new' | null>(null)
  const { data, isFetching } = useQuery({
    queryKey: ['packages', 'all'],
    queryFn: async () => unwrap(await api.GET('/api/packages')),
  })
  return (
    <>
      {canEdit && (
        <Group justify="flex-end" mb="sm">
          <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>
            New package
          </Button>
        </Group>
      )}
      <DataTable<Package>
        rows={data}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={canEdit ? (r) => setEditing(r) : undefined}
        empty="No packages yet — a package (such as hosting + domain) fills a new subscription's lines in one go."
        columns={[
          {
            key: 'name',
            header: 'Package',
            render: (r) => (
              <Group gap={6}>
                {r.name}
                {!r.is_active && (
                  <Badge size="xs" color="gray">
                    Inactive
                  </Badge>
                )}
              </Group>
            ),
          },
          { key: 'items', header: 'Items', render: (r) => r.items.map((i) => (Number(i.quantity) === 1 ? i.item_name : `${Number(i.quantity)} × ${i.item_name}`)).join(', ') },
          { key: 'total', header: 'Price', align: 'right', render: (r) => <Money value={r.total} /> },
        ]}
      />
      {editing && <PackageForm pkg={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  )
}
