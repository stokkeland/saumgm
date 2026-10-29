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

import { Anchor, Button, Card, Group, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { IconCash, IconFileInvoice, IconReceipt } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { api, unwrap } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DateText, Money, PageHeader } from '../../components/ui'
import { DOCUMENT_TYPES, labelOf } from '../../lib/labels'
import { DocumentStatusBadge } from '../contacts/ContactDocuments'

function Stat({
  label,
  value,
  note,
  to,
  color,
}: {
  label: string
  value: ReactNode
  note?: ReactNode
  to?: string
  color?: string
}) {
  const body = (
    <Card withBorder h="100%">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="xl" fw={700} c={color} mt={4}>
        {value}
      </Text>
      {note && (
        <Text size="xs" c="dimmed" mt={2}>
          {note}
        </Text>
      )}
    </Card>
  )
  return to ? (
    <Anchor component={Link} to={to} underline="never" c="inherit">
      {body}
    </Anchor>
  ) : (
    body
  )
}

/** Contacts' documents (W-9s, certificates...) that have expired or expire soon. */
function DocumentsCard() {
  const { data } = useQuery({
    queryKey: ['documents-attention'],
    queryFn: async () => unwrap(await api.GET('/api/documents/attention')),
  })
  if (!data?.length) return null
  return (
    <Card withBorder>
      <Text fw={600} mb="xs">
        Documents expired or expiring soon
      </Text>
      <Table>
        <Table.Tbody>
          {data.map((d) => (
            <Table.Tr key={d.id}>
              <Table.Td>
                <Anchor component={Link} to={`/contacts/${d.party_id}?tab=documents`} size="sm">
                  {d.party_name}
                </Anchor>
              </Table.Td>
              <Table.Td>
                <Text size="sm">
                  {labelOf(DOCUMENT_TYPES, d.document_type)}
                  {d.title !== labelOf(DOCUMENT_TYPES, d.document_type) && ` – ${d.title}`}
                </Text>
              </Table.Td>
              <Table.Td>
                <DateText value={d.expires_on} />
              </Table.Td>
              <Table.Td>
                <DocumentStatusBadge doc={d} />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  )
}

export function DashboardPage() {
  const { canEdit, me } = useAuth()
  const { data } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => unwrap(await api.GET('/api/dashboard')),
  })

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={me.organization.display_name}
        actions={
          canEdit && (
            <>
              <Button component={Link} to="/invoices/new" leftSection={<IconFileInvoice size={16} />}>
                New invoice
              </Button>
              <Button component={Link} to="/payments/new" variant="light" leftSection={<IconCash size={16} />}>
                Receive payment
              </Button>
              <Button component={Link} to="/expenses/new" variant="light" leftSection={<IconReceipt size={16} />}>
                New expense
              </Button>
            </>
          )
        }
      />
      {data && (
        <Stack>
          <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
            <Stat
              label="Owed to you"
              value={<Money value={data.receivable} />}
              note={`${data.open_invoices} open invoice(s)`}
              to="/invoices?view=open"
            />
            <Stat
              label="Overdue"
              value={<Money value={data.overdue} />}
              note={`${data.overdue_invoices} invoice(s)`}
              color={Number(data.overdue) > 0 ? 'red' : undefined}
              to="/invoices?view=overdue"
            />
            <Stat
              label="Waiting to be deposited"
              value={<Money value={data.undeposited} />}
              note={`${data.undeposited_payments} payment(s)`}
              to="/payments?view=undeposited"
            />
            <Stat label="Draft invoices" value={data.drafts} to="/invoices?view=draft" />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <SimpleGrid cols={2}>
              <Stat
                label="Sales this year"
                value={<Money value={data.sales_this_year} />}
                note={
                  <>
                    since <DateText value={data.year_start} />, before tax
                  </>
                }
              />
              <Stat
                label="Expenses this year"
                value={<Money value={data.expenses_this_year} />}
                note={
                  <>
                    since <DateText value={data.year_start} />
                  </>
                }
                to={`/expenses?from=${data.year_start}`}
              />
              {Number(data.unapplied_credit) > 0 && (
                <Stat label="Client credit (unapplied payments)" value={<Money value={data.unapplied_credit} />} />
              )}
            </SimpleGrid>
            <Card withBorder>
              <Group justify="space-between" mb="xs">
                <Text fw={600}>Subscriptions due in the next 30 days</Text>
                <Anchor component={Link} to="/subscriptions" size="sm">
                  All subscriptions
                </Anchor>
              </Group>
              {data.renewals.length === 0 ? (
                <Text size="sm" c="dimmed">
                  Nothing due
                </Text>
              ) : (
                <Table>
                  <Table.Tbody>
                    {data.renewals.map((r) => (
                      <Table.Tr key={r.subscription_id}>
                        <Table.Td>
                          <DateText value={r.next_bill_date} />
                        </Table.Td>
                        <Table.Td>
                          <Anchor component={Link} to={`/contacts/${r.party_id}`} size="sm">
                            {r.party_name}
                          </Anchor>
                        </Table.Td>
                        <Table.Td>
                          {r.item_name}
                          {r.service_identifier && ` – ${r.service_identifier}`}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Card>
          </SimpleGrid>
          <DocumentsCard />
        </Stack>
      )}
    </>
  )
}
