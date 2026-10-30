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

/** Admin -> Asset categories: the list, and the extra fields each one asks for. */

import { ActionIcon, Badge, Button, Checkbox, Group, Modal, NumberInput, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap } from '../../api/client'
import { DataTable } from '../../components/DataTable'
import { PageHeader } from '../../components/ui'
import { ASSET_FIELD_TYPES, labelOf } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { useAssetCategories, type AssetCategory } from './shared'

type Field = AssetCategory['fields'][number]

/** "Renewal date" -> "renewal_date": the stored name of a new field. */
function keyOf(label: string) {
  const key = label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return /^[a-z]/.test(key) ? key.slice(0, 40) : `f_${key}`.slice(0, 40)
}

function CategoryForm({ category, onClose }: { category?: AssetCategory; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(category?.name ?? '')
  const [order, setOrder] = useState<number | ''>(category?.sort_order ?? 100)
  const [active, setActive] = useState(category?.is_active ?? true)
  // Keys of fields that existed when the form opened stay as they were (values are stored by key).
  const [fields, setFields] = useState<(Field & { saved: boolean })[]>(
    (category?.fields ?? []).map((f) => ({ ...f, saved: true })),
  )
  const update = (i: number, change: Partial<Field>) =>
    setFields((all) =>
      all.map((f, n) => (n === i ? { ...f, ...change, key: f.saved || !change.label ? (change.key ?? f.key) : keyOf(change.label) } : f)),
    )
  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name: name.trim(),
        sort_order: Number(order || 0),
        is_active: active,
        fields: fields.filter((f) => f.label.trim()).map(({ key, label, type }) => ({ key, label: label.trim(), type })),
      }
      return category
        ? unwrap(await api.PATCH('/api/asset-categories/{category_id}', { params: { path: { category_id: category.id } }, body }))
        : unwrap(await api.POST('/api/asset-categories', { body }))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['asset-categories'] })
      notifySaved('Category saved')
      onClose()
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/asset-categories/{category_id}', { params: { path: { category_id: category!.id } } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['asset-categories'] })
      notifySaved('Category deleted')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={category ? category.name : 'New asset category'} size="lg">
      <Stack>
        <Group grow>
          <TextInput label="Name" required value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <NumberInput label="Order in lists" value={order} onChange={(v) => setOrder(v === '' ? '' : Number(v))} />
        </Group>
        <Text size="sm" fw={600}>
          Extra fields
        </Text>
        <Text size="xs" c="dimmed">
          Asked for on each asset of this category, and searchable: for example RAM and OS for computers, the license
          key and seats for software. Removing a field keeps the values already entered, hidden.
        </Text>
        {fields.map((f, i) => (
          <Group key={i} gap="xs" wrap="nowrap">
            <TextInput flex={1} aria-label={`Field ${i + 1}`} placeholder="Label, e.g. RAM" value={f.label} onChange={(e) => update(i, { label: e.currentTarget.value })} />
            <Select w={130} aria-label={`Type of field ${i + 1}`} allowDeselect={false} data={ASSET_FIELD_TYPES} value={f.type} onChange={(type) => update(i, { type: (type ?? 'text') as Field['type'] })} />
            <ActionIcon variant="subtle" color="red" aria-label={`Remove field ${i + 1}`} onClick={() => setFields((all) => all.filter((_, n) => n !== i))}>
              <IconTrash size={14} />
            </ActionIcon>
          </Group>
        ))}
        <Group>
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setFields((all) => [...all, { key: '', label: '', type: 'text', saved: false }])}>
            Add field
          </Button>
        </Group>
        {category && <Checkbox label="In use (untick to hide it from new assets)" checked={active} onChange={(e) => setActive(e.currentTarget.checked)} />}
        <Group justify="space-between">
          <div>
            {category && category.assets === 0 && (
              <Button variant="subtle" color="red" loading={remove.isPending} onClick={() => remove.mutate()}>
                Delete
              </Button>
            )}
          </div>
          <Group>
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button disabled={!name.trim()} loading={save.isPending} onClick={() => save.mutate()}>
              Save
            </Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  )
}

export function AssetCategoriesPage() {
  const { data } = useAssetCategories()
  const [editing, setEditing] = useState<AssetCategory | 'new' | null>(null)
  return (
    <>
      <PageHeader
        title="Asset categories"
        subtitle="Kinds of equipment and licenses, and the details each one records"
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>
            New category
          </Button>
        }
      />
      <DataTable<AssetCategory>
        rows={data}
        rowKey={(r) => r.id}
        onRowClick={setEditing}
        columns={[
          {
            key: 'name',
            header: 'Category',
            render: (r) => (
              <>
                {r.name}
                {!r.is_active && <Badge ml="xs" variant="light" color="gray">not in use</Badge>}
              </>
            ),
          },
          {
            key: 'fields',
            header: 'Extra fields',
            wide: true,
            render: (r) => r.fields.map((f) => (f.type === 'text' ? f.label : `${f.label} (${labelOf(ASSET_FIELD_TYPES, f.type).toLowerCase()})`)).join(', '),
          },
          { key: 'assets', header: 'Assets', align: 'right', render: (r) => r.assets },
        ]}
      />
      {editing && <CategoryForm category={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  )
}
