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

import { Alert, Button, Checkbox, Group, Loader, Modal, Stack, TagsInput, Text, Textarea, TextInput } from '@mantine/core'
import { IconMail, IconPaperclip } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap } from '../api/client'
import type { Schemas } from '../api/client'
import { notifyError, notifySaved } from '../lib/notify'

type RecordType = 'invoice' | 'payment'
type Draft = Schemas['DraftOut']
type ReportName = 'sales' | 'sales-tax' | 'expenses' | 'profit-loss' | 'aging'
type ReportQuery = { date_from?: string; date_to?: string; group?: string; basis?: 'accrual' | 'cash' }

/** What is being sent: how to get the draft, how to send it, and what to refresh afterwards. */
type Source = {
  key: unknown[]
  compose: () => Promise<Draft>
  send: (body: Schemas['SendIn'], pdf: boolean) => Promise<Schemas['MessageOut']>
  history?: unknown[]
  /** Offer a PDF copy as an attachment (an article); the file it would be. */
  optionalPdf?: string
}

/** A button that opens the "Send by email" dialog for one record (its PDF goes along). */
export function EmailButton({
  recordType,
  recordId,
  label = 'Email',
}: {
  recordType: RecordType
  recordId: number
  label?: string
}) {
  const path = { record_type: recordType, record_id: recordId }
  const source: Source = {
    key: [recordType, recordId],
    compose: async () => unwrap(await api.GET('/api/email/compose/{record_type}/{record_id}', { params: { path } })),
    send: async (body) => unwrap(await api.POST('/api/email/send/{record_type}/{record_id}', { params: { path }, body })),
    history: ['history', recordType, String(recordId)],
  }
  return <EmailDialogButton source={source} label={label} />
}

/** The same dialog for a report as shown: its PDF goes along, addressed to yourself. */
export function ReportEmailButton({ report, query }: { report: ReportName; query: ReportQuery }) {
  const params = { path: { report }, query }
  const source: Source = {
    key: ['report', report, query],
    compose: async () => unwrap(await api.GET('/api/reports/{report}/email', { params })),
    send: async (body) => unwrap(await api.POST('/api/reports/{report}/email', { params, body })),
  }
  return <EmailDialogButton source={source} label="Email" />
}

/** A knowledge base article: the message, then the article; a PDF copy if wanted. */
export function ArticleEmailButton({ articleId, pdfName }: { articleId: number; pdfName: string }) {
  const path = { article_id: articleId }
  const source: Source = {
    key: ['kb-article', articleId],
    compose: async () => unwrap(await api.GET('/api/kb/articles/{article_id}/email', { params: { path } })),
    send: async (body, pdf) =>
      unwrap(await api.POST('/api/kb/articles/{article_id}/email', { params: { path, query: { pdf } }, body })),
    history: ['history', 'kb_article', String(articleId)],
    optionalPdf: pdfName,
  }
  return <EmailDialogButton source={source} label="Email to…" />
}

function EmailDialogButton({ source, label }: { source: Source; label: string }) {
  const [opened, setOpened] = useState(false)
  return (
    <>
      <Button variant="default" leftSection={<IconMail size={16} />} onClick={() => setOpened(true)}>
        {label}
      </Button>
      <Modal opened={opened} onClose={() => setOpened(false)} title="Send by email" size="lg">
        {opened && <EmailForm source={source} onDone={() => setOpened(false)} />}
      </Modal>
    </>
  )
}

function EmailForm({ source, onDone }: { source: Source; onDone: () => void }) {
  const draft = useQuery({
    queryKey: ['email-compose', ...source.key],
    queryFn: source.compose,
    // Always the current template and recipients.
    gcTime: 0,
    retry: false,
  })
  if (draft.isPending) return <Loader size="sm" />
  if (draft.isError) {
    return (
      <Alert color="red" variant="light">
        {(draft.error as Error).message}
      </Alert>
    )
  }
  return <Composer draft={draft.data} source={source} onDone={onDone} />
}

function Composer({ draft, source, onDone }: { draft: Draft; source: Source; onDone: () => void }) {
  const queryClient = useQueryClient()
  const [to, setTo] = useState(draft.to)
  const [cc, setCc] = useState(draft.cc)
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const [pdf, setPdf] = useState(false)
  const send = useMutation({
    mutationFn: () => source.send({ to, cc, subject, body }, pdf),
    onSuccess: (sent) => {
      notifySaved(sent.redirected_to ? `Sent to ${sent.redirected_to} (redirected)` : `Sent to ${sent.to_addresses}`)
      if (source.history) queryClient.invalidateQueries({ queryKey: source.history })
      queryClient.invalidateQueries({ queryKey: ['email-messages'] })
      onDone()
    },
    onError: notifyError,
  })
  const splitPaste = (values: string[]) => values.flatMap((v) => v.split(/[,;\s]+/)).filter(Boolean)
  return (
    <Stack>
      {draft.redirect_to && (
        <Alert color="orange" variant="light">
          This installation sends every message to {draft.redirect_to} instead (EMAIL_REDIRECT_TO); the
          recipients below only appear in the message.
        </Alert>
      )}
      <TagsInput
        label="To"
        required
        value={to}
        onChange={(v) => setTo(splitPaste(v))}
        placeholder={to.length ? undefined : 'Type an address and press Enter'}
        splitChars={[',', ';', ' ']}
      />
      <TagsInput label="Cc" value={cc} onChange={(v) => setCc(splitPaste(v))} splitChars={[',', ';', ' ']} />
      <TextInput label="Subject" required value={subject} onChange={(e) => setSubject(e.currentTarget.value)} />
      <Textarea label="Message" required autosize minRows={8} maxRows={20} value={body} onChange={(e) => setBody(e.currentTarget.value)} />
      {source.optionalPdf && (
        <Text size="xs" c="dimmed">
          The article follows your message.
        </Text>
      )}
      {[...draft.attachments, ...(pdf && source.optionalPdf ? [source.optionalPdf] : [])].map((name) => (
        <Group key={name} gap={6}>
          <IconPaperclip size={16} />
          <Text size="sm">{name}</Text>
        </Group>
      ))}
      {source.optionalPdf && (
        <Checkbox label="Attach a PDF copy" checked={pdf} onChange={(e) => setPdf(e.currentTarget.checked)} />
      )}
      <Group justify="flex-end">
        <Button variant="default" onClick={onDone}>
          Cancel
        </Button>
        <Button
          leftSection={<IconMail size={16} />}
          disabled={!to.length || !subject.trim() || !body.trim()}
          loading={send.isPending}
          onClick={() => send.mutate()}
        >
          Send
        </Button>
      </Group>
    </Stack>
  )
}
