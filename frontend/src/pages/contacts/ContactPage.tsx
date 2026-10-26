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
  Code,
  Grid,
  Group,
  Loader,
  Menu,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import {
  IconArchive,
  IconCash,
  IconDots,
  IconFileInvoice,
  IconPencil,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { api, send, unwrap, type Schemas } from '../../api/client'
import { useJurisdictions } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { DataTable } from '../../components/DataTable'
import { HistoryPanel } from '../../components/HistoryPanel'
import { ArchivedBadge, DateText, Money, PageHeader, PaymentStatusBadge } from '../../components/ui'
import { ADDRESS_TYPES, labelOf, PAYMENT_METHODS } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { ContactDocuments } from './ContactDocuments'
import { AddressForm, ContactForm, ExemptionForm, PersonForm } from './ContactForm'
import { RoleBadges } from './ContactsPage'

type Detail = Schemas['PartyDetail']

function Field({ label, children }: { label: string; children: ReactNode }) {
  if (children === null || children === undefined || children === '') return null
  return (
    <Group gap="xs" wrap="nowrap" align="flex-start">
      <Text size="sm" c="dimmed" w={150} style={{ flexShrink: 0 }}>
        {label}
      </Text>
      <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
        {children}
      </Text>
    </Group>
  )
}

function BalanceCard({ partyId }: { partyId: number }) {
  const { data } = useQuery({
    queryKey: ['contact-balance', partyId],
    queryFn: async () =>
      unwrap(await api.GET('/api/contacts/{party_id}/balance', { params: { path: { party_id: partyId } } })),
  })
  return (
    <Card withBorder>
      <Text fw={600} mb="xs">
        Balance
      </Text>
      {!data ? (
        <Loader size="sm" />
      ) : (
        <Stack gap={4}>
          <Group justify="space-between">
            <Text size="sm">Open invoices ({data.open_invoices})</Text>
            <Money value={data.receivable} />
          </Group>
          <Group justify="space-between">
            <Text size="sm" c={Number(data.overdue) > 0 ? 'red' : undefined}>
              Overdue
            </Text>
            <Money value={data.overdue} />
          </Group>
          <Group justify="space-between">
            <Text size="sm">Unapplied credit</Text>
            <Money value={data.unapplied_credit} />
          </Group>
          <Group justify="space-between">
            <Text size="sm" fw={600}>
              Owes you
            </Text>
            <Money value={data.net} strong />
          </Group>
        </Stack>
      )}
    </Card>
  )
}

function useRemove(partyId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => send('DELETE', path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact', partyId] })
      notifySaved('Removed')
    },
    onError: notifyError,
  })
}

function AddressesAndPeople({ contact, canEdit }: { contact: Detail; canEdit: boolean }) {
  const [address, setAddress] = useState<Schemas['AddressOut'] | 'new' | null>(null)
  const [person, setPerson] = useState<Schemas['PersonOut'] | 'new' | null>(null)
  const remove = useRemove(contact.id)
  const confirm = (what: string, path: string) =>
    modals.openConfirmModal({
      title: `Remove ${what}?`,
      labels: { confirm: 'Remove', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () => remove.mutate(path),
    })

  return (
    <SimpleGrid cols={{ base: 1, md: 2 }}>
      <Card withBorder>
        <Group justify="space-between" mb="xs">
          <Text fw={600}>Addresses</Text>
          {canEdit && (
            <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setAddress('new')}>
              Add
            </Button>
          )}
        </Group>
        <Stack gap="sm">
          {contact.addresses.length === 0 && <Text c="dimmed" size="sm">No addresses</Text>}
          {contact.addresses.map((a) => (
            <Group key={a.id} justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={0}>
                <Group gap={6}>
                  <Text size="sm" fw={500}>
                    {labelOf(ADDRESS_TYPES, a.address_type)}
                  </Text>
                  {a.is_default && <Badge size="xs" variant="light">Default</Badge>}
                </Group>
                {[a.line1, a.line2, [a.city, a.region, a.postal_code].filter(Boolean).join(' '), a.country_code]
                  .filter(Boolean)
                  .map((line, i) => (
                    <Text key={i} size="sm">
                      {line}
                    </Text>
                  ))}
              </Stack>
              {canEdit && (
                <Group gap={4} wrap="nowrap">
                  <ActionIcon variant="subtle" aria-label="Edit address" onClick={() => setAddress(a)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    aria-label="Remove address"
                    onClick={() => confirm('this address', `/api/contacts/${contact.id}/addresses/${a.id}`)}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              )}
            </Group>
          ))}
        </Stack>
      </Card>
      <Card withBorder>
        <Group justify="space-between" mb="xs">
          <Text fw={600}>People</Text>
          {canEdit && (
            <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setPerson('new')}>
              Add
            </Button>
          )}
        </Group>
        <Stack gap="sm">
          {contact.people.length === 0 && <Text c="dimmed" size="sm">No people</Text>}
          {contact.people.map((p) => (
            <Group key={p.id} justify="space-between" align="flex-start" wrap="nowrap">
              <Stack gap={0}>
                <Group gap={6}>
                  <Text size="sm" fw={500}>
                    {p.name}
                  </Text>
                  {p.title && <Text size="sm" c="dimmed">{p.title}</Text>}
                  {p.is_primary && <Badge size="xs" variant="light">Primary</Badge>}
                </Group>
                {[p.email, p.phone, p.mobile && `Mobile ${p.mobile}`].filter(Boolean).map((line, i) => (
                  <Text key={i} size="sm">
                    {line}
                  </Text>
                ))}
              </Stack>
              {canEdit && (
                <Group gap={4} wrap="nowrap">
                  <ActionIcon variant="subtle" aria-label="Edit person" onClick={() => setPerson(p)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    aria-label="Remove person"
                    onClick={() => confirm(p.name, `/api/contacts/${contact.id}/people/${p.id}`)}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              )}
            </Group>
          ))}
        </Stack>
      </Card>
      {address && (
        <AddressForm
          partyId={contact.id}
          address={address === 'new' ? undefined : address}
          onClose={() => setAddress(null)}
        />
      )}
      {person && (
        <PersonForm partyId={contact.id} person={person === 'new' ? undefined : person} onClose={() => setPerson(null)} />
      )}
    </SimpleGrid>
  )
}

function Exemptions({ contact, canEdit }: { contact: Detail; canEdit: boolean }) {
  const [editing, setEditing] = useState<Schemas['ExemptionOut'] | 'new' | null>(null)
  const { data: jurisdictions } = useJurisdictions()
  const remove = useRemove(contact.id)
  const name = (id: number | null | undefined) =>
    id ? (jurisdictions?.find((j) => j.id === id)?.name ?? `#${id}`) : 'Everywhere'
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Tax exemptions</Text>
        {canEdit && (
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing('new')}>
            Add
          </Button>
        )}
      </Group>
      {contact.tax_exemptions.length === 0 ? (
        <Text c="dimmed" size="sm">
          Not tax exempt
        </Text>
      ) : (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Type</Table.Th>
              <Table.Th>Certificate</Table.Th>
              <Table.Th>Applies in</Table.Th>
              <Table.Th>Valid</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {contact.tax_exemptions.map((e) => (
              <Table.Tr key={e.id}>
                <Table.Td>{e.certificate_type}</Table.Td>
                <Table.Td>{e.certificate_number}</Table.Td>
                <Table.Td>{name(e.jurisdiction_id)}</Table.Td>
                <Table.Td>
                  {e.valid_from || e.valid_to ? (
                    <>
                      <DateText value={e.valid_from} /> – <DateText value={e.valid_to} />
                    </>
                  ) : (
                    'Always'
                  )}
                </Table.Td>
                <Table.Td>
                  {canEdit && (
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <ActionIcon variant="subtle" aria-label="Edit exemption" onClick={() => setEditing(e)}>
                        <IconPencil size={16} />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        aria-label="Remove exemption"
                        onClick={() =>
                          modals.openConfirmModal({
                            title: 'Remove this tax exemption?',
                            labels: { confirm: 'Remove', cancel: 'Cancel' },
                            confirmProps: { color: 'red' },
                            onConfirm: () =>
                              remove.mutate(`/api/contacts/${contact.id}/tax-exemptions/${e.id}`),
                          })
                        }
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Group>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {editing && (
        <ExemptionForm
          partyId={contact.id}
          exemption={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </Card>
  )
}

function ContactInvoices({ partyId }: { partyId: number }) {
  const navigate = useNavigate()
  const { data, isFetching } = useQuery({
    queryKey: ['invoices', { party: partyId }],
    queryFn: async () =>
      unwrap(await api.GET('/api/invoices', { params: { query: { party_id: partyId, archived: 'all', limit: 200 } } })),
  })
  return (
    <DataTable<Schemas['InvoiceListItem']>
      rows={data?.items}
      loading={isFetching}
      rowKey={(r) => r.id}
      onRowClick={(r) => navigate(`/invoices/${r.id}`)}
      empty="No invoices"
      columns={[
        { key: 'no', header: 'No.', render: (r) => r.number ?? 'Draft' },
        { key: 'date', header: 'Date', render: (r) => <DateText value={r.issue_date} /> },
        { key: 'status', header: 'Status', render: (r) => <PaymentStatusBadge status={r.payment_status} overdue={r.is_overdue} /> },
        { key: 'total', header: 'Total', align: 'right', render: (r) => <Money value={r.total} /> },
        { key: 'due', header: 'Balance', align: 'right', render: (r) => <Money value={r.balance_due} /> },
        { key: 'arch', header: '', wide: true, render: (r) => <ArchivedBadge at={r.archived_at} /> },
      ]}
    />
  )
}

function ContactPayments({ partyId }: { partyId: number }) {
  const navigate = useNavigate()
  const { data, isFetching } = useQuery({
    queryKey: ['payments', { party: partyId }],
    queryFn: async () =>
      unwrap(await api.GET('/api/payments', { params: { query: { party_id: partyId, archived: 'all', limit: 200 } } })),
  })
  return (
    <DataTable<Schemas['PaymentOut']>
      rows={data?.items}
      loading={isFetching}
      rowKey={(r) => r.id}
      onRowClick={(r) => navigate(`/payments/${r.id}`)}
      empty="No payments"
      columns={[
        { key: 'date', header: 'Received', render: (r) => <DateText value={r.received_date} /> },
        { key: 'method', header: 'Method', render: (r) => labelOf(PAYMENT_METHODS, r.method) },
        { key: 'ref', header: 'Reference', render: (r) => r.reference },
        {
          key: 'inv',
          header: 'Invoices',
          wide: true,
          render: (r) => r.allocations.map((a) => a.invoice_number).filter(Boolean).join(', '),
        },
        { key: 'amount', header: 'Amount', align: 'right', render: (r) => <Money value={r.amount} /> },
      ]}
    />
  )
}

export function ContactPage() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const partyId = Number(id)
  const { canEdit, isOwner } = useAuth()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const { data: contact, error } = useQuery({
    queryKey: ['contact', partyId],
    queryFn: async () =>
      unwrap(await api.GET('/api/contacts/{party_id}', { params: { path: { party_id: partyId } } })),
  })
  const archive = useMutation({
    mutationFn: async (archived: boolean) => {
      const path = archived ? '/api/contacts/{party_id}/archive' : '/api/contacts/{party_id}/unarchive'
      return unwrap(await api.POST(path, { params: { path: { party_id: partyId } } }))
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(['contact', partyId], saved)
      queryClient.invalidateQueries({ queryKey: ['contacts'] })
      notifySaved(saved.archived_at ? 'Contact archived' : 'Contact restored')
    },
    onError: notifyError,
  })

  if (error) return <Text c="red">{error.message}</Text>
  if (!contact) return <Loader />

  const isClient = contact.roles.includes('client')
  const editable = canEdit && !contact.archived_at

  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            {contact.name}
            {!contact.is_active && <Badge color="gray">Inactive</Badge>}
            <ArchivedBadge at={contact.archived_at} />
          </Group>
        }
        subtitle={
          <Group gap="xs">
            <span>
              No. {contact.party_no} · {contact.short_code}
            </span>
            <RoleBadges roles={contact.roles} />
          </Group>
        }
        actions={
          <>
            {editable && isClient && (
              <>
                <Button
                  component={Link}
                  to={`/invoices/new?party=${contact.id}`}
                  leftSection={<IconFileInvoice size={16} />}
                  variant="light"
                >
                  New invoice
                </Button>
                <Button
                  component={Link}
                  to={`/payments/new?party=${contact.id}`}
                  leftSection={<IconCash size={16} />}
                  variant="light"
                >
                  Receive payment
                </Button>
              </>
            )}
            {editable && (
              <Button leftSection={<IconPencil size={16} />} onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
            {canEdit && !contact.roles.includes('self') && (
              <Menu position="bottom-end">
                <Menu.Target>
                  <ActionIcon variant="default" size="lg" aria-label="More actions">
                    <IconDots size={18} />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  {contact.archived_at ? (
                    <Menu.Item
                      leftSection={<IconArchive size={14} />}
                      disabled={!isOwner}
                      onClick={() => archive.mutate(false)}
                    >
                      Unarchive{!isOwner && ' (owner only)'}
                    </Menu.Item>
                  ) : (
                    <Menu.Item leftSection={<IconArchive size={14} />} onClick={() => archive.mutate(true)}>
                      Archive
                    </Menu.Item>
                  )}
                </Menu.Dropdown>
              </Menu>
            )}
          </>
        }
      />

      <Grid mb="md">
        <Grid.Col span={{ base: 12, md: isClient ? 8 : 12 }}>
          <Card withBorder h="100%">
            <Stack gap={6}>
              <Field label="Email">
                {contact.email && <Anchor href={`mailto:${contact.email}`}>{contact.email}</Anchor>}
              </Field>
              <Field label="Phone">{contact.phone}</Field>
              <Field label="Fax">{contact.fax}</Field>
              <Field label="Website">
                {contact.website && (
                  <Anchor href={contact.website.startsWith('http') ? contact.website : `https://${contact.website}`} target="_blank">
                    {contact.website}
                  </Anchor>
                )}
              </Field>
              <Field label="Tax ID">{contact.tax_id}</Field>
              <Field label="Payment terms">
                {contact.default_terms_days !== null && contact.default_terms_days !== undefined
                  ? `${contact.default_terms_days} days`
                  : ''}
              </Field>
              <Field label="Our account no.">{contact.vendor_account_no}</Field>
              <Field label="Notes">{contact.notes}</Field>
              {!contact.email && !contact.phone && !contact.notes && (
                <Text c="dimmed" size="sm">
                  No contact details yet
                </Text>
              )}
            </Stack>
          </Card>
        </Grid.Col>
        {isClient && (
          <Grid.Col span={{ base: 12, md: 4 }}>
            <BalanceCard partyId={contact.id} />
          </Grid.Col>
        )}
      </Grid>

      <Tabs
        value={params.get('tab') ?? 'details'}
        onChange={(tab) => setParams(tab && tab !== 'details' ? { tab } : {}, { replace: true })}
        keepMounted={false}
      >
        <Tabs.List mb="md">
          <Tabs.Tab value="details">Addresses & people</Tabs.Tab>
          <Tabs.Tab value="tax">Tax</Tabs.Tab>
          <Tabs.Tab value="documents">Documents</Tabs.Tab>
          {isClient && <Tabs.Tab value="invoices">Invoices</Tabs.Tab>}
          {isClient && <Tabs.Tab value="payments">Payments</Tabs.Tab>}
          <Tabs.Tab value="history">History</Tabs.Tab>
          {contact.legacy_data && <Tabs.Tab value="legacy">Old system</Tabs.Tab>}
        </Tabs.List>
        <Tabs.Panel value="details">
          <AddressesAndPeople contact={contact} canEdit={editable} />
        </Tabs.Panel>
        <Tabs.Panel value="tax">
          <Exemptions contact={contact} canEdit={editable} />
        </Tabs.Panel>
        <Tabs.Panel value="documents">
          <ContactDocuments contact={contact} canEdit={editable} />
        </Tabs.Panel>
        <Tabs.Panel value="invoices">
          <ContactInvoices partyId={contact.id} />
        </Tabs.Panel>
        <Tabs.Panel value="payments">
          <ContactPayments partyId={contact.id} />
        </Tabs.Panel>
        <Tabs.Panel value="history">
          <HistoryPanel entityType="party" entityId={contact.id} />
        </Tabs.Panel>
        <Tabs.Panel value="legacy">
          <Text size="sm" c="dimmed" mb="xs">
            Values from the MS Access system that have no place in the new one (kept for reference).
          </Text>
          <Code block>{JSON.stringify(contact.legacy_data, null, 2)}</Code>
        </Tabs.Panel>
      </Tabs>

      {editing && <ContactForm contact={contact} onClose={() => setEditing(false)} />}
    </>
  )
}
