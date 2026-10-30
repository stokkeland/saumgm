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

import { Anchor, Button, Card, Group, Loader, Stack, Table, Text, Title } from '@mantine/core'
import { IconSettings } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DateText, Money, PageHeader } from '../../components/ui'

type Section = Schemas['ReminderSection']

const FLAG_COLORS: Record<string, string> = {
  overdue: 'red',
  expired: 'red',
  expiring: 'orange',
  autopay: 'blue',
}

function useReminders() {
  return useQuery({
    queryKey: ['reminders'],
    queryFn: async () => unwrap(await api.GET('/api/reminders')),
    // Built from many kinds of records; fetch it fresh whenever a page shows it.
    staleTime: 0,
  })
}

/** One section of the to-do list; `limit` shortens it (the dashboard). */
export function ReminderSection({ section, limit }: { section: Section; limit?: number }) {
  const { canEdit } = useAuth()
  const items = limit ? section.items.slice(0, limit) : section.items
  const more = section.items.length - items.length
  return (
    <Stack gap={4}>
      <Group justify="space-between" wrap="nowrap">
        <div>
          <Anchor component={Link} to={section.link} fw={600} c="inherit">
            {section.title}
          </Anchor>
          <Text size="sm" c="dimmed">
            {section.summary}
          </Text>
        </div>
        {canEdit && section.action_label && section.action_link && (
          <Button component={Link} to={section.action_link} size="xs" variant="light">
            {section.action_label}
          </Button>
        )}
      </Group>
      <Table>
        <Table.Tbody>
          {items.map((item, n) => (
            <Table.Tr key={n}>
              <Table.Td w={120}>
                <DateText value={item.date} />
              </Table.Td>
              <Table.Td>
                <Anchor component={Link} to={item.link} size="sm">
                  {item.title}
                </Anchor>
              </Table.Td>
              <Table.Td ta="right">{item.amount !== null && <Money value={item.amount} />}</Table.Td>
              <Table.Td>
                {item.note && (
                  <Text size="sm" c={FLAG_COLORS[item.flag ?? ''] ?? 'dimmed'}>
                    {item.note}
                  </Text>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {more > 0 && (
        <Anchor component={Link} to={section.link} size="sm">
          and {more} more
        </Anchor>
      )}
    </Stack>
  )
}

export function ToDoPage() {
  const { isOwner } = useAuth()
  const { data } = useReminders()
  return (
    <>
      <PageHeader
        title="To do"
        subtitle="Clients to bill, vendors to pay, invoices to collect, documents to renew"
        actions={
          isOwner && (
            <Button component={Link} to="/admin/reminders" variant="light" leftSection={<IconSettings size={16} />}>
              Reminder settings
            </Button>
          )
        }
      />
      {!data ? (
        <Loader size="sm" />
      ) : (
        <Stack>
          <Text>{data.summary}</Text>
          {data.sections.map((s) => (
            <Card withBorder key={s.key}>
              <ReminderSection section={s} />
            </Card>
          ))}
        </Stack>
      )}
    </>
  )
}

/** The dashboard's summary: each section, a few items each. */
export function ToDoCard() {
  const { data } = useReminders()
  if (!data) return null
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Title order={5}>To do</Title>
        <Anchor component={Link} to="/todo" size="sm">
          Full to-do list
        </Anchor>
      </Group>
      {data.sections.length === 0 ? (
        <Text size="sm" c="dimmed">
          Nothing needs doing right now.
        </Text>
      ) : (
        <Stack gap="lg">
          {data.sections.map((s) => (
            <ReminderSection key={s.key} section={s} limit={5} />
          ))}
        </Stack>
      )}
    </Card>
  )
}
