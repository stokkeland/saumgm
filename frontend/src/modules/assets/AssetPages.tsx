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
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  FileButton,
  Group,
  Loader,
  MultiSelect,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconPaperclip, IconPlus, IconTrash } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { api, send, unwrap } from '../../api/client'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { DataTable } from '../../components/DataTable'
import { HistoryPanel } from '../../components/HistoryPanel'
import { DateText, PageHeader, SearchInput } from '../../components/ui'
import { ASSET_STATUS_COLORS, ASSET_STATUSES, labelOf } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'
import { useAssetCategories, type Asset, type AssetCategory } from './shared'

const LIMIT = 50
// Lists show the equipment still around unless asked otherwise.
const CURRENT = 'in_use,in_stock,in_repair'

export function AssetStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="light" color={ASSET_STATUS_COLORS[status]}>
      {labelOf(ASSET_STATUSES, status)}
    </Badge>
  )
}

function soon(day: string | null | undefined) {
  if (!day) return false
  const days = (new Date(day).getTime() - Date.now()) / 86_400_000
  return days < 30
}

export function AssetsPage() {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const { data: categories } = useAssetCategories()
  const [f, setF] = useUrlState({ q: '', category: '', status: CURRENT, owner: '', offset: '0' })
  const { data, isFetching } = useQuery({
    queryKey: ['assets', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/assets', {
          params: {
            query: {
              q: f.q || undefined,
              category_id: f.category ? Number(f.category) : undefined,
              status: f.status ? (f.status.split(',') as Asset['status'][]) : undefined,
              owner_party_id: f.owner ? Number(f.owner) : undefined,
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
        title="Assets"
        subtitle="Equipment and licenses: your own and what you manage for clients"
        actions={
          canEdit && (
            <Button component={Link} to="/assets/new" leftSection={<IconPlus size={16} />}>
              New asset
            </Button>
          )
        }
      />
      <Group mb="sm" gap="sm" align="flex-start">
        <SearchInput value={f.q} onChange={(q) => setF({ q })} placeholder="Tag, name, serial, IP, person…" />
        <Select
          w={180}
          aria-label="Category"
          placeholder="Any category"
          clearable
          value={f.category || null}
          onChange={(category) => setF({ category: category ?? '' })}
          data={(categories ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
        />
        <MultiSelect
          w={300}
          aria-label="Status"
          placeholder="Any status"
          value={f.status ? f.status.split(',') : []}
          onChange={(values) => setF({ status: values.join(',') })}
          data={ASSET_STATUSES}
        />
        <ContactSelect
          w={220}
          aria-label="Owner"
          placeholder="Any owner"
          value={f.owner ? Number(f.owner) : null}
          onChange={(id) => setF({ owner: id ? String(id) : '' })}
        />
      </Group>
      <DataTable<Asset>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/assets/${r.id}`)}
        empty="No assets. Add your equipment and licenses, and the equipment you look after for clients."
        page={data && { total: data.total, limit: LIMIT, offset: Number(f.offset), onOffset: (o) => setF({ offset: String(o) }) }}
        columns={[
          { key: 'tag', header: 'Tag', render: (r) => r.tag },
          { key: 'name', header: 'Name', wide: true, render: (r) => r.name },
          { key: 'cat', header: 'Category', render: (r) => r.category_name },
          { key: 'model', header: 'Make / model', render: (r) => [r.manufacturer, r.model].filter(Boolean).join(' ') },
          { key: 'owner', header: 'Owner', render: (r) => r.owner_name },
          { key: 'where', header: 'Location / person', render: (r) => [r.location, r.assigned_to].filter(Boolean).join(' · ') },
          {
            key: 'warranty',
            header: 'Warranty',
            render: (r) =>
              r.warranty_expires && (
                <Text span size="sm" c={soon(r.warranty_expires) ? 'red' : undefined}>
                  <DateText value={r.warranty_expires} />
                </Text>
              ),
          },
          { key: 'status', header: 'Status', render: (r) => <AssetStatusBadge status={r.status} /> },
        ]}
      />
    </>
  )
}

/** The value inputs for a category's extra fields. */
function ExtraFields({
  category,
  values,
  disabled,
  onChange,
}: {
  category: AssetCategory | undefined
  values: Record<string, unknown>
  disabled: boolean
  onChange: (key: string, value: unknown) => void
}) {
  if (!category?.fields.length) return null
  return (
    <SimpleGrid cols={{ base: 1, sm: 3 }}>
      {category.fields.map((field) => {
        const value = values[field.key]
        if (field.type === 'bool')
          return (
            <Checkbox
              key={field.key}
              mt="xl"
              label={field.label}
              disabled={disabled}
              checked={value === true}
              onChange={(e) => onChange(field.key, e.currentTarget.checked)}
            />
          )
        if (field.type === 'number')
          return (
            <NumberInput
              key={field.key}
              label={field.label}
              disabled={disabled}
              value={typeof value === 'number' ? value : ''}
              onChange={(v) => onChange(field.key, v === '' ? null : Number(v))}
            />
          )
        return (
          <TextInput
            key={field.key}
            type={field.type === 'date' ? 'date' : 'text'}
            label={field.label}
            disabled={disabled}
            value={value == null ? '' : String(value)}
            onChange={(e) => onChange(field.key, e.currentTarget.value)}
          />
        )
      })}
    </SimpleGrid>
  )
}

function AssetForm({ asset }: { asset?: Asset }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params] = useSearchParams()
  const { canEdit } = useAuth()
  const { data: categories } = useAssetCategories()
  const [v, setV] = useState({
    tag: asset?.tag ?? '',
    name: asset?.name ?? '',
    category_id: asset?.category_id ? String(asset.category_id) : null,
    status: asset?.status ?? 'in_use',
    manufacturer: asset?.manufacturer ?? '',
    model: asset?.model ?? '',
    serial_number: asset?.serial_number ?? '',
    owner_party_id: asset?.owner_party_id ?? (params.get('owner') ? Number(params.get('owner')) : null),
    location: asset?.location ?? '',
    assigned_to: asset?.assigned_to ?? '',
    purchase_date: asset?.purchase_date ?? '',
    purchase_price: asset?.purchase_price ? Number(asset.purchase_price) : ('' as number | ''),
    vendor_party_id: asset?.vendor_party_id ?? null,
    warranty_expires: asset?.warranty_expires ?? '',
    support_ends: asset?.support_ends ?? '',
    notes: asset?.notes ?? '',
  })
  const [attributes, setAttributes] = useState<Record<string, unknown>>(asset?.attributes ?? {})
  const set = (change: Partial<typeof v>) => setV((old) => ({ ...old, ...change }))
  const category = categories?.find((c) => String(c.id) === v.category_id)
  const save = useMutation({
    mutationFn: async () => {
      const keys = new Set(category?.fields.map((f) => f.key) ?? [])
      const body = {
        tag: v.tag.trim() || null,
        name: v.name.trim(),
        category_id: v.category_id ? Number(v.category_id) : null,
        status: v.status as Asset['status'],
        manufacturer: v.manufacturer.trim() || null,
        model: v.model.trim() || null,
        serial_number: v.serial_number.trim() || null,
        owner_party_id: v.owner_party_id,
        location: v.location.trim() || null,
        assigned_to: v.assigned_to.trim() || null,
        purchase_date: v.purchase_date || null,
        purchase_price: v.purchase_price === '' ? null : String(v.purchase_price),
        vendor_party_id: v.vendor_party_id,
        warranty_expires: v.warranty_expires || null,
        support_ends: v.support_ends || null,
        notes: v.notes.trim() || null,
        attributes: Object.fromEntries(
          Object.entries(attributes).filter(([k]) => keys.has(k)),
        ) as Asset['attributes'],
      }
      return asset
        ? unwrap(await api.PATCH('/api/assets/{asset_id}', { params: { path: { asset_id: asset.id } }, body }))
        : unwrap(await api.POST('/api/assets', { body }))
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ['assets'] })
      queryClient.setQueryData(['asset', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['reminders'] })
      notifySaved(`Asset ${saved.tag} saved`)
      if (!asset) navigate(`/assets/${saved.id}`, { replace: true })
    },
    onError: notifyError,
  })
  const disabled = !canEdit
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <Stack>
        <Card withBorder>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <TextInput label="Name" required disabled={disabled} placeholder="Office NAS, Jane's laptop…" value={v.name} onChange={(e) => set({ name: e.currentTarget.value })} />
            <TextInput label="Tag" disabled={disabled} placeholder="Next number (A-0001…)" value={v.tag} onChange={(e) => set({ tag: e.currentTarget.value })} />
            <Select
              label="Category"
              disabled={disabled}
              clearable
              data={(categories ?? [])
                .filter((c) => c.is_active || String(c.id) === v.category_id)
                .map((c) => ({ value: String(c.id), label: c.name }))}
              value={v.category_id}
              onChange={(category_id) => set({ category_id })}
            />
            <TextInput label="Manufacturer" disabled={disabled} value={v.manufacturer} onChange={(e) => set({ manufacturer: e.currentTarget.value })} />
            <TextInput label="Model" disabled={disabled} value={v.model} onChange={(e) => set({ model: e.currentTarget.value })} />
            <TextInput label="Serial number" disabled={disabled} value={v.serial_number} onChange={(e) => set({ serial_number: e.currentTarget.value })} />
            <Select label="Status" disabled={disabled} allowDeselect={false} data={ASSET_STATUSES} value={v.status} onChange={(status) => set({ status: (status ?? 'in_use') as Asset['status'] })} />
            <ContactSelect
              label="Owner"
              disabled={disabled}
              placeholder="Your business"
              value={v.owner_party_id}
              onChange={(owner_party_id) => set({ owner_party_id })}
            />
            <TextInput label="Location" disabled={disabled} value={v.location} onChange={(e) => set({ location: e.currentTarget.value })} />
            <TextInput label="Assigned to" disabled={disabled} value={v.assigned_to} onChange={(e) => set({ assigned_to: e.currentTarget.value })} />
          </SimpleGrid>
        </Card>
        {category && category.fields.length > 0 && (
          <Card withBorder>
            <Title order={6} mb="xs">
              {category.name} details
            </Title>
            <ExtraFields
              category={category}
              values={attributes}
              disabled={disabled}
              onChange={(key, value) => setAttributes((old) => ({ ...old, [key]: value }))}
            />
          </Card>
        )}
        <Card withBorder>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <TextInput type="date" label="Purchased" disabled={disabled} value={v.purchase_date} onChange={(e) => set({ purchase_date: e.currentTarget.value })} />
            <NumberInput label="Price" min={0} decimalScale={2} disabled={disabled} value={v.purchase_price} onChange={(p) => set({ purchase_price: p === '' ? '' : Number(p) })} />
            <ContactSelect label="Bought from" role="vendor" disabled={disabled} value={v.vendor_party_id} onChange={(vendor_party_id) => set({ vendor_party_id })} />
            <TextInput type="date" label="Warranty expires" disabled={disabled} value={v.warranty_expires} onChange={(e) => set({ warranty_expires: e.currentTarget.value })} />
            <TextInput type="date" label="Support contract ends" disabled={disabled} value={v.support_ends} onChange={(e) => set({ support_ends: e.currentTarget.value })} />
            {asset?.expense_id && (
              <Text size="sm" mt="xl">
                Paid by{' '}
                <Anchor component={Link} to={`/expenses/${asset.expense_id}`}>
                  this expense
                </Anchor>
              </Text>
            )}
          </SimpleGrid>
          <Textarea mt="sm" label="Notes" autosize minRows={2} disabled={disabled} value={v.notes} onChange={(e) => set({ notes: e.currentTarget.value })} />
        </Card>
        {canEdit && (
          <Group justify="flex-end">
            {!asset && (
              <Button variant="default" onClick={() => navigate(-1)}>
                Cancel
              </Button>
            )}
            <Button type="submit" loading={save.isPending} disabled={!v.name.trim()}>
              {asset ? 'Save' : 'Add asset'}
            </Button>
          </Group>
        )}
      </Stack>
    </form>
  )
}

function Attachments({ asset }: { asset: Asset }) {
  const queryClient = useQueryClient()
  const { canEdit } = useAuth()
  const refresh = (saved?: Asset) => {
    if (saved) queryClient.setQueryData(['asset', asset.id], saved)
    else queryClient.invalidateQueries({ queryKey: ['asset', asset.id] })
  }
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return (await send('POST', `/api/assets/${asset.id}/attachments`, form)) as Asset
    },
    onSuccess: (saved) => {
      refresh(saved)
      notifySaved('File attached')
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async (id: number) =>
      unwrap(
        await api.DELETE('/api/assets/{asset_id}/attachments/{attachment_id}', {
          params: { path: { asset_id: asset.id, attachment_id: id } },
        }),
      ),
    onSuccess: () => refresh(),
    onError: notifyError,
  })
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Files</Text>
        {canEdit && (
          <FileButton onChange={(file) => file && upload.mutate(file)}>
            {(props) => (
              <Button {...props} size="xs" variant="light" leftSection={<IconPaperclip size={14} />} loading={upload.isPending}>
                Attach a file
              </Button>
            )}
          </FileButton>
        )}
      </Group>
      {asset.attachments.length === 0 ? (
        <Text size="sm" c="dimmed">
          Receipts, photos, configuration backups.
        </Text>
      ) : (
        <Table>
          <Table.Tbody>
            {asset.attachments.map((a) => (
              <Table.Tr key={a.id}>
                <Table.Td>
                  {canEdit ? (
                    <Anchor href={`/api/files/${a.file_id}`} target="_blank" size="sm">
                      {a.name}
                    </Anchor>
                  ) : (
                    <Text size="sm">{a.name}</Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text size="xs" c="dimmed">
                    {a.size < 1024 ? `${a.size} bytes` : `${Math.round(a.size / 1024)} KB`} · <DateText value={a.uploaded_at.slice(0, 10)} />
                  </Text>
                </Table.Td>
                <Table.Td w={1}>
                  {canEdit && (
                    <ActionIcon variant="subtle" color="red" aria-label={`Remove ${a.name}`} onClick={() => remove.mutate(a.id)}>
                      <IconTrash size={14} />
                    </ActionIcon>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Card>
  )
}

export function NewAssetPage() {
  return (
    <>
      <PageHeader title="New asset" />
      <AssetForm />
    </>
  )
}

export function AssetPage() {
  const { id } = useParams()
  const assetId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { isOwner } = useAuth()
  const { data: asset, error } = useQuery({
    queryKey: ['asset', assetId],
    queryFn: async () => unwrap(await api.GET('/api/assets/{asset_id}', { params: { path: { asset_id: assetId } } })),
  })
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE('/api/assets/{asset_id}', { params: { path: { asset_id: assetId } } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['assets'] })
      notifySaved('Asset deleted')
      navigate('/assets')
    },
    onError: notifyError,
  })
  if (error) return <Text c="red">{error.message}</Text>
  if (!asset) return <Loader />
  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            {asset.tag} {asset.name}
            <AssetStatusBadge status={asset.status} />
          </Group>
        }
        subtitle={[asset.category_name, asset.owner_name].filter(Boolean).join(' · ')}
        actions={
          isOwner && (
            <Button
              variant="subtle"
              color="red"
              leftSection={<IconTrash size={16} />}
              onClick={() =>
                modals.openConfirmModal({
                  title: `Delete ${asset.tag}?`,
                  children: <Text size="sm">For mistakes. Equipment sold or scrapped is marked "Disposed" instead.</Text>,
                  labels: { confirm: 'Delete', cancel: 'Cancel' },
                  confirmProps: { color: 'red' },
                  onConfirm: () => remove.mutate(),
                })
              }
            >
              Delete
            </Button>
          )
        }
      />
      <Stack>
        <AssetForm key={asset.updated_at} asset={asset} />
        <Attachments asset={asset} />
        <HistoryPanel entityType="asset" entityId={asset.id} />
      </Stack>
    </>
  )
}

/** A contact's Assets tab: what they own that you look after. */
export function ContactAssets({ partyId }: { partyId: number }) {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const { data } = useQuery({
    queryKey: ['assets', { owner: partyId }],
    queryFn: async () =>
      unwrap(await api.GET('/api/assets', { params: { query: { owner_party_id: partyId, limit: 500 } } })).items,
  })
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Equipment and licenses</Text>
        {canEdit && (
          <Button component={Link} to={`/assets/new?owner=${partyId}`} size="xs" variant="light" leftSection={<IconPlus size={14} />}>
            New asset
          </Button>
        )}
      </Group>
      <DataTable<Asset>
        rows={data}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/assets/${r.id}`)}
        empty="No assets recorded for this contact."
        columns={[
          { key: 'tag', header: 'Tag', render: (r) => r.tag },
          { key: 'name', header: 'Name', wide: true, render: (r) => r.name },
          { key: 'cat', header: 'Category', render: (r) => r.category_name },
          { key: 'serial', header: 'Serial', render: (r) => r.serial_number },
          { key: 'warranty', header: 'Warranty', render: (r) => <DateText value={r.warranty_expires} /> },
          { key: 'status', header: 'Status', render: (r) => <AssetStatusBadge status={r.status} /> },
        ]}
      />
    </Card>
  )
}
