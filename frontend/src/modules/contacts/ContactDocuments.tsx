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
  FileInput,
  Group,
  Menu,
  Modal,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconDots, IconFile, IconPlus, IconUpload } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, send, unwrap, type Schemas } from '../../api/client'
import { useAuth } from '../../auth/context'
import { ArchivedBadge, DateText } from '../../components/ui'
import { DOCUMENT_TYPES, labelOf } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'

type Doc = Schemas['DocumentOut']
type Detail = Schemas['PartyDetail']

const ACCEPT = 'application/pdf,image/*,.doc,.docx'
// Types where a newer document normally replaces the older one.
const REPLACES = new Set(['w9', 'w8', 'insurance', 'tax_exemption'])

export function DocumentStatusBadge({ doc }: { doc: Pick<Doc, 'status' | 'days_to_expiry'> }) {
  const days = doc.days_to_expiry ?? 0
  if (doc.status === 'expired')
    return (
      <Badge color="red" variant="light">
        Expired {-days} day{days === -1 ? '' : 's'} ago
      </Badge>
    )
  if (doc.status === 'expiring')
    return (
      <Badge color="yellow" variant="light">
        {days === 0 ? 'Expires today' : `Expires in ${days} day${days === 1 ? '' : 's'}`}
      </Badge>
    )
  if (doc.status === 'valid')
    return (
      <Badge color="green" variant="light">
        Valid
      </Badge>
    )
  return null
}

function fileUrl(doc: Doc, download = false) {
  return `/api/contacts/${doc.party_id}/documents/${doc.id}/file${download ? '?download=true' : ''}`
}

function DocumentForm({
  contact,
  doc,
  current,
  onClose,
}: {
  contact: Detail
  doc?: Doc
  current: Doc[]
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [type, setType] = useState<string | null>(doc?.document_type ?? 'w9')
  const [title, setTitle] = useState(doc?.title ?? '')
  const [file, setFile] = useState<File | null>(null)
  const [documentDate, setDocumentDate] = useState(doc?.document_date ?? '')
  const [expiresOn, setExpiresOn] = useState(doc?.expires_on ?? '')
  const [remindDays, setRemindDays] = useState<string | number>(doc?.remind_days_before ?? '')
  const [exemption, setExemption] = useState<string | null>(
    doc?.tax_exemption_id ? String(doc.tax_exemption_id) : null,
  )
  const [notes, setNotes] = useState(doc?.notes ?? '')
  const sameType = current.filter((d) => d.document_type === type && d.id !== doc?.id)
  // replacing is the default for W-9s, certificates and the like; contracts usually add up
  const [replaceChoice, setReplaceChoice] = useState<boolean | null>(null)
  const replace = replaceChoice ?? REPLACES.has(type ?? '')

  const typeLabel = labelOf(DOCUMENT_TYPES, type ?? '')
  const save = useMutation({
    mutationFn: async () => {
      const fields = {
        document_type: type as Doc['document_type'],
        title: title.trim() || typeLabel,
        document_date: documentDate || null,
        expires_on: expiresOn || null,
        remind_days_before: remindDays === '' ? null : Number(remindDays),
        tax_exemption_id: type === 'tax_exemption' && exemption ? Number(exemption) : null,
        notes: notes.trim() || null,
      }
      if (doc) {
        return unwrap(
          await api.PATCH('/api/contacts/{party_id}/documents/{document_id}', {
            params: { path: { party_id: contact.id, document_id: doc.id } },
            body: fields,
          }),
        )
      }
      const form = new FormData()
      for (const [key, value] of Object.entries(fields)) {
        if (value !== null) form.append(key, String(value))
      }
      if (file) form.append('file', file)
      if (replace && sameType.length) form.append('replace_previous', 'true')
      return send('POST', `/api/contacts/${contact.id}/documents`, form)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact-documents', contact.id] })
      queryClient.invalidateQueries({ queryKey: ['documents-attention'] })
      notifySaved(doc ? 'Document updated' : 'Document recorded')
      onClose()
    },
    onError: notifyError,
  })

  return (
    <Modal opened onClose={onClose} title={doc ? 'Edit document' : 'Add document'} size="lg">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select label="Type" data={DOCUMENT_TYPES} value={type} onChange={setType} allowDeselect={false} required />
            <TextInput
              label="Title"
              placeholder={typeLabel}
              value={title}
              onChange={(e) => setTitle(e.currentTarget.value)}
              maxLength={200}
            />
          </SimpleGrid>
          {!doc && (
            <FileInput
              label="File"
              description="PDF, image or Word document, up to 20 MB. Leave empty to record a paper copy; you can attach a scan later."
              placeholder="Choose a file"
              accept={ACCEPT}
              clearable
              leftSection={<IconFile size={16} />}
              value={file}
              onChange={setFile}
            />
          )}
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <TextInput
              type="date"
              label="Signed / issued"
              value={documentDate}
              onChange={(e) => setDocumentDate(e.currentTarget.value)}
            />
            <TextInput
              type="date"
              label="Expires"
              description="Empty: does not expire"
              value={expiresOn}
              onChange={(e) => setExpiresOn(e.currentTarget.value)}
            />
            <NumberInput
              label="Warn days before"
              description="Default 30"
              min={0}
              max={3650}
              allowDecimal={false}
              disabled={!expiresOn}
              value={remindDays}
              onChange={setRemindDays}
            />
          </SimpleGrid>
          {type === 'tax_exemption' && (
            <Select
              label="Supports exemption"
              description={
                contact.tax_exemptions.length
                  ? 'The exemption (Tax tab) is what removes tax from invoices; this is its certificate.'
                  : 'Add the exemption on the Tax tab so invoices are not taxed; then link it here.'
              }
              placeholder="None"
              clearable
              data={contact.tax_exemptions.map((e) => ({
                value: String(e.id),
                label: [e.certificate_type, e.certificate_number].filter(Boolean).join(' – '),
              }))}
              value={exemption}
              onChange={(value) => {
                setExemption(value)
                const linked = contact.tax_exemptions.find((e) => String(e.id) === value)
                if (linked?.valid_to && !expiresOn) setExpiresOn(linked.valid_to)
              }}
            />
          )}
          <Textarea label="Notes" autosize minRows={2} value={notes} onChange={(e) => setNotes(e.currentTarget.value)} />
          {!doc && sameType.length > 0 && (
            <Checkbox
              label={`This replaces the current ${typeLabel} (${sameType.length}); keep the old one${
                sameType.length > 1 ? 's' : ''
              } as archived`}
              checked={replace}
              onChange={(e) => setReplaceChoice(e.currentTarget.checked)}
            />
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending} disabled={!type}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

export function ContactDocuments({ contact, canEdit }: { contact: Detail; canEdit: boolean }) {
  // Files can hold taxpayer ids: only owners and bookkeepers may open them (the API enforces it).
  const { canEdit: mayOpenFiles, isOwner } = useAuth()
  const queryClient = useQueryClient()
  const [showArchived, setShowArchived] = useState(false)
  const [editing, setEditing] = useState<Doc | 'new' | null>(null)
  const { data: docs } = useQuery({
    queryKey: ['contact-documents', contact.id, showArchived],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/contacts/{party_id}/documents', {
          params: { path: { party_id: contact.id }, query: { archived: showArchived ? 'all' : 'current' } },
        }),
      ),
  })
  const current = (docs ?? []).filter((d) => !d.archived_at)
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['contact-documents', contact.id] })
    queryClient.invalidateQueries({ queryKey: ['documents-attention'] })
  }
  const action = useMutation({
    mutationFn: ({ method, path, body }: { method: string; path: string; body?: unknown }) =>
      send(method, path, body),
    onSuccess: refresh,
    onError: notifyError,
  })
  const attach = (doc: Doc, file: File) => {
    const form = new FormData()
    form.append('file', file)
    action.mutate(
      { method: 'PUT', path: `/api/contacts/${contact.id}/documents/${doc.id}/file`, body: form },
      { onSuccess: () => notifySaved('File attached') },
    )
  }
  const exemptionName = (id: number | null | undefined) => {
    const e = contact.tax_exemptions.find((x) => x.id === id)
    return e ? `Supports: ${e.certificate_type}` : null
  }

  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Text fw={600}>Documents on file</Text>
        <Group gap="sm">
          <Switch
            size="xs"
            label="Show replaced"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.currentTarget.checked)}
          />
          {canEdit && (
            <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing('new')}>
              Add document
            </Button>
          )}
        </Group>
      </Group>
      {docs && docs.length === 0 ? (
        <Text c="dimmed" size="sm">
          No documents yet (W-9, exemption certificates, insurance, contracts…)
        </Text>
      ) : (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Type</Table.Th>
              <Table.Th>Document</Table.Th>
              <Table.Th>Signed</Table.Th>
              <Table.Th>Expires</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {docs?.map((d) => (
              <Table.Tr key={d.id} opacity={d.archived_at ? 0.6 : 1}>
                <Table.Td>{labelOf(DOCUMENT_TYPES, d.document_type)}</Table.Td>
                <Table.Td>
                  <Stack gap={2}>
                    <Group gap="xs">
                      {d.file && mayOpenFiles ? (
                        <Anchor href={fileUrl(d)} target="_blank" rel="noopener" size="sm">
                          {d.title}
                        </Anchor>
                      ) : (
                        <Text size="sm">{d.title}</Text>
                      )}
                      <ArchivedBadge at={d.archived_at} />
                    </Group>
                    <Text size="xs" c="dimmed">
                      {d.file ? d.file.original_name : 'No file (paper copy)'}
                      {exemptionName(d.tax_exemption_id) && ` · ${exemptionName(d.tax_exemption_id)}`}
                      {d.notes && ` · ${d.notes}`}
                    </Text>
                  </Stack>
                </Table.Td>
                <Table.Td>
                  <DateText value={d.document_date} />
                </Table.Td>
                <Table.Td>
                  <Group gap="xs" wrap="nowrap">
                    {d.expires_on ? <DateText value={d.expires_on} /> : <Text size="sm" c="dimmed">—</Text>}
                    {!d.archived_at && <DocumentStatusBadge doc={d} />}
                  </Group>
                </Table.Td>
                <Table.Td>
                  {canEdit && (
                    <Group justify="flex-end">
                      <Menu position="bottom-end">
                        <Menu.Target>
                          <ActionIcon variant="subtle" aria-label={`Actions for ${d.title}`}>
                            <IconDots size={16} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item onClick={() => setEditing(d)}>Edit details</Menu.Item>
                          <FileUploadItem label={d.file ? 'Replace file…' : 'Attach file…'} onFile={(f) => attach(d, f)} />
                          {d.file && (
                            <Menu.Item component="a" href={fileUrl(d, true)}>
                              Download
                            </Menu.Item>
                          )}
                          <Menu.Item
                            onClick={() =>
                              action.mutate({
                                method: 'POST',
                                path: `/api/contacts/${contact.id}/documents/${d.id}/${d.archived_at ? 'unarchive' : 'archive'}`,
                              })
                            }
                          >
                            {d.archived_at ? 'Make current again' : 'Archive (replaced)'}
                          </Menu.Item>
                          {isOwner && (
                            <Menu.Item
                              color="red"
                              onClick={() =>
                                modals.openConfirmModal({
                                  title: 'Delete this document?',
                                  children: (
                                    <Text size="sm">
                                      Only for documents recorded by mistake. To keep a replaced document on file,
                                      archive it instead.
                                    </Text>
                                  ),
                                  labels: { confirm: 'Delete', cancel: 'Cancel' },
                                  confirmProps: { color: 'red' },
                                  onConfirm: () =>
                                    action.mutate(
                                      { method: 'DELETE', path: `/api/contacts/${contact.id}/documents/${d.id}` },
                                      { onSuccess: () => notifySaved('Document deleted') },
                                    ),
                                })
                              }
                            >
                              Delete
                            </Menu.Item>
                          )}
                        </Menu.Dropdown>
                      </Menu>
                    </Group>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {editing && (
        <DocumentForm
          contact={contact}
          doc={editing === 'new' ? undefined : editing}
          current={current}
          onClose={() => setEditing(null)}
        />
      )}
    </Card>
  )
}

/** A menu item that opens the file picker. */
function FileUploadItem({ label, onFile }: { label: string; onFile: (file: File) => void }) {
  return (
    <Menu.Item
      leftSection={<IconUpload size={14} />}
      onClick={() => {
        const input = document.createElement('input')
        input.type = 'file'
        input.accept = ACCEPT
        input.onchange = () => input.files?.[0] && onFile(input.files[0])
        input.click()
      }}
    >
      {label}
    </Menu.Item>
  )
}
