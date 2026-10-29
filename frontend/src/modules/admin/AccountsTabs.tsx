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

import { Badge, Button, Card, Checkbox, Group, Modal, Select, SimpleGrid, Stack, Table, Text, Textarea, TextInput } from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconPlus } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAccounts, useRevenueCategories, useTaxCategories } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { notifyError, notifySaved } from '../../lib/notify'

type Account = Schemas['AccountOut']

function AccountForm({ account, onClose }: { account?: Account; onClose: () => void }) {
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: {
      code: account?.code ?? '',
      name: account?.name ?? '',
      account_type: account?.account_type ?? 'expense',
      description: account?.description ?? '',
      is_active: account?.is_active ?? true,
    },
    validate: { code: (v) => (v.trim() ? null : 'Required'), name: (v) => (v.trim() ? null : 'Required') },
  })
  const save = useMutation({
    mutationFn: async (v: typeof form.values) => {
      const body = { ...v, account_type: v.account_type as Account['account_type'], description: v.description.trim() || null }
      return account
        ? unwrap(await api.PATCH('/api/accounts/{account_id}', { params: { path: { account_id: account.id } }, body }))
        : unwrap(await api.POST('/api/accounts', { body }))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      notifySaved('Account saved')
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={account ? `Edit ${account.code}` : 'New account'}>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <SimpleGrid cols={2}>
            <TextInput label="Code" {...form.getInputProps('code')} />
            <Select
              label="Type"
              data={[
                { value: 'expense', label: 'Expense' },
                { value: 'cogs', label: 'Cost of goods sold' },
                { value: 'revenue', label: 'Revenue' },
              ]}
              {...form.getInputProps('account_type')}
            />
          </SimpleGrid>
          <TextInput label="Name" {...form.getInputProps('name')} />
          <Textarea label="Description" autosize {...form.getInputProps('description')} />
          <Checkbox label="Active" {...form.getInputProps('is_active', { type: 'checkbox' })} />
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

export function AccountsTab() {
  const { isOwner } = useAuth()
  const { data } = useAccounts()
  const [editing, setEditing] = useState<Account | 'new' | null>(null)
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text size="sm" c="dimmed">
          Accounts that expenses are booked to.
        </Text>
        {isOwner && (
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing('new')}>
            New account
          </Button>
        )}
      </Group>
      <Table highlightOnHover={isOwner}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Code</Table.Th>
            <Table.Th>Name</Table.Th>
            <Table.Th>Type</Table.Th>
            <Table.Th>Description</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {data?.map((a) => (
            <Table.Tr
              key={a.id}
              c={a.is_active ? undefined : 'dimmed'}
              style={isOwner ? { cursor: 'pointer' } : undefined}
              onClick={isOwner ? () => setEditing(a) : undefined}
            >
              <Table.Td ff="monospace">{a.code}</Table.Td>
              <Table.Td>
                {a.name} {!a.is_active && <Badge size="xs" color="gray">Inactive</Badge>}
              </Table.Td>
              <Table.Td>{a.account_type === 'cogs' ? 'COGS' : a.account_type}</Table.Td>
              <Table.Td>
                <Text size="sm" lineClamp={1}>
                  {a.description}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {editing && <AccountForm account={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    </Card>
  )
}

function NameList({
  title,
  description,
  rows,
  onAdd,
  onRename,
  onToggle,
  canEdit,
}: {
  title: string
  description: string
  rows: { id: number; name: string; is_active: boolean; code?: string }[]
  onAdd: (name: string) => void
  onRename: (id: number, name: string) => void
  onToggle: (id: number, active: boolean) => void
  canEdit: boolean
}) {
  const [name, setName] = useState('')
  return (
    <Card withBorder>
      <Text fw={600}>{title}</Text>
      <Text size="sm" c="dimmed" mb="xs">
        {description}
      </Text>
      <Stack gap={6}>
        {rows.map((r) => (
          <Group key={r.id} gap="xs" wrap="nowrap">
            <TextInput
              aria-label={`Name of ${r.name}`}
              style={{ flex: 1 }}
              defaultValue={r.name}
              disabled={!canEdit}
              onBlur={(e) => e.currentTarget.value.trim() && e.currentTarget.value !== r.name && onRename(r.id, e.currentTarget.value.trim())}
            />
            {r.code && (
              <Text size="xs" c="dimmed" ff="monospace" w={90}>
                {r.code}
              </Text>
            )}
            <Checkbox label="Active" disabled={!canEdit} checked={r.is_active} onChange={(e) => onToggle(r.id, e.currentTarget.checked)} />
          </Group>
        ))}
        {canEdit && (
          <Group gap="xs">
            <TextInput placeholder="New name" style={{ flex: 1 }} value={name} onChange={(e) => setName(e.currentTarget.value)} />
            <Button
              variant="light"
              disabled={!name.trim()}
              onClick={() => {
                onAdd(name.trim())
                setName('')
              }}
            >
              Add
            </Button>
          </Group>
        )}
      </Stack>
    </Card>
  )
}

export function CategoriesTab() {
  const { canEdit, isOwner } = useAuth()
  const queryClient = useQueryClient()
  const { data: revenue } = useRevenueCategories()
  const { data: tax } = useTaxCategories()
  const done = (key: string) => () => {
    queryClient.invalidateQueries({ queryKey: [key] })
    notifySaved()
  }
  const revenueSave = useMutation({
    mutationFn: async ({ id, body }: { id?: number; body: { name?: string; is_active?: boolean } }) =>
      id
        ? unwrap(await api.PATCH('/api/revenue-categories/{category_id}', { params: { path: { category_id: id } }, body }))
        : unwrap(await api.POST('/api/revenue-categories', { body: { name: body.name!, is_active: true } })),
    onSuccess: done('revenue-categories'),
    onError: notifyError,
  })
  const taxSave = useMutation({
    mutationFn: async ({ id, body }: { id?: number; body: { name?: string; is_active?: boolean } }) =>
      id
        ? unwrap(await api.PATCH('/api/tax/categories/{category_id}', { params: { path: { category_id: id } }, body }))
        : unwrap(
            await api.POST('/api/tax/categories', {
              body: { name: body.name!, code: body.name!.toLowerCase().replace(/[^a-z0-9]+/g, '_'), is_active: true },
            }),
          ),
    onSuccess: done('tax-categories'),
    onError: notifyError,
  })
  return (
    <SimpleGrid cols={{ base: 1, md: 2 }}>
      <NameList
        title="Revenue categories"
        description="Group sales in reports: Hosting, Domains, Development…"
        rows={revenue ?? []}
        canEdit={canEdit}
        onAdd={(name) => revenueSave.mutate({ body: { name } })}
        onRename={(id, name) => revenueSave.mutate({ id, body: { name } })}
        onToggle={(id, is_active) => revenueSave.mutate({ id, body: { is_active } })}
      />
      <NameList
        title="Tax categories"
        description="How items are taxed; set what is taxable where under Sales tax."
        rows={tax ?? []}
        canEdit={isOwner}
        onAdd={(name) => taxSave.mutate({ body: { name } })}
        onRename={(id, name) => taxSave.mutate({ id, body: { name } })}
        onToggle={(id, is_active) => taxSave.mutate({ id, body: { is_active } })}
      />
    </SimpleGrid>
  )
}
