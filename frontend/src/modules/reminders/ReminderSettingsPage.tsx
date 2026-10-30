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

import { Alert, Button, Card, Code, Group, Loader, NumberInput, SimpleGrid, Stack, Text, Textarea, Title } from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconMail } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '../../api/client'
import { PageHeader } from '../../components/ui'
import { notifyError, notifySaved } from '../../lib/notify'

type Settings = Schemas['ReminderSettingsOut']

function SettingsForm({ settings }: { settings: Settings }) {
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: {
      bill_days: settings.bill_days,
      pay_days: settings.pay_days,
      reconcile_days: settings.reconcile_days,
      recipients: settings.recipients.join('\n'),
    },
  })
  const save = useMutation({
    mutationFn: async (values: typeof form.values) =>
      unwrap(
        await api.PATCH('/api/reminders/settings', {
          body: {
            bill_days: Number(values.bill_days),
            pay_days: Number(values.pay_days),
            reconcile_days: Number(values.reconcile_days),
            recipients: values.recipients.split(/[\s,;]+/).filter(Boolean),
          },
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(['reminder-settings'], saved)
      queryClient.invalidateQueries({ queryKey: ['reminders'] })
      queryClient.invalidateQueries({ queryKey: ['reminder-digest'] })
      form.setValues({ ...form.values, recipients: saved.recipients.join('\n') })
      form.resetDirty()
      notifySaved()
    },
    onError: notifyError,
  })
  return (
    <Card withBorder>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <Title order={5}>Lead times</Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <NumberInput
              label="Bill clients"
              description="Client subscriptions due for billing within this many days"
              min={0}
              max={365}
              suffix=" days"
              {...form.getInputProps('bill_days')}
            />
            <NumberInput
              label="Pay vendors"
              description="Vendor subscriptions due within this many days"
              min={0}
              max={365}
              suffix=" days"
              {...form.getInputProps('pay_days')}
            />
            <NumberInput
              label="Reconcile"
              description="Bank accounts not reconciled for this many days"
              min={1}
              max={365}
              suffix=" days"
              {...form.getInputProps('reconcile_days')}
            />
          </SimpleGrid>
          <Text size="sm" c="dimmed">
            Overdue invoices are listed once they are overdue; contact documents by each document's own reminder
            window.
          </Text>
          <Title order={5}>Digest email</Title>
          <Textarea
            label="Send the digest to"
            description={`One address per line. Empty: the owners (${settings.owners.join(', ') || 'none'})`}
            autosize
            minRows={2}
            {...form.getInputProps('recipients')}
          />
          <Group justify="flex-end">
            <Button type="submit" loading={save.isPending} disabled={!form.isDirty()}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Card>
  )
}

function DigestCard({ settings }: { settings: Settings }) {
  const queryClient = useQueryClient()
  const { data: draft } = useQuery({
    queryKey: ['reminder-digest'],
    queryFn: async () => unwrap(await api.GET('/api/reminders/digest')),
  })
  const send = useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/reminders/digest')),
    onSuccess: (sent) => {
      notifySaved(`Digest sent to ${sent.redirected_to ?? sent.to_addresses}`)
      queryClient.invalidateQueries({ queryKey: ['email-messages'] })
    },
    onError: notifyError,
  })
  return (
    <Card withBorder>
      <Stack>
        <Group justify="space-between">
          <Title order={5}>The digest as it would go out now</Title>
          <Button
            variant="light"
            leftSection={<IconMail size={16} />}
            loading={send.isPending}
            disabled={!draft?.to.length}
            onClick={() => send.mutate()}
          >
            Send now
          </Button>
        </Group>
        {!settings.app_url && (
          <Alert variant="light" color="yellow">
            The digest has no links into the app until <Code>APP_URL</Code> is set in the server's <Code>.env</Code>{' '}
            (for example <Code>APP_URL=https://saumgm.example.com</Code>).
          </Alert>
        )}
        {!draft ? (
          <Loader size="sm" />
        ) : (
          <>
            <Text size="sm">
              <b>To:</b> {draft.to.join(', ') || 'nobody (no owner, no address above)'}
              {draft.redirect_to && ` (redirected to ${draft.redirect_to} by EMAIL_REDIRECT_TO)`}
            </Text>
            <Text size="sm">
              <b>Subject:</b> {draft.subject}
            </Text>
            <Code block>{draft.body}</Code>
          </>
        )}
        <Text size="sm" c="dimmed">
          The server sends it daily with <Code>python -m saumgm notify</Code> (the <Code>saumgm-notify.timer</Code>), and
          only when something is due. Sent digests are in Admin → Email → Sent messages.
        </Text>
      </Stack>
    </Card>
  )
}

export function ReminderSettingsPage() {
  const { data } = useQuery({
    queryKey: ['reminder-settings'],
    queryFn: async () => unwrap(await api.GET('/api/reminders/settings')),
  })
  return (
    <>
      <PageHeader title="Reminders" subtitle="The to-do list and the daily digest email" />
      {!data ? (
        <Loader size="sm" />
      ) : (
        <Stack maw={820}>
          <SettingsForm settings={data} />
          <DigestCard settings={data} />
        </Stack>
      )}
    </>
  )
}
