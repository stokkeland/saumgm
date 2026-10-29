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

import { Alert, Button, Group, Loader, Modal, Stack, TagsInput, Text, Textarea, TextInput } from '@mantine/core'
import { IconMail, IconPaperclip } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, unwrap } from '../api/client'
import type { Schemas } from '../api/client'
import { notifyError, notifySaved } from '../lib/notify'

type RecordType = 'invoice' | 'payment'
type Draft = Schemas['DraftOut']

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
  const [opened, setOpened] = useState(false)
  return (
    <>
      <Button variant="default" leftSection={<IconMail size={16} />} onClick={() => setOpened(true)}>
        {label}
      </Button>
      <Modal opened={opened} onClose={() => setOpened(false)} title="Send by email" size="lg">
        {opened && <EmailForm recordType={recordType} recordId={recordId} onDone={() => setOpened(false)} />}
      </Modal>
    </>
  )
}

function EmailForm({ recordType, recordId, onDone }: { recordType: RecordType; recordId: number; onDone: () => void }) {
  const draft = useQuery({
    queryKey: ['email-compose', recordType, recordId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/email/compose/{record_type}/{record_id}', {
          params: { path: { record_type: recordType, record_id: recordId } },
        }),
      ),
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
  return <Composer draft={draft.data} recordType={recordType} recordId={recordId} onDone={onDone} />
}

function Composer({
  draft,
  recordType,
  recordId,
  onDone,
}: {
  draft: Draft
  recordType: RecordType
  recordId: number
  onDone: () => void
}) {
  const queryClient = useQueryClient()
  const [to, setTo] = useState(draft.to)
  const [cc, setCc] = useState(draft.cc)
  const [subject, setSubject] = useState(draft.subject)
  const [body, setBody] = useState(draft.body)
  const send = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/email/send/{record_type}/{record_id}', {
          params: { path: { record_type: recordType, record_id: recordId } },
          body: { to, cc, subject, body },
        }),
      ),
    onSuccess: (sent) => {
      notifySaved(sent.redirected_to ? `Sent to ${sent.redirected_to} (redirected)` : `Sent to ${sent.to_addresses}`)
      queryClient.invalidateQueries({ queryKey: ['history', recordType, String(recordId)] })
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
      {draft.attachments.map((name) => (
        <Group key={name} gap={6}>
          <IconPaperclip size={16} />
          <Text size="sm">{name}</Text>
        </Group>
      ))}
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
