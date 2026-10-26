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
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Code,
  Divider,
  Grid,
  Group,
  Loader,
  Menu,
  Modal,
  NumberInput,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import {
  IconArchive,
  IconBan,
  IconCash,
  IconDots,
  IconPencil,
  IconReceiptRefund,
  IconTrash,
  IconX,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { useJurisdictions, useOrganization } from '../../api/lookups'
import { useAuth } from '../../auth/context'
import { HistoryPanel } from '../../components/HistoryPanel'
import { ArchivedBadge, DateText, Money, PageHeader, PaymentStatusBadge, PdfButton } from '../../components/ui'
import { formatDateTime, formatNumber, formatRate } from '../../lib/format'
import { labelOf, PAYMENT_METHODS } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'
import { InvoiceEditor } from './InvoiceEditor'
import { UndoWriteOffModal, WriteOffModal } from './WriteOffModal'

type Invoice = Schemas['InvoiceOut']

function useInvoice(id: number) {
  return useQuery({
    queryKey: ['invoice', id],
    queryFn: async () =>
      unwrap(await api.GET('/api/invoices/{invoice_id}', { params: { path: { invoice_id: id } } })),
  })
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Group justify="space-between" wrap="nowrap">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" ta="right">
        {children}
      </Text>
    </Group>
  )
}

function CreditNoteModal({ invoice, onClose }: { invoice: Invoice; onClose: () => void }) {
  const navigate = useNavigate()
  const [description, setDescription] = useState(`Credit for invoice ${invoice.number}`)
  const [amount, setAmount] = useState<number | string>('')
  const create = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/invoices/{invoice_id}/credit-note', {
          params: { path: { invoice_id: invoice.id } },
          body: { lines: [{ description, unit_price: String(amount), quantity: '1' }], notes: null },
        }),
      ),
    onSuccess: (note) => {
      notifySaved('Draft credit note created; review and issue it')
      navigate(`/invoices/${note.id}`)
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={`Credit note for invoice ${invoice.number}`}>
      <Stack>
        <Text size="sm" c="dimmed">
          For a discount, refund or write-off after the invoice was issued. To correct a mistake,
          revise the invoice instead.
        </Text>
        <TextInput label="Description" value={description} onChange={(e) => setDescription(e.currentTarget.value)} />
        <NumberInput label="Amount" min={0} decimalScale={2} value={amount} onChange={setAmount} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!amount || !description.trim()} loading={create.isPending} onClick={() => create.mutate()}>
            Create draft credit note
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function VoidModal({ invoice, onClose }: { invoice: Invoice; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')
  const voidIt = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/invoices/{invoice_id}/void', {
          params: { path: { invoice_id: invoice.id } },
          body: { reason },
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(['invoice', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      notifySaved(`Invoice ${saved.number} voided`)
      onClose()
    },
    onError: notifyError,
  })
  return (
    <Modal opened onClose={onClose} title={`Void invoice ${invoice.number}?`}>
      <Stack>
        <Text size="sm">
          A void invoice keeps its number but no longer counts as owed. This cannot be undone.
        </Text>
        <Textarea label="Reason" required autosize minRows={2} value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color="red" disabled={reason.trim().length < 3} loading={voidIt.isPending} onClick={() => voidIt.mutate()}>
            Void invoice
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function RevisionModal({ invoice, revisionNo, onClose }: { invoice: Invoice; revisionNo: number; onClose: () => void }) {
  const { data } = useQuery({
    queryKey: ['invoice-revision', invoice.id, revisionNo],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/invoices/{invoice_id}/revisions/{revision_no}', {
          params: { path: { invoice_id: invoice.id, revision_no: revisionNo } },
        }),
      ),
  })
  const snap = data?.snapshot as
    | { total: string; subtotal: string; tax_total: string; lines: { description: string; quantity: string; unit_price: string; line_total: string }[] }
    | undefined
  return (
    <Modal opened onClose={onClose} title={`Invoice ${invoice.number} as it was before revision ${revisionNo + 1}`} size="lg">
      {!snap ? (
        <Loader />
      ) : (
        <Stack>
          <Text size="sm">
            <b>Reason for the change:</b> {data?.reason}
          </Text>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Description</Table.Th>
                <Table.Th ta="right">Qty</Table.Th>
                <Table.Th ta="right">Price</Table.Th>
                <Table.Th ta="right">Amount</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {snap.lines.map((l, i) => (
                <Table.Tr key={i}>
                  <Table.Td>{l.description}</Table.Td>
                  <Table.Td ta="right">{Number(l.quantity)}</Table.Td>
                  <Table.Td ta="right">
                    <Money value={l.unit_price} />
                  </Table.Td>
                  <Table.Td ta="right">
                    <Money value={l.line_total} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Group justify="flex-end" gap="xl">
            <Text size="sm">
              Tax <Money value={snap.tax_total} />
            </Text>
            <Text fw={600}>
              Total <Money value={snap.total} strong />
            </Text>
          </Group>
          <Accordion variant="contained">
            <Accordion.Item value="raw">
              <Accordion.Control>All stored fields</Accordion.Control>
              <Accordion.Panel>
                <Code block>{JSON.stringify(data?.snapshot, null, 2)}</Code>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        </Stack>
      )}
    </Modal>
  )
}

function InvoiceView({ invoice }: { invoice: Invoice }) {
  const { locale } = useAuth()
  const { data: jurisdictions } = useJurisdictions()
  const [revision, setRevision] = useState<number | null>(null)
  const jurisdiction = jurisdictions?.find((j) => j.id === invoice.tax_jurisdiction_id)
  const billTo = [
    invoice.bill_to_company,
    invoice.bill_to_name && (invoice.bill_to_company ? `Attn: ${invoice.bill_to_name}` : invoice.bill_to_name),
    invoice.bill_to_line1,
    invoice.bill_to_line2,
    [invoice.bill_to_city, invoice.bill_to_region, invoice.bill_to_postal_code].filter(Boolean).join(' '),
    invoice.bill_to_country,
    invoice.bill_to_email,
    invoice.bill_to_phone,
  ].filter(Boolean)
  const showLegacyTax = invoice.lines.some((l) => l.legacy_unit_tax && Number(l.legacy_unit_tax) !== 0)

  return (
    <Stack>
      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <Text size="sm" c="dimmed" mb={4}>
              Bill to
            </Text>
            {billTo.map((line, i) => (
              <Text key={i} size="sm" fw={i === 0 ? 600 : undefined}>
                {line}
              </Text>
            ))}
            <Anchor component={Link} to={`/contacts/${invoice.party_id}`} size="sm" mt="xs">
              Open contact {invoice.party_name}
            </Anchor>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <Stack gap={4}>
              <Row label="Invoice date">
                <DateText value={invoice.issue_date} />
              </Row>
              <Row label="Due">
                <DateText value={invoice.due_date} />
              </Row>
              <Row label="Terms">{invoice.terms_text ?? (invoice.terms_days !== null ? `${invoice.terms_days} days` : '')}</Row>
              <Row label="Tax location">{jurisdiction?.name ?? invoice.tax_location_text ?? '—'}</Row>
              {invoice.credited_invoice_id && (
                <Row label="Credits invoice">
                  <Anchor component={Link} to={`/invoices/${invoice.credited_invoice_id}`}>
                    open
                  </Anchor>
                </Row>
              )}
              {invoice.void_reason && <Row label="Void reason">{invoice.void_reason}</Row>}
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>

      <Card withBorder p={0}>
        <Table.ScrollContainer minWidth={640}>
          <Table verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Description</Table.Th>
                <Table.Th ta="right">Qty</Table.Th>
                <Table.Th ta="right">Price</Table.Th>
                <Table.Th ta="right">Discount</Table.Th>
                {showLegacyTax && <Table.Th ta="right">Tax / unit (old)</Table.Th>}
                <Table.Th ta="right">Amount</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {invoice.lines.map((l) => (
                <Table.Tr key={l.id}>
                  <Table.Td>{l.description}</Table.Td>
                  <Table.Td ta="right">
                    {formatNumber(l.quantity, locale.locale)} {l.unit}
                  </Table.Td>
                  <Table.Td ta="right">
                    <Money value={l.unit_price} />
                  </Table.Td>
                  <Table.Td ta="right">{Number(l.unit_discount) ? <Money value={l.unit_discount} /> : ''}</Table.Td>
                  {showLegacyTax && (
                    <Table.Td ta="right">{Number(l.legacy_unit_tax) ? <Money value={l.legacy_unit_tax} /> : ''}</Table.Td>
                  )}
                  <Table.Td ta="right">
                    <Money value={l.line_total} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Stack>
          {invoice.notes && (
            <Card withBorder>
              <Text size="sm" c="dimmed">
                Notes
              </Text>
              <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                {invoice.notes}
              </Text>
            </Card>
          )}
          <Card withBorder>
            <Text fw={600} mb="xs">
              Payments
            </Text>
            {invoice.payments.length === 0 ? (
              <Text size="sm" c="dimmed">
                No payments recorded
              </Text>
            ) : (
              <Table>
                <Table.Tbody>
                  {invoice.payments.map((p) => (
                    <Table.Tr key={p.payment_id}>
                      <Table.Td>
                        <Anchor component={Link} to={`/payments/${p.payment_id}`} size="sm">
                          <DateText value={p.received_date} />
                        </Anchor>
                      </Table.Td>
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
            {invoice.credit_note_ids.length > 0 && (
              <Group gap="xs" mt="xs">
                <Text size="sm">Credit notes:</Text>
                {invoice.credit_note_ids.map((id) => (
                  <Anchor key={id} component={Link} to={`/invoices/${id}`} size="sm">
                    #{id}
                  </Anchor>
                ))}
              </Group>
            )}
          </Card>
        </Stack>
        <Card withBorder style={{ alignSelf: 'start' }}>
          <Stack gap={6}>
            <Row label="Subtotal">
              <Money value={invoice.subtotal} />
            </Row>
            {Number(invoice.freight) !== 0 && (
              <Row label="Freight">
                <Money value={invoice.freight} />
              </Row>
            )}
            {Number(invoice.adjustment) !== 0 && (
              <Row label={invoice.adjustment_note ?? 'Adjustment'}>
                <Money value={invoice.adjustment} />
              </Row>
            )}
            {invoice.taxes.map((t) => (
              <Row key={`${t.jurisdiction_id}-${t.name}`} label={`${t.name} ${formatRate(t.rate, locale.locale)}`}>
                <Money value={t.amount} />
              </Row>
            ))}
            <Divider />
            <Row label="Total">
              <Money value={invoice.total} strong />
            </Row>
            <Row label="Paid">
              <Money value={invoice.amount_paid} />
            </Row>
            {Number(invoice.amount_credited) !== 0 && (
              <Row label="Credited">
                <Money value={invoice.amount_credited} />
              </Row>
            )}
            <Row label="Balance due">
              <Money value={invoice.balance_due} strong />
            </Row>
          </Stack>
        </Card>
      </SimpleGrid>

      <Tabs defaultValue="revisions" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="revisions">Revisions ({invoice.revisions.length})</Tabs.Tab>
          <Tabs.Tab value="history">History</Tabs.Tab>
          {invoice.legacy_data && <Tabs.Tab value="legacy">Old system</Tabs.Tab>}
        </Tabs.List>
        <Tabs.Panel value="revisions">
          {invoice.revisions.length === 0 ? (
            <Text size="sm" c="dimmed">
              Never revised
            </Text>
          ) : (
            <Table>
              <Table.Tbody>
                {invoice.revisions.map((r) => (
                  <Table.Tr key={r.revision_no}>
                    <Table.Td>Revision {r.revision_no + 1}</Table.Td>
                    <Table.Td>{formatDateTime(r.changed_at, locale.locale)}</Table.Td>
                    <Table.Td>{r.reason}</Table.Td>
                    <Table.Td>
                      <Button size="xs" variant="subtle" onClick={() => setRevision(r.revision_no)}>
                        Show earlier version
                      </Button>
                      {r.pdf_file_id !== null && (
                        <Button
                          size="xs"
                          variant="subtle"
                          component="a"
                          href={`/api/invoices/${invoice.id}/revisions/${r.revision_no}/pdf`}
                          target="_blank"
                          rel="noopener"
                        >
                          PDF as sent
                        </Button>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Tabs.Panel>
        <Tabs.Panel value="history">
          <HistoryPanel entityType="invoice" entityId={invoice.id} />
        </Tabs.Panel>
        <Tabs.Panel value="legacy">
          <Code block>{JSON.stringify(invoice.legacy_data, null, 2)}</Code>
        </Tabs.Panel>
      </Tabs>
      {revision !== null && <RevisionModal invoice={invoice} revisionNo={revision} onClose={() => setRevision(null)} />}
    </Stack>
  )
}

export function InvoicePage() {
  const { id } = useParams()
  const invoiceId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canEdit, isOwner } = useAuth()
  const { data: organization } = useOrganization()
  const { data: invoice, error } = useInvoice(invoiceId)
  const [revising, setRevising] = useState(false)
  const [dialog, setDialog] = useState<'credit' | 'void' | 'writeoff' | 'undo' | null>(null)

  const archive = useMutation({
    mutationFn: async (archived: boolean) =>
      unwrap(
        await api.POST(
          archived ? '/api/invoices/{invoice_id}/archive' : '/api/invoices/{invoice_id}/unarchive',
          { params: { path: { invoice_id: invoiceId } } },
        ),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(['invoice', saved.id], saved)
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
    },
    onError: notifyError,
  })
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE('/api/invoices/{invoice_id}', { params: { path: { invoice_id: invoiceId } } })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      notifySaved('Draft deleted')
      navigate('/invoices')
    },
    onError: notifyError,
  })

  if (error) return <Text c="red">{error.message}</Text>
  if (!invoice) return <Loader />

  const kind = invoice.kind === 'credit_note' ? 'Credit note' : 'Invoice'
  const title =
    invoice.status === 'draft' ? `Draft ${kind.toLowerCase()}` : `${kind} ${invoice.number}`
  const editable = canEdit && !invoice.archived_at
  // The business can restrict revising issued invoices to the owner.
  const ownerOnlyRevise = !isOwner && !!organization?.invoice_revision_owner_only

  if (invoice.status === 'draft' && editable) {
    return (
      <>
        <PageHeader
          title={title}
          subtitle={invoice.party_name}
          actions={
            <>
            <PdfButton href={`/api/invoices/${invoice.id}/pdf`} label="Preview PDF" />
            <Button
              color="red"
              variant="light"
              leftSection={<IconTrash size={16} />}
              onClick={() =>
                modals.openConfirmModal({
                  title: 'Delete this draft?',
                  labels: { confirm: 'Delete', cancel: 'Cancel' },
                  confirmProps: { color: 'red' },
                  onConfirm: () => remove.mutate(),
                })
              }
            >
              Delete draft
            </Button>
            </>
          }
        />
        <InvoiceEditor
          key={invoice.id}
          mode="draft"
          invoice={invoice}
          onDone={() => {}}
          onCancel={() => navigate('/invoices')}
        />
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={
          <Group gap="sm">
            {title}
            <PaymentStatusBadge status={invoice.payment_status} overdue={invoice.is_overdue} />
            <ArchivedBadge at={invoice.archived_at} />
            {invoice.is_historical && (
              <Badge variant="outline" color="gray" size="sm">
                Imported
              </Badge>
            )}
          </Group>
        }
        subtitle={invoice.party_name}
        actions={
          !revising && (
            <>
              <PdfButton href={`/api/invoices/${invoice.id}/pdf`} />
              {editable && (
            <>
              {invoice.status === 'issued' && invoice.kind === 'invoice' && Number(invoice.balance_due) > 0 && (
                <Button
                  component={Link}
                  to={`/payments/new?party=${invoice.party_id}&invoice=${invoice.id}`}
                  leftSection={<IconCash size={16} />}
                >
                  Record payment
                </Button>
              )}
              {invoice.status === 'issued' && !ownerOnlyRevise && !invoice.write_off_date && (
                <Button variant="light" leftSection={<IconPencil size={16} />} onClick={() => setRevising(true)}>
                  Revise
                </Button>
              )}
              <Menu position="bottom-end">
                <Menu.Target>
                  <ActionIcon variant="default" size="lg" aria-label="More actions">
                    <IconDots size={18} />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  {invoice.status === 'issued' && invoice.kind === 'invoice' && (
                    <Menu.Item leftSection={<IconReceiptRefund size={14} />} onClick={() => setDialog('credit')}>
                      Credit note…
                    </Menu.Item>
                  )}
                  {invoice.status === 'issued' && invoice.kind === 'invoice' && Number(invoice.balance_due) > 0 && (
                    <Menu.Item leftSection={<IconBan size={14} />} onClick={() => setDialog('writeoff')}>
                      Write off as uncollectible…
                    </Menu.Item>
                  )}
                  {invoice.status === 'issued' && !invoice.write_off_date && (
                    <Menu.Item color="red" leftSection={<IconX size={14} />} onClick={() => setDialog('void')}>
                      Void…
                    </Menu.Item>
                  )}
                  <Menu.Item leftSection={<IconArchive size={14} />} onClick={() => archive.mutate(true)}>
                    Archive
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </>
              )}
            </>
          )
        }
      />
      {invoice.archived_at && isOwner && (
        <Button mb="md" variant="light" size="xs" onClick={() => archive.mutate(false)}>
          Unarchive
        </Button>
      )}
      {invoice.write_off_date && (
        <Alert color="dark" variant="light" mb="md" title="Written off as uncollectible">
          <Group justify="space-between" align="flex-start">
            <Text size="sm">
              <Money value={invoice.write_off_amount} /> on <DateText value={invoice.write_off_date} />
              {invoice.write_off_reason && <> — {invoice.write_off_reason}</>}
            </Text>
            {isOwner && (
              <Button size="xs" variant="subtle" onClick={() => setDialog('undo')}>
                Undo write-off
              </Button>
            )}
          </Group>
        </Alert>
      )}
      {revising ? (
        <InvoiceEditor
          mode="revise"
          invoice={invoice}
          onDone={() => setRevising(false)}
          onCancel={() => setRevising(false)}
        />
      ) : (
        <InvoiceView invoice={invoice} />
      )}
      {dialog === 'credit' && <CreditNoteModal invoice={invoice} onClose={() => setDialog(null)} />}
      {dialog === 'void' && <VoidModal invoice={invoice} onClose={() => setDialog(null)} />}
      {dialog === 'writeoff' && <WriteOffModal invoiceIds={[invoice.id]} onClose={() => setDialog(null)} />}
      {dialog === 'undo' && <UndoWriteOffModal invoice={invoice} onClose={() => setDialog(null)} />}
    </>
  )
}

export function NewInvoicePage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const party = params.get('party')
  return (
    <>
      <PageHeader title="New invoice" subtitle="Saved as a draft until you issue it" />
      <InvoiceEditor
        mode="create"
        partyId={party ? Number(party) : null}
        onDone={(saved) => navigate(`/invoices/${saved.id}`, { replace: true })}
        onCancel={() => navigate(-1)}
      />
    </>
  )
}
