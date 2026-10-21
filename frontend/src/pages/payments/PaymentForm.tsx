import {
  Alert,
  Button,
  Card,
  Checkbox,
  Group,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { api, unwrap, type Schemas } from '../../api/client'
import { ContactSelect } from '../../components/ContactSelect'
import { DateText, Money, PageHeader } from '../../components/ui'
import { todayIso } from '../../lib/format'
import { PAYMENT_CHANNELS, PAYMENT_METHODS } from '../../lib/labels'
import { notifyError, notifySaved } from '../../lib/notify'

type OpenInvoice = Schemas['InvoiceListItem']

const cents = (v: number) => Math.round(v * 100) / 100

/** Open invoices of a contact with how much of a payment goes to each. */
function useOpenInvoices(partyId: number | null) {
  return useQuery({
    queryKey: ['invoices', { party: partyId, open: true }],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/invoices', {
          params: { query: { party_id: partyId!, payment: 'open', limit: 200 } },
        }),
      ).items,
    enabled: partyId !== null,
  })
}

/** Oldest due first (the list comes newest first). */
function oldestFirst(invoices: OpenInvoice[]) {
  return [...invoices].sort((a, b) =>
    (a.due_date ?? a.issue_date ?? '').localeCompare(b.due_date ?? b.issue_date ?? ''),
  )
}

export function ReceivePaymentPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params] = useSearchParams()
  const [partyId, setPartyId] = useState<number | null>(params.get('party') ? Number(params.get('party')) : null)
  const preselect = params.get('invoice') ? Number(params.get('invoice')) : null
  const [receivedDate, setReceivedDate] = useState(todayIso())
  const [amountInput, setAmount] = useState<number | string | null>(null)
  const [method, setMethod] = useState<string | null>('check')
  const [channel, setChannel] = useState<string | null>(null)
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')
  const [manualApplied, setManualApplied] = useState<Record<number, number | string> | null>(null)

  const { data: invoices } = useOpenInvoices(partyId)
  const ordered = useMemo(() => oldestFirst(invoices ?? []), [invoices])

  // Coming from an invoice's "Record payment": its balance is the default amount, applied to it.
  const preselected = preselect ? invoices?.find((i) => i.id === preselect) : undefined
  const defaultApplied: Record<number, number | string> = preselected
    ? { [preselected.id]: Number(preselected.balance_due) }
    : {}
  const applied = manualApplied ?? defaultApplied
  const setApplied = (
    change: (current: Record<number, number | string>) => Record<number, number | string>,
  ) => setManualApplied((current) => change(current ?? defaultApplied))
  const amount = amountInput ?? (preselected ? Number(preselected.balance_due) : '')

  const total = Number(amount || 0)
  const appliedTotal = cents(Object.values(applied).reduce<number>((sum, v) => sum + Number(v || 0), 0))
  const unapplied = cents(total - appliedTotal)

  const applyOldestFirst = () => {
    let remaining = total
    const next: Record<number, number> = {}
    for (const invoice of ordered) {
      if (remaining <= 0) break
      const part = cents(Math.min(remaining, Number(invoice.balance_due)))
      next[invoice.id] = part
      remaining = cents(remaining - part)
    }
    setManualApplied(next)
  }

  const save = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/payments', {
          body: {
            party_id: partyId!,
            received_date: receivedDate,
            amount: String(total),
            method: method as Schemas['PaymentCreate']['method'],
            channel: channel as Schemas['PaymentCreate']['channel'],
            reference: reference.trim() || null,
            notes: notes.trim() || null,
            auto_allocate: false,
            allocations: Object.entries(applied)
              .filter(([, v]) => Number(v) > 0)
              .map(([invoiceId, v]) => ({ invoice_id: Number(invoiceId), amount: String(v) })),
          },
        }),
      ),
    onSuccess: (payment) => {
      queryClient.invalidateQueries({ queryKey: ['payments'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['invoice'] })
      queryClient.invalidateQueries({ queryKey: ['contact-balance'] })
      notifySaved('Payment recorded')
      navigate(`/payments/${payment.id}`, { replace: true })
    },
    onError: notifyError,
  })

  const invalid = !partyId || total <= 0 || !receivedDate || unapplied < 0

  return (
    <>
      <PageHeader title="Receive payment" subtitle="Record money received and apply it to invoices" />
      <Stack>
        <Card withBorder>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
            <ContactSelect
              label="From"
              role="client"
              required
              value={partyId}
              onChange={(id) => {
                setPartyId(id)
                setManualApplied({})
              }}
            />
            <TextInput type="date" label="Received" required value={receivedDate} onChange={(e) => setReceivedDate(e.currentTarget.value)} />
            <NumberInput label="Amount" required min={0} decimalScale={2} value={amount} onChange={setAmount} />
            <Select label="Method" data={PAYMENT_METHODS} value={method} onChange={setMethod} />
            <Select label="Received by" clearable data={PAYMENT_CHANNELS} value={channel} onChange={setChannel} />
            <TextInput label="Reference" placeholder="Check number, transaction id" value={reference} onChange={(e) => setReference(e.currentTarget.value)} />
          </SimpleGrid>
          <Textarea mt="sm" label="Notes" autosize value={notes} onChange={(e) => setNotes(e.currentTarget.value)} />
        </Card>

        {partyId && (
          <Card withBorder>
            <Group justify="space-between" mb="xs">
              <Text fw={600}>Apply to open invoices</Text>
              <Button size="xs" variant="light" disabled={!total || !ordered.length} onClick={applyOldestFirst}>
                Apply oldest first
              </Button>
            </Group>
            {ordered.length === 0 ? (
              <Text size="sm" c="dimmed">
                No open invoices; the payment will be kept as credit for this client.
              </Text>
            ) : (
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={40} />
                    <Table.Th>Invoice</Table.Th>
                    <Table.Th>Date</Table.Th>
                    <Table.Th>Due</Table.Th>
                    <Table.Th ta="right">Balance</Table.Th>
                    <Table.Th w={150} ta="right">
                      Apply
                    </Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {ordered.map((invoice) => {
                    const value = applied[invoice.id] ?? ''
                    return (
                      <Table.Tr key={invoice.id}>
                        <Table.Td>
                          <Checkbox
                            aria-label={`Apply to invoice ${invoice.number}`}
                            checked={Number(value) > 0}
                            onChange={(e) => {
                              const checked = e.currentTarget.checked
                              setApplied((a) => ({
                                ...a,
                                [invoice.id]: checked
                                  ? cents(Math.min(Number(invoice.balance_due), Math.max(unapplied, 0) || Number(invoice.balance_due)))
                                  : '',
                              }))
                            }}
                          />
                        </Table.Td>
                        <Table.Td>{invoice.number}</Table.Td>
                        <Table.Td>
                          <DateText value={invoice.issue_date} />
                        </Table.Td>
                        <Table.Td>
                          <Text span size="sm" c={invoice.is_overdue ? 'red' : undefined}>
                            <DateText value={invoice.due_date} />
                          </Text>
                        </Table.Td>
                        <Table.Td ta="right">
                          <Money value={invoice.balance_due} />
                        </Table.Td>
                        <Table.Td>
                          <NumberInput
                            aria-label={`Amount for invoice ${invoice.number}`}
                            hideControls
                            min={0}
                            max={Number(invoice.balance_due)}
                            decimalScale={2}
                            value={value}
                            onChange={(v) => setApplied((a) => ({ ...a, [invoice.id]: v }))}
                          />
                        </Table.Td>
                      </Table.Tr>
                    )
                  })}
                </Table.Tbody>
              </Table>
            )}
            <Group justify="flex-end" gap="xl" mt="sm">
              <Text size="sm">
                Applied <Money value={String(appliedTotal)} />
              </Text>
              <Text size="sm" c={unapplied < 0 ? 'red' : undefined}>
                {unapplied < 0 ? 'Over-applied' : 'Left as credit'} <Money value={String(Math.abs(unapplied))} />
              </Text>
            </Group>
          </Card>
        )}
        {unapplied < 0 && <Alert color="red">More is applied to invoices than the payment amount.</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={() => navigate(-1)}>
            Cancel
          </Button>
          <Button disabled={invalid} loading={save.isPending} onClick={() => save.mutate()}>
            Record payment
          </Button>
        </Group>
      </Stack>
    </>
  )
}
