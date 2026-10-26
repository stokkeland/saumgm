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
  Button,
  Card,
  Checkbox,
  Group,
  Loader,
  NumberInput,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { ContactSelect } from '../../components/ContactSelect'
import { DataTable } from '../../components/DataTable'
import { HistoryPanel } from '../../components/HistoryPanel'
import { ArchivedBadge, ArchiveFilter, DateText, Money, PageHeader, PdfButton, type ArchiveFilterValue } from '../../components/ui'
import { todayIso } from '../../lib/format'
import { labelOf, PAYMENT_METHODS } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { useUrlState } from '../../lib/useUrlState'

type Deposit = Schemas['DepositOut']
const LIMIT = 50

export function DepositsPage() {
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const [f, setF] = useUrlState({ archived: 'current', offset: '0' })
  const { data, isFetching } = useQuery({
    queryKey: ['deposits', f],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/deposits', {
          params: { query: { archived: f.archived as ArchiveFilterValue, limit: LIMIT, offset: Number(f.offset) } },
        }),
      ),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <PageHeader
        title="Deposits"
        subtitle="Bank deposits made from received payments"
        actions={
          canEdit && (
            <Button component={Link} to="/deposits/new" leftSection={<IconPlus size={16} />}>
              Make deposit
            </Button>
          )
        }
      />
      <Group mb="sm">
        <ArchiveFilter value={f.archived as ArchiveFilterValue} onChange={(archived) => setF({ archived })} />
      </Group>
      <DataTable<Deposit>
        rows={data?.items}
        loading={isFetching}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigate(`/deposits/${r.id}`)}
        empty="No deposits"
        page={data && { total: data.total, limit: LIMIT, offset: Number(f.offset), onOffset: (o) => setF({ offset: String(o) }) }}
        columns={[
          { key: 'date', header: 'Date', render: (r) => <DateText value={r.deposit_date} /> },
          {
            key: 'what',
            header: 'Contents',
            render: (r) =>
              [r.payments.length && `${r.payments.length} payment(s)`, r.items.length && `${r.items.length} other item(s)`]
                .filter(Boolean)
                .join(', '),
          },
          { key: 'notes', header: 'Notes', wide: true, render: (r) => r.notes },
          { key: 'arch', header: '', render: (r) => <ArchivedBadge at={r.archived_at} /> },
          { key: 'total', header: 'Total', align: 'right', render: (r) => <Money value={r.total} /> },
        ]}
      />
    </>
  )
}

interface ExtraItem {
  key: number
  description: string
  amount: number | string
}

export function NewDepositPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [date, setDate] = useState(todayIso())
  const [bank, setBank] = useState<number | null>(null)
  const [notes, setNotes] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [items, setItems] = useState<ExtraItem[]>([])

  const { data: waiting } = useQuery({
    queryKey: ['payments', { undeposited: true }],
    queryFn: async () =>
      unwrap(await api.GET('/api/payments', { params: { query: { undeposited: true, limit: 500 } } })).items,
  })

  const paymentsTotal = (waiting ?? [])
    .filter((p) => selected.includes(p.id))
    .reduce((sum, p) => sum + Number(p.amount), 0)
  const itemsTotal = items.reduce((sum, i) => sum + Number(i.amount || 0), 0)

  const save = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/deposits', {
          body: {
            deposit_date: date,
            bank_party_id: bank,
            notes: notes.trim() || null,
            payment_ids: selected,
            items: items
              .filter((i) => Number(i.amount))
              .map((i) => ({ amount: String(i.amount), description: i.description.trim() || null })),
          },
        }),
      ),
    onSuccess: (deposit) => {
      queryClient.invalidateQueries({ queryKey: ['deposits'] })
      queryClient.invalidateQueries({ queryKey: ['payments'] })
      notifySaved('Deposit recorded')
      navigate(`/deposits/${deposit.id}`, { replace: true })
    },
    onError: notifyError,
  })

  const all = waiting ?? []
  return (
    <>
      <PageHeader title="Make deposit" subtitle="Choose the payments going to the bank" />
      <Stack>
        <Card withBorder>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <TextInput type="date" label="Deposit date" required value={date} onChange={(e) => setDate(e.currentTarget.value)} />
            <ContactSelect label="Bank" role="financial" value={bank} onChange={setBank} />
            <Textarea label="Notes" autosize value={notes} onChange={(e) => setNotes(e.currentTarget.value)} />
          </SimpleGrid>
        </Card>
        <Card withBorder>
          <Group justify="space-between" mb="xs">
            <Text fw={600}>Payments not yet deposited</Text>
            {all.length > 0 && (
              <Checkbox
                label="Select all"
                checked={selected.length === all.length}
                indeterminate={selected.length > 0 && selected.length < all.length}
                onChange={(e) => setSelected(e.currentTarget.checked ? all.map((p) => p.id) : [])}
              />
            )}
          </Group>
          {all.length === 0 ? (
            <Text size="sm" c="dimmed">
              Every payment has been deposited.
            </Text>
          ) : (
            <Table>
              <Table.Tbody>
                {all.map((p) => (
                  <Table.Tr key={p.id}>
                    <Table.Td w={40}>
                      <Checkbox
                        aria-label={`Deposit payment from ${p.party_name}`}
                        checked={selected.includes(p.id)}
                        onChange={(e) => {
                          const checked = e.currentTarget.checked
                          setSelected((s) => (checked ? [...s, p.id] : s.filter((x) => x !== p.id)))
                        }}
                      />
                    </Table.Td>
                    <Table.Td>
                      <DateText value={p.received_date} />
                    </Table.Td>
                    <Table.Td>{p.party_name}</Table.Td>
                    <Table.Td>
                      {labelOf(PAYMENT_METHODS, p.method)} {p.reference}
                    </Table.Td>
                    <Table.Td ta="right">
                      <Money value={p.amount} />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Card>
        <Card withBorder>
          <Group justify="space-between" mb="xs">
            <Text fw={600}>Other items</Text>
            <Button
              size="xs"
              variant="light"
              leftSection={<IconPlus size={14} />}
              onClick={() => setItems((i) => [...i, { key: Date.now(), description: '', amount: '' }])}
            >
              Add item
            </Button>
          </Group>
          <Stack gap="xs">
            {items.length === 0 && (
              <Text size="sm" c="dimmed">
                For money not recorded as a payment (e.g. a cash sale).
              </Text>
            )}
            {items.map((item, index) => (
              <Group key={item.key} wrap="nowrap">
                <TextInput
                  aria-label="Item description"
                  placeholder="Description"
                  style={{ flex: 1 }}
                  value={item.description}
                  onChange={(e) => {
                    const description = e.currentTarget.value
                    setItems((all) => all.map((x, i) => (i === index ? { ...x, description } : x)))
                  }}
                />
                <NumberInput
                  aria-label="Item amount"
                  w={140}
                  decimalScale={2}
                  value={item.amount}
                  onChange={(amount) => setItems((all) => all.map((x, i) => (i === index ? { ...x, amount } : x)))}
                />
                <ActionIcon variant="subtle" color="red" aria-label="Remove item" onClick={() => setItems((all) => all.filter((_, i) => i !== index))}>
                  <IconTrash size={16} />
                </ActionIcon>
              </Group>
            ))}
          </Stack>
        </Card>
        <Group justify="space-between">
          <Text fw={600}>
            Deposit total <Money value={String(paymentsTotal + itemsTotal)} strong />
          </Text>
          <Group>
            <Button variant="default" onClick={() => navigate(-1)}>
              Cancel
            </Button>
            <Button disabled={!date || (!selected.length && !itemsTotal)} loading={save.isPending} onClick={() => save.mutate()}>
              Record deposit
            </Button>
          </Group>
        </Group>
      </Stack>
    </>
  )
}

export function DepositPage() {
  const { id } = useParams()
  const depositId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canEdit } = useAuth()
  const { data: deposit, error } = useQuery({
    queryKey: ['deposit', depositId],
    queryFn: async () =>
      unwrap(await api.GET('/api/deposits/{deposit_id}', { params: { path: { deposit_id: depositId } } })),
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/deposits/{deposit_id}', { params: { path: { deposit_id: depositId } } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deposits'] })
      queryClient.invalidateQueries({ queryKey: ['payments'] })
      notifySaved('Deposit deleted; its payments are waiting to be deposited again')
      navigate('/deposits')
    },
    onError: notifyError,
  })

  if (error) return <Text c="red">{error.message}</Text>
  if (!deposit) return <Loader />
  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            Deposit <DateText value={deposit.deposit_date} />
            <ArchivedBadge at={deposit.archived_at} />
          </Group>
        }
        subtitle={deposit.notes}
        actions={
          <>
            <PdfButton href={`/api/deposits/${deposit.id}/slip.pdf`} label="Deposit slip" />
            {canEdit && !deposit.archived_at && (
            <Button
              color="red"
              variant="light"
              leftSection={<IconTrash size={16} />}
              onClick={() =>
                modals.openConfirmModal({
                  title: 'Delete this deposit?',
                  children: <Text size="sm">Its payments go back to "not deposited".</Text>,
                  labels: { confirm: 'Delete', cancel: 'Cancel' },
                  confirmProps: { color: 'red' },
                  onConfirm: () => remove.mutate(),
                })
              }
            >
              Delete
            </Button>
            )}
          </>
        }
      />
      <Card withBorder mb="md">
        <Table>
          <Table.Tbody>
            {deposit.payments.map((p) => (
              <Table.Tr key={`p${p.id}`}>
                <Table.Td>
                  <Anchor component={Link} to={`/payments/${p.id}`}>
                    <DateText value={p.received_date} />
                  </Anchor>
                </Table.Td>
                <Table.Td>{p.party_name}</Table.Td>
                <Table.Td>
                  {labelOf(PAYMENT_METHODS, p.method)} {p.reference}
                </Table.Td>
                <Table.Td ta="right">
                  <Money value={p.amount} />
                </Table.Td>
              </Table.Tr>
            ))}
            {deposit.items.map((i) => (
              <Table.Tr key={`i${i.id}`}>
                <Table.Td colSpan={3}>{i.description}</Table.Td>
                <Table.Td ta="right">
                  <Money value={i.amount} />
                </Table.Td>
              </Table.Tr>
            ))}
            <Table.Tr>
              <Table.Td colSpan={3} fw={600}>
                Total
              </Table.Td>
              <Table.Td ta="right">
                <Money value={deposit.total} strong />
              </Table.Td>
            </Table.Tr>
          </Table.Tbody>
        </Table>
      </Card>
      <HistoryPanel entityType="deposit" entityId={deposit.id} />
    </>
  )
}
