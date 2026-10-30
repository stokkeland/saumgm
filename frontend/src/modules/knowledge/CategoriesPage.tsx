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

/** Knowledge base -> Categories: the tree articles are filed in. */

import { Button, Group, Modal, NumberInput, Select, Stack, Text, TextInput } from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DataTable } from '../../components/DataTable'
import { PageHeader } from '../../components/ui'
import { notifyError, notifySaved } from '../../lib/notify'
import { categoryOptions, useKbCategories, type KbCategory } from './shared'

function CategoryForm({ category, onClose }: { category?: KbCategory; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { data: categories } = useKbCategories()
  const [name, setName] = useState(category?.name ?? '')
  const [parent, setParent] = useState<string | null>(category?.parent_id ? String(category.parent_id) : null)
  const [order, setOrder] = useState<number | ''>(category?.sort_order ?? 0)
  const done = (message: string) => {
    queryClient.invalidateQueries({ queryKey: ['kb-categories'] })
    queryClient.invalidateQueries({ queryKey: ['kb-articles'] })
    notifySaved(message)
    onClose()
  }
  const save = useMutation({
    mutationFn: async () => {
      const body = { name: name.trim(), parent_id: parent ? Number(parent) : null, sort_order: Number(order || 0) }
      return category
        ? unwrap(await api.PATCH('/api/kb/categories/{category_id}', { params: { path: { category_id: category.id } }, body }))
        : unwrap(await api.POST('/api/kb/categories', { body }))
    },
    onSuccess: () => done('Category saved'),
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/kb/categories/{category_id}', { params: { path: { category_id: category!.id } } })),
    onSuccess: () => done('Category deleted'),
    onError: notifyError,
  })
  // A category cannot go inside itself or below it.
  const inside = (c: KbCategory) => category && (c.id === category.id || c.path.startsWith(`${category.path} / `))
  return (
    <Modal opened onClose={onClose} title={category ? category.path : 'New category'}>
      <Stack>
        <TextInput label="Name" required data-autofocus value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Select
          label="Inside"
          placeholder="At the top"
          clearable
          searchable
          data={categoryOptions((categories ?? []).filter((c) => !inside(c)))}
          value={parent}
          onChange={setParent}
        />
        <NumberInput label="Order" description="Lower comes first; the same number sorts by name" value={order} onChange={(v) => setOrder(v === '' ? '' : Number(v))} />
        <Group justify="space-between">
          {category ? (
            <Button variant="subtle" color="red" loading={remove.isPending} onClick={() => remove.mutate()} disabled={category.articles > 0}>
              Delete
            </Button>
          ) : (
            <span />
          )}
          <Group>
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>
              Save
            </Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  )
}

export function KbCategoriesPage() {
  const { canEdit } = useAuth()
  const { data, isFetching } = useKbCategories()
  const [editing, setEditing] = useState<KbCategory | 'new' | null>(null)
  return (
    <>
      <PageHeader
        title="Knowledge base categories"
        subtitle="Folders for articles, as deep as you like: Clients → a client, How-to, Servers…"
        actions={
          canEdit && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>
              New category
            </Button>
          )
        }
      />
      <DataTable<KbCategory>
        rows={data}
        loading={isFetching}
        rowKey={(c) => c.id}
        onRowClick={canEdit ? (c) => setEditing(c) : undefined}
        empty="No categories yet."
        columns={[
          {
            key: 'name',
            header: 'Category',
            render: (c) => (
              <Text size="sm" pl={16 * (c.path.split(' / ').length - 1)}>
                {c.name}
              </Text>
            ),
          },
          { key: 'articles', header: 'Articles', render: (c) => c.articles },
          { key: 'order', header: 'Order', render: (c) => c.sort_order },
        ]}
      />
      {editing && <CategoryForm category={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </>
  )
}
