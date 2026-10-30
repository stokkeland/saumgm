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
  Accordion,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { IconMail } from '@tabler/icons-react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { DataTable } from '../../components/DataTable'
import { PageHeader } from '../../components/ui'
import { formatDateTime } from '../../lib/format'
import { notifyError, notifySaved } from '../../lib/notify'

type Settings = Schemas['EmailSettingsOut']
type Template = Schemas['TemplateOut']
type Message = Schemas['MessageOut']

const KIND_LABELS: Record<string, string> = {
  invoice: 'Invoice',
  credit_note: 'Credit note',
  receipt: 'Payment receipt',
  report: 'Report',
  test: 'Test message',
  digest: 'Reminders digest',
}

const RECORD_LINKS: Record<string, string> = { invoice: '/invoices', payment: '/payments' }

export function EmailPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'sender'
  return (
    <>
      <PageHeader title="Email" subtitle="Who the messages come from, their text, and what was sent" />
      <Tabs value={tab} onChange={(t) => setParams({ tab: t ?? 'sender' }, { replace: true })} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="sender">Sender</Tabs.Tab>
          <Tabs.Tab value="templates">Templates</Tabs.Tab>
          <Tabs.Tab value="log">Sent messages</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="sender">
          <SenderTab />
        </Tabs.Panel>
        <Tabs.Panel value="templates">
          <TemplatesTab />
        </Tabs.Panel>
        <Tabs.Panel value="log">
          <LogTab />
        </Tabs.Panel>
      </Tabs>
    </>
  )
}

function useEmailSettings() {
  return useQuery({
    queryKey: ['email-settings'],
    queryFn: async () => unwrap(await api.GET('/api/email/settings')),
  })
}

function SenderTab() {
  const { data } = useEmailSettings()
  if (!data) return <Loader size="sm" />
  return (
    <Stack maw={720}>
      <SenderForm settings={data} />
      <TestCard settings={data} />
    </Stack>
  )
}

function SenderForm({ settings }: { settings: Settings }) {
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: {
      from_address: settings.from_address ?? '',
      from_name: settings.from_name ?? '',
      reply_to: settings.reply_to ?? '',
    },
  })
  const save = useMutation({
    mutationFn: async (values: typeof form.values) =>
      unwrap(await api.PATCH('/api/email/settings', { body: values })),
    onSuccess: (saved) => {
      queryClient.setQueryData(['email-settings'], saved)
      form.resetDirty()
      notifySaved()
    },
    onError: notifyError,
  })
  return (
    <Card withBorder>
      <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
        <Stack>
          <Text size="sm" c="dimmed">
            Messages come from this address. It must be on a domain verified with the email provider (Resend: Domains),
            or they are refused.
          </Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput
              label="From address"
              placeholder={settings.default_from ?? 'billing@yourbusiness.com'}
              description={settings.default_from ? `Empty: ${settings.default_from} (EMAIL_FROM on the server)` : undefined}
              {...form.getInputProps('from_address')}
            />
            <TextInput label="From name" placeholder="Your business name" {...form.getInputProps('from_name')} />
            <TextInput
              label="Replies go to"
              placeholder="The from address"
              description="Optional: where clients' replies should land"
              {...form.getInputProps('reply_to')}
            />
          </SimpleGrid>
          <Group justify="space-between">
            <Text size="sm">
              Sends as: <Code>{settings.sender ?? 'not set yet'}</Code>
            </Text>
            <Button type="submit" loading={save.isPending} disabled={!form.isDirty()}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Card>
  )
}

function TestCard({ settings }: { settings: Settings }) {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const [to, setTo] = useState('')
  const test = useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/email/test', { body: { to: to.trim() || null } })),
    onSuccess: (sent) => {
      notifySaved(`Test message sent to ${sent.redirected_to ?? sent.to_addresses}`)
      queryClient.invalidateQueries({ queryKey: ['email-messages'] })
    },
    onError: (error) => {
      queryClient.invalidateQueries({ queryKey: ['email-messages'] })
      notifyError(error)
    },
  })
  return (
    <Card withBorder>
      <Stack>
        <Title order={5}>Check the setup</Title>
        <Group gap="xs">
          <Text size="sm">Sending through:</Text>
          <Badge variant="light" color={settings.backend === 'console' ? 'gray' : 'green'}>
            {settings.backend}
          </Badge>
          {settings.backend === 'console' && (
            <Text size="sm" c="dimmed">
              messages are only written to the server log (EMAIL_URL=console://)
            </Text>
          )}
        </Group>
        {settings.redirect_to && (
          <Alert color="orange" variant="light">
            Every message goes to {settings.redirect_to} instead of its recipients (EMAIL_REDIRECT_TO on the server).
          </Alert>
        )}
        <Group align="flex-end">
          <TextInput
            label="Send a test message to"
            placeholder={me.user.email}
            value={to}
            onChange={(e) => setTo(e.currentTarget.value)}
            w={320}
          />
          <Button leftSection={<IconMail size={16} />} loading={test.isPending} disabled={!settings.sender} onClick={() => test.mutate()}>
            Send test
          </Button>
        </Group>
      </Stack>
    </Card>
  )
}

function TemplatesTab() {
  const { data } = useQuery({
    queryKey: ['email-templates'],
    queryFn: async () => unwrap(await api.GET('/api/email/templates')),
  })
  if (!data) return <Loader size="sm" />
  return (
    <Stack maw={860}>
      <Text size="sm" c="dimmed">
        The subject and message each kind of email starts with; they can still be changed before sending. Words in
        braces are filled in, for example <Code>{'{invoice_number}'}</Code>.
      </Text>
      <Accordion variant="separated" multiple>
        {data.map((t) => (
          <Accordion.Item key={t.kind} value={t.kind}>
            <Accordion.Control>
              <Group gap="xs">
                <Text>{KIND_LABELS[t.kind] ?? t.kind}</Text>
                {t.customized && (
                  <Badge size="sm" variant="light">
                    your text
                  </Badge>
                )}
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <TemplateForm template={t} />
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
    </Stack>
  )
}

function TemplateForm({ template }: { template: Template }) {
  const queryClient = useQueryClient()
  const form = useForm({ initialValues: { subject: template.subject, body: template.body } })
  const done = () => queryClient.invalidateQueries({ queryKey: ['email-templates'] })
  const save = useMutation({
    mutationFn: async (values: typeof form.values) =>
      unwrap(await api.PUT('/api/email/templates/{kind}', { params: { path: { kind: template.kind } }, body: values })),
    onSuccess: () => {
      form.resetDirty()
      notifySaved()
      done()
    },
    onError: notifyError,
  })
  const reset = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/email/templates/{kind}', { params: { path: { kind: template.kind } } })),
    onSuccess: () => {
      notifySaved('Back to the built-in text')
      done()
    },
    onError: notifyError,
  })
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
      <Stack>
        <TextInput label="Subject" required {...form.getInputProps('subject')} />
        <Textarea label="Message" required autosize minRows={6} {...form.getInputProps('body')} />
        <Group gap={6}>
          {Object.entries(template.placeholders).map(([name, description]) => (
            <Tooltip key={name} label={description}>
              <Code>{`{${name}}`}</Code>
            </Tooltip>
          ))}
        </Group>
        <Group justify="flex-end">
          {template.customized && (
            <Button variant="subtle" color="gray" loading={reset.isPending} onClick={() => reset.mutate()}>
              Use the built-in text
            </Button>
          )}
          <Button type="submit" loading={save.isPending} disabled={!form.isDirty()}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  )
}

const LIMIT = 50

function LogTab() {
  const { locale } = useAuth()
  const [offset, setOffset] = useState(0)
  const { data, isFetching } = useQuery({
    queryKey: ['email-messages', offset],
    queryFn: async () =>
      unwrap(await api.GET('/api/email/messages', { params: { query: { limit: LIMIT, offset } } })),
    placeholderData: keepPreviousData,
  })
  const record = (m: Message) => {
    const base = m.entity_type ? RECORD_LINKS[m.entity_type] : undefined
    if (m.entity_type === 'report') return <Text size="sm">{m.entity_id}</Text>
    if (!base || !m.entity_id) return null
    return (
      <Anchor component={Link} to={`${base}/${m.entity_id}`} size="sm">
        {KIND_LABELS[m.kind] ?? m.kind}
      </Anchor>
    )
  }
  return (
    <DataTable<Message>
      loading={isFetching && !data}
      rows={data?.items}
      rowKey={(m) => m.id}
      empty="Nothing sent yet"
      page={data && { total: data.total, limit: LIMIT, offset, onOffset: setOffset }}
      columns={[
        { key: 'when', header: 'Sent', render: (m) => formatDateTime(m.created_at, locale.locale), width: 170 },
        {
          key: 'to',
          header: 'To',
          render: (m) => (
            <Stack gap={0}>
              <Text size="sm">{m.to_addresses}</Text>
              {m.cc_addresses && (
                <Text size="xs" c="dimmed">
                  cc {m.cc_addresses}
                </Text>
              )}
              {m.redirected_to && (
                <Text size="xs" c="orange">
                  went to {m.redirected_to}
                </Text>
              )}
            </Stack>
          ),
        },
        { key: 'subject', header: 'Subject', render: (m) => m.subject },
        { key: 'record', header: 'About', render: (m) => record(m) ?? KIND_LABELS[m.kind] ?? m.kind, wide: true },
        { key: 'by', header: 'By', render: (m) => m.sent_by ?? '—', wide: true },
        {
          key: 'status',
          header: 'Status',
          render: (m) =>
            m.status === 'sent' ? (
              <Badge variant="light" color={m.provider === 'console' || m.provider === 'none' ? 'gray' : 'green'}>
                {m.provider === 'console' || m.provider === 'none' ? 'logged only' : 'sent'}
              </Badge>
            ) : (
              <Tooltip label={m.error} multiline w={320}>
                <Badge variant="light" color="red">
                  failed
                </Badge>
              </Tooltip>
            ),
        },
      ]}
    />
  )
}
